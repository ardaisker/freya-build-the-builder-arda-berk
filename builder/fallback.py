"""A build must end with a workflow. When the compiler or the lint rejects a spec, the optional parts of the spec are moved,
step by step, into `residual_rules` (they stay in the prompts word for word, only the code for them is left out) and the
spec is compiled again. The core of the call (opening, security check, tool wiring, deadlines, floors, outcomes) is never
touched. Nothing here names a bank, a rule or a value."""
from __future__ import annotations

import copy
import json

# each level drops these sections on top of the levels before it
LEVELS = [
    ("special_cases",),
    ("multi_product", "forbidden_offers", "confirm_record", "debt_statement"),
    ("third_party", "persuasion", "date_rules"),
]


def degrade(spec: dict, level: int) -> dict:
    """The spec for fallback `level` (1..len(LEVELS)). Level 0 is the spec itself."""
    out = copy.deepcopy(spec)
    residual = list(out.get("residual_rules") or [])
    for keys in LEVELS[:level]:
        for k in keys:
            v = out.get(k)
            if v in (None, "", [], {}):
                continue
            residual.append(f"[{k}] " + json.dumps(v, ensure_ascii=False))
            out[k] = [] if isinstance(v, list) else {}
    out["residual_rules"] = residual
    return out


def compile_with_fallback(spec: dict, build, log=print):
    """`build(spec)` compiles and lints, and raises when it cannot. Returns (workflow, spec used, level).
    Raises the first error when even the last level fails."""
    first = None
    for level in range(len(LEVELS) + 1):
        s = spec if level == 0 else degrade(spec, level)
        try:
            return build(s), s, level
        except Exception as e:
            first = first or e
            log(f"compile at fallback level {level} failed: {type(e).__name__}: {str(e)[:300]}")
    raise first
