"""Brief(s) + tool API -> policy spec (JSON). The only place the builder reads natural language.

The spec schema is generic. Values come from the brief and from the tool API's enums, never from this code.
"""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SCHEMA = (HERE / "spec_schema.json").read_text()

SYSTEM = """You are a precise analyst turning a bank's call specification into a machine-readable policy spec.
You answer with ONE JSON object and nothing else. No markdown, no commentary.
Rules:
- Follow the schema exactly (same keys). Fill every key. Use "" or [] when the material says nothing. Never null.
- Every outcome, reason, queue, identity field, note reason and product type MUST be a value that appears in the tool API's enums. Copy them exactly. If the material names an outcome that is not in the API, put the closest API value and add the original wording to residual_rules.
- Dates as YYYY-MM-DD. Times as HH:MM. Numbers as numbers.
- Instruction strings are written for the phone agent, in the brief's language, short, imperative, and they keep every exact sentence the material prescribes (quote it).
- Where the material gives several documents (a mail, a policy, a memo that changes it, a code list), the LATEST or most specific rule wins; note superseded rules in residual_rules as "superseded: ...".
- residual_rules must contain EVERY rule of the material that the other fields do not capture, so that nothing is lost. When in doubt, put it in residual_rules too.
- Fields described as 'exact spoken' hold the words the agent says, never an instruction about them. If the material prescribes the content but not the words, write natural spoken words that carry exactly that content.
- Do not invent rules that are not in the material. Do not copy rules from any other bank or brief you may know.
"""


def user_prompt(briefs: list[tuple[str, str]], openapi: dict) -> str:
    enums = {}
    for path, item in openapi.get("paths", {}).items():
        body = (((item.get("post") or {}).get("requestBody") or {}).get("content") or {}).get("application/json", {}).get("schema", {})
        for name, prop in (body.get("properties") or {}).items():
            if "enum" in prop:
                enums[f"{path.strip('/')}.{name}"] = prop["enum"]
            if prop.get("type") == "array" and "items" in prop:
                for n2, p2 in (prop["items"].get("properties") or {}).items():
                    if "enum" in p2:
                        enums[f"{path.strip('/')}.{name}[].{n2}"] = p2["enum"]
        resp = ((((item.get("post") or {}).get("responses") or {}).get("200") or {}).get("content") or {}).get("application/json", {}).get("schema", {})
        for name, prop in (resp.get("properties") or {}).items():
            if "enum" in prop:
                enums[f"{path.strip('/')} response.{name}"] = prop["enum"]
            if prop.get("type") == "array" and "items" in prop:
                for n2, p2 in (prop["items"].get("properties") or {}).items():
                    if "enum" in p2:
                        enums[f"{path.strip('/')} response.{name}[].{n2}"] = p2["enum"]
    parts = ["# Schema to fill\n", SCHEMA, "\n\n# Tool API enums (the only allowed values)\n", json.dumps(enums, indent=1),
             "\n\n# Tool API (full)\n", json.dumps(openapi, indent=1)]
    for name, text in briefs:
        parts += [f"\n\n# Material: {name}\n", text]
    parts.append("\n\nNow answer with the filled JSON object.")
    return "".join(parts)


def validate(spec: dict, openapi: dict) -> list[str]:
    """Cheap structural checks. Returns a list of problems (empty = fine)."""
    problems = []
    need = ["opening", "third_party", "identity", "debt_statement", "calendar", "bands", "amounts", "persuasion", "special_cases", "confirm_record", "multi_product", "closing", "residual_rules"]
    for k in need:
        if k not in spec:
            problems.append(f"missing key {k}")
    enums = {}
    for path, item in openapi.get("paths", {}).items():
        body = (((item.get("post") or {}).get("requestBody") or {}).get("content") or {}).get("application/json", {}).get("schema", {})
        for name, prop in (body.get("properties") or {}).items():
            if "enum" in prop:
                enums[(path.strip("/"), name)] = set(prop["enum"])
    outcomes = enums.get(("close_call", "outcome"), set())

    def check_outcome(o, where):
        if not isinstance(o, dict):
            problems.append(f"{where}: outcome must be an object"); return
        if o.get("outcome") and outcomes and o["outcome"] not in outcomes:
            problems.append(f"{where}: outcome '{o['outcome']}' not in API enum {sorted(outcomes)}")

    for q in (spec.get("identity") or {}).get("questions") or []:
        f = enums.get(("verify_identity", "field"))
        if f and q.get("field") not in f:
            problems.append(f"identity question field '{q.get('field')}' not in API enum {sorted(f)}")
    if not (spec.get("identity") or {}).get("questions"):
        problems.append("identity.questions is empty")
    if not spec.get("bands"):
        problems.append("bands is empty")
    for b in spec.get("bands") or []:
        for k in ("days_late_min", "days_late_max", "deadline_business_days_after_today", "persuasion_attempts"):
            if not isinstance(b.get(k), (int, float)):
                problems.append(f"band {b.get('name')}: {k} must be a number")
    for h in (spec.get("calendar") or {}).get("holidays") or []:
        if not isinstance(h, str) or len(h) != 10:
            problems.append(f"holiday '{h}' is not YYYY-MM-DD")
    check_outcome((spec.get("persuasion") or {}).get("exhausted_outcome", {}), "persuasion.exhausted_outcome")
    check_outcome((spec.get("identity") or {}).get("fail", {}).get("outcome", {}), "identity.fail")
    check_outcome((spec.get("confirm_record") or {}).get("failure_outcome", {}), "confirm_record.failure_outcome")
    return problems


def extract(llm, briefs: list[tuple[str, str]], openapi: dict) -> dict:
    spec = llm.ask_json("read the brief(s) and the tool API, fill the policy spec", SYSTEM, user_prompt(briefs, openapi), retries=1)
    problems = validate(spec, openapi)
    if problems:
        fix = ("The spec you produced has these problems:\n- " + "\n- ".join(problems) +
               "\nReturn the corrected full JSON object. Keep everything else unchanged.\n\nYour spec was:\n" + json.dumps(spec, indent=1))
        spec = llm.ask_json("fix spec problems: " + "; ".join(problems)[:200], SYSTEM, user_prompt(briefs, openapi) + "\n\n" + fix, retries=1)
        problems = validate(spec, openapi)
        if problems:
            raise RuntimeError("spec still invalid: " + "; ".join(problems))
    return spec


if __name__ == "__main__":
    import sys
    from llm import LLM
    files = sys.argv[1:]
    api = [f for f in files if f.endswith(".json")]
    md = [f for f in files if not f.endswith(".json")]
    openapi = json.load(open(api[0]))
    spec = extract(LLM(), [(pathlib.Path(f).name, open(f).read()) for f in md], openapi)
    out = pathlib.Path("out") / (pathlib.Path(md[-1]).stem + ".spec.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    print("spec written:", out)
