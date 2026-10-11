"""After the final briefs open, nothing from them may be written into the builder: no rule, no value, no name.
This compares every line added to the builder since a git tag with the words, numbers and dates that occur in the
final material but nowhere in the repository at that tag, and fails when one of them shows up.

  python3 builder/leakcheck.py --base pre-reveal briefs/hidden-1.md briefs/hidden-1.openapi.json ..."""
from __future__ import annotations

import argparse, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WATCHED = ["builder", "tests", "tools", "fixtures", "freya.py", "README-BUILDER.md", "requirements.txt"]
TOKEN = re.compile(r"\d{4}-\d{2}-\d{2}|\d+(?:[.,]\d+)*|[A-Za-z][A-Za-z_]{3,}")


def tokens(text):
    return set(t.lower() for t in TOKEN.findall(text))


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=str(ROOT), errors="replace").stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hidden", nargs="+", help="the final brief and tool API files")
    ap.add_argument("--base", default="pre-reveal")
    a = ap.parse_args()
    hidden_paths = {str(pathlib.Path(h).resolve()) for h in a.hidden}
    hidden = set()
    for h in a.hidden:
        hidden |= tokens(pathlib.Path(h).read_text(errors="replace"))
    known = set()
    for path in git("ls-tree", "-r", "--name-only", a.base).splitlines():
        if str((ROOT / path).resolve()) in hidden_paths:
            continue
        known |= tokens(git("show", f"{a.base}:{path}"))
    only_hidden = hidden - known
    added = []                                              # (file, line) added since the tag, committed or not
    cur = ""
    for line in git("diff", a.base, "--unified=0", "--", *WATCHED).splitlines():
        if line.startswith("+++ "):
            cur = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            added.append((cur, line[1:]))
    for path in git("ls-files", "--others", "--exclude-standard", "--", *WATCHED).splitlines():
        if str((ROOT / path).resolve()) in hidden_paths:
            continue
        try:
            added += [(path, l) for l in (ROOT / path).read_text(errors="replace").splitlines()]
        except Exception:
            pass
    hits = []
    for path, line in added:
        found = tokens(line) & only_hidden
        if found:
            hits.append((path, sorted(found), line.strip()[:160]))
    print(f"final material: {len(hidden)} distinct words/numbers, {len(only_hidden)} of them new since {a.base}; {len(added)} added builder lines checked")
    for path, found, line in hits:
        print(f"LEAK? {path}: {', '.join(found)}  |  {line}")
    print("clean: nothing from the final material is in the builder" if not hits else f"{len(hits)} line(s) to look at")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
