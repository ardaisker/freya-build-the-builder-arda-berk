"""Read a case folder: every file a client might send (text, mail, JSON, PDF, Word, Excel, a zip of those) becomes
(relative path, text). Nothing here knows what the case is about."""
from __future__ import annotations

import email
import email.policy
import html
import io
import json
import pathlib
import re
import subprocess
import sys
import zipfile

TEXT = {".md", ".txt", ".json", ".csv", ".tsv", ".yaml", ".yml", ".xml", ".log", ".ini", ".toml", ".js", ".ts", ".mjs", ".py", ".sh", ".sql", ".http", ".jsonc", ".jsonl", ".vtt", ".srt", ".rtf", ""}
SKIP_DIRS = {"node_modules", ".git", "__MACOSX", ".wrangler", "dist"}
MAX_FILE = 400_000


def _strip_tags(s: str) -> str:
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", s)
    s = re.sub(r"(?i)</t[dh]>", " | ", s)
    return re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def _pdf(data: bytes) -> str:
    try:
        import pypdf
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pypdf"], check=False)
        import pypdf
    r = pypdf.PdfReader(io.BytesIO(data))
    return "\n\n".join(f"[page {i + 1}]\n" + (p.extract_text() or "") for i, p in enumerate(r.pages))


def _docx(data: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(data))
    out = []
    for name in z.namelist():
        if re.match(r"word/(document|header\d*|footer\d*|footnotes|comments)\.xml$", name):
            x = z.read(name).decode("utf-8", "replace")
            x = re.sub(r"</w:p>", "\n", x)
            x = re.sub(r"</w:tc>", " | ", x)
            x = re.sub(r"<w:tab/>", "\t", x)
            out.append(html.unescape(re.sub(r"<[^>]+>", "", x)))
    return "\n".join(out)


def _xlsx(data: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in re.findall(r"(?s)<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8", "replace")):
            shared.append(html.unescape("".join(re.findall(r"(?s)<t[^>]*>(.*?)</t>", si))))
    out = []
    for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
        out.append(f"[{name.split('/')[-1]}]")
        for row in re.findall(r"(?s)<row[^>]*>(.*?)</row>", z.read(name).decode("utf-8", "replace")):
            cells = []
            for attrs, body in re.findall(r"(?s)<c([^>]*)>(.*?)</c>", row):
                v = re.search(r"(?s)<v>(.*?)</v>", body)
                t = re.search(r"(?s)<t[^>]*>(.*?)</t>", body)
                val = v.group(1) if v else (t.group(1) if t else "")
                if 't="s"' in attrs and val.isdigit() and int(val) < len(shared):
                    val = shared[int(val)]
                cells.append(html.unescape(val))
            out.append(" | ".join(cells))
    return "\n".join(out)


def _pptx(data: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(data))
    out = []
    for name in sorted(n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)):
        out.append(f"[{name.split('/')[-1]}] " + " ".join(html.unescape(t) for t in re.findall(r"(?s)<a:t>(.*?)</a:t>", z.read(name).decode("utf-8", "replace"))))
    return "\n".join(out)


def _mail(data: bytes, rel: str, out: list) -> str:
    m = email.message_from_bytes(data, policy=email.policy.default)
    head = "\n".join(f"{h}: {m.get(h)}" for h in ("From", "To", "Cc", "Date", "Subject") if m.get(h))
    body, parts = "", list(m.walk()) if m.is_multipart() else [m]
    for p in parts:
        if p.is_multipart():
            continue
        name = p.get_filename()
        try:
            payload = p.get_payload(decode=True) or b""
        except Exception:
            payload = b""
        if name:
            _one(rel + "::" + name, payload, out)
        elif p.get_content_type() == "text/plain" and not body:
            body = payload.decode(p.get_content_charset() or "utf-8", "replace")
        elif p.get_content_type() == "text/html" and not body:
            body = _strip_tags(payload.decode(p.get_content_charset() or "utf-8", "replace"))
    return head + "\n\n" + body


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1254", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", "replace")


BIG_DATA = 120_000


def _shrink(v, budget):
    """A JSON value cut to about `budget` characters: the first entries of every long list or record table are kept
    whole, later ones are shortened and then left out, so the model sees the exact shapes without reading every row."""
    if len(json.dumps(v, ensure_ascii=False)) <= budget:
        return v
    if isinstance(v, str):
        return v[:max(20, budget - 10)] + "…(cut)"
    if budget < 120:
        if isinstance(v, dict):
            return "…(cut: record with fields " + ", ".join(str(k) for k in list(v)[:12]) + ")"
        if isinstance(v, list):
            return f"…(cut: list of {len(v)})"
        return v
    table = isinstance(v, dict) and len(v) > 6 and len({type(x).__name__ for x in v.values()}) == 1 and isinstance(next(iter(v.values())), (dict, list))
    if isinstance(v, list) or table:
        items = list(v.items()) if table else list(enumerate(v))
        head = min(2, len(items))
        rest = items[head:]
        kept = [(k, _shrink(x, int(budget * 0.6 / max(1, head)))) for k, x in items[:head]]
        small = int(budget * 0.4 / max(1, len(rest)))
        if small < 120:
            n = int(budget * 0.4 // 120)
            kept += [(k, _shrink(x, 120)) for k, x in rest[:n]]
            if len(rest) > n:
                kept.append(("…", f"(cut: {len(rest) - n} more entries of the same shape)"))
        else:
            kept += [(k, _shrink(x, small)) for k, x in rest]
        return dict(kept) if table else [x for _, x in kept]
    if isinstance(v, dict):
        keys = list(v)
        sizes = {k: len(json.dumps(v[k], ensure_ascii=False)) for k in keys}
        out, left = {}, budget
        for k in sorted(keys, key=lambda k: sizes[k]):          # small fields first, the large ones share what is left
            out[k] = _shrink(v[k], max(40, left // max(1, len(keys) - len(out))))
            left -= len(json.dumps(out[k], ensure_ascii=False))
        return {k: out[k] for k in keys}
    return v


def _big_json(text: str) -> str:
    try:
        doc = json.loads(text)
    except ValueError:
        return text
    cut = json.dumps(_shrink(doc, BIG_DATA // 2), ensure_ascii=False)
    return (f"(large data file, {len(text)} characters: abridged below. The first entries of each list or table are complete, later ones are shortened with '…(cut)'. "
            "The shapes and field names are exact; the builder checks the services against the real data.)\n" + cut)


def _one(rel: str, data: bytes, out: list):
    """Append (rel, text) for one file; containers (zip, mail attachments) append their members."""
    ext = pathlib.PurePosixPath(rel.split("::")[-1]).suffix.lower()
    try:
        if ext == ".zip":
            z = zipfile.ZipFile(io.BytesIO(data))
            for n in sorted(z.namelist()):
                if n.endswith("/") or any(part in SKIP_DIRS or part.startswith(".") for part in n.split("/")):
                    continue
                _one(rel + "::" + n, z.read(n), out)
            return
        if ext == ".pdf":
            text = _pdf(data)
        elif ext in (".docx", ".docm"):
            text = _docx(data)
        elif ext in (".xlsx", ".xlsm"):
            text = _xlsx(data)
        elif ext == ".pptx":
            text = _pptx(data)
        elif ext in (".eml", ".msg", ".mbox"):
            text = _mail(data, rel, out)
        elif ext in (".html", ".htm"):
            text = _strip_tags(_decode(data))
        elif ext in TEXT or (b"\x00" not in data[:4000]):
            text = _decode(data)
        else:
            out.append((rel, f"(binary file, {len(data)} bytes, not read)"))
            return
    except Exception as e:      # one unreadable file never stops the build
        out.append((rel, f"(could not be read: {type(e).__name__}: {str(e)[:120]})"))
        return
    text = text.strip()
    if ext in (".json", ".jsonl") and len(text) > BIG_DATA:
        text = _big_json(text)
    if len(text) > MAX_FILE:
        text = text[:MAX_FILE] + f"\n(... cut, {len(text) - MAX_FILE} more characters)"
    out.append((rel, text or "(empty)"))


def read_case(paths) -> list[tuple[str, str]]:
    """Every readable file under the given paths as (relative path, text), in a stable order."""
    out: list[tuple[str, str]] = []
    for p in paths:
        pp = pathlib.Path(p)
        if pp.is_dir():
            for f in sorted(x for x in pp.rglob("*") if x.is_file()):
                relp = f.relative_to(pp)
                if any(part in SKIP_DIRS or part.startswith(".") for part in relp.parts):
                    continue
                _one(str(relp), f.read_bytes(), out)
        elif pp.is_file():
            _one(pp.name, pp.read_bytes(), out)
    return out


def as_prompt(material: list[tuple[str, str]], limit: int = 900_000) -> str:
    """The material as one text block for the model, each file under its path. Very large packs are cut file by file."""
    total = sum(len(t) for _, t in material)
    per = None if total <= limit else max(4000, limit // max(1, len(material)))
    blocks = []
    for rel, text in material:
        if per and len(text) > per:
            text = text[:per] + "\n(... cut)"
        blocks.append(f"===== FILE: {rel} =====\n{text}")
    return "\n\n".join(blocks)


if __name__ == "__main__":
    mat = read_case(sys.argv[1:])
    for rel, text in mat:
        print(f"{len(text):>8}  {rel}")
    print(json.dumps({"files": len(mat), "chars": sum(len(t) for _, t in mat)}))
