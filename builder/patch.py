"""Failures -> a revised spec. The model may change instruction strings and residual rules; the topology is fixed by compile.py."""
from __future__ import annotations

import json

SYSTEM = """You improve a policy spec for a phone agent after seeing failed test calls. Answer with ONE JSON object: the complete revised spec, same keys.
Rules:
- Change only what the failures show: sharpen instruction strings, add a missing rule to residual_rules, fix a wrong value that contradicts the material.
- Every value must still come from the material and the tool API enums. Never add a rule that the material does not contain.
- Keep every exact spoken sentence the material prescribes.
- Do not remove rules. Do not change calendar, bands or outcomes unless the material proves they were extracted wrongly.
"""


def patch_spec(llm, spec: dict, failures: list[dict], briefs_text: list[tuple[str, str]], openapi: dict) -> dict:
    parts = ["# Current spec\n", json.dumps(spec, indent=1, ensure_ascii=False), "\n\n# Failed cases\n"]
    for f in failures:
        parts.append(f"\n## {f['id']} ({f['family']})\nReasons: {json.dumps(f['failed'])}\nTools called: {f['tools']}\nTranscript:\n{f['transcript']}\n")
    for name, text in briefs_text:
        parts += [f"\n\n# Material: {name}\n", text]
    parts.append("\n\nReturn the complete revised spec as one JSON object.")
    return llm.ask_json(f"revise the spec from {len(failures)} failed calls", SYSTEM, "".join(parts), retries=1)
