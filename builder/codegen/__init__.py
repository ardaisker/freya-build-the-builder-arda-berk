"""Python snippets that run inside Freya code nodes. Rules (docs/tools-and-code.md): read/write through `vars`,
never raise, only json/re/datetime, and NO brace characters at all (the platform may template `{{ }}`).
The spec is embedded as a JSON string with braces written as \\x7b / \\x7d escapes."""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def embed_json(obj) -> str:
    """A Python expression that rebuilds `obj` at run time without a single brace in the source."""
    s = json.dumps(obj, ensure_ascii=True, separators=(",", ":"))
    s = s.replace("\\", "\\\\").replace("'", "\\'").replace("{", "\\x7b").replace("}", "\\x7d")
    return "json.loads('" + s + "')"


def snippet(name: str, libs=("calendar_lib",), **consts) -> str:
    """Load codegen/<name>.py and prepend constant assignments (each value embedded brace-free)."""
    lib = "\n".join((HERE / (l + ".py")).read_text() for l in libs)
    body = (HERE / (name + ".py")).read_text()
    head = "import json, re, datetime\n"
    for k, v in consts.items():
        head += f"{k} = {embed_json(v)}\n"
    code = head + lib + "\n" + body
    assert "{" not in code and "}" not in code, f"brace in snippet {name}"
    return code
