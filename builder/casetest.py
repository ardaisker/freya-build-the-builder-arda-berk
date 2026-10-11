"""The builder's own tests for a case-folder build: (1) every service call the workflow can make is tried against the
real address with the test inputs the material names; (2) the test conversations the material describes are played
against the published agent as a Freya text simulation, and their transcripts come back for judging."""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))

from casecompile import ident, run_tool_locally  # noqa: E402

PERSONA = """OUTPUT RULE: Write only the words you say on the phone, in {language}. No stage directions, no brackets. One or two short sentences per turn, then wait for the other side.

WHO YOU ARE AND WHAT HAPPENS IN THIS CALL: {script}

RULES:
- You are the caller. The other side is the phone assistant. Answer what you are asked and do not volunteer what nobody asked for.
- Do not invent facts that are not written above. If asked something that is not covered, give a short neutral answer.
- If the assistant reads something back and it matches what you want, confirm it.
- When the assistant says goodbye or hands you over, say a short goodbye and say nothing more."""


def check_tools(spec, base_url, log):
    """Try every test call of every service. Returns (rows, problems)."""
    call_vars = [str(v.get("name")) for v in spec.get("call_variables") or [] if isinstance(v, dict)]
    rows, problems = [], []
    examples = {str(v.get("name")): v.get("example") for v in spec.get("call_variables") or [] if isinstance(v, dict) and v.get("example") not in (None, "")}
    now = str(examples.get(str(spec.get("now_variable") or "")) or "")
    today = now[:10] if len(now) >= 10 else ""
    end_ids = [ident(e.get("id") or e.get("when"), "end") for e in spec.get("endings") or [] if isinstance(e, dict)]
    other = {}
    for t in spec.get("tools") or []:
        if not isinstance(t, dict) or not t.get("path"):
            continue
        for test in (t.get("tests") or [])[:8]:
            if not isinstance(test, dict):
                continue
            try:
                r = run_tool_locally(t, base_url, call_vars, test.get("args") or {}, examples=examples, today=today, endings=end_ids, other=other)
                if 200 <= int(r["status"]) < 300:           # later services may read this answer (rules with @service paths)
                    other[ident(t.get("name")) + "_json"] = json.dumps(r["raw"], ensure_ascii=False)
            except Exception as e:
                r = {"url": str(t.get("path")), "method": str(t.get("method")), "status": 0, "body": type(e).__name__ + ": " + str(e)[:200], "what_to_do_next": None, "raw": None}
            want = test.get("expect_status")
            ok = (want is None or int(want) == int(r["status"])) and r["status"] != 0
            contains = str(test.get("expect_contains") or "")
            if ok and contains and contains.lower() not in json.dumps(r["body"], ensure_ascii=False).lower():
                ok = False
            row = {"tool": ident(t.get("name")), "args": test.get("args") or {}, "method": r["method"], "url": r["url"], "status": r["status"], "expected_status": want,
                   "expected_contains": contains, "ok": ok, "body": json.dumps(r["body"], ensure_ascii=False)[:1500], "what_to_do_next": r["what_to_do_next"], "ends_call": r.get("go") or "", "spoken_at_end": r.get("say") or ""}
            rows.append(row)
            log(f"TEST service {row['tool']} {json.dumps(row['args'], ensure_ascii=False)[:120]} -> {row['status']} (expected {want}) {'ok' if ok else 'MISMATCH'}  " + (f"ENDS THE CALL ({row['ends_call']}): {row['spoken_at_end']}" if row["ends_call"] else "agent is told: " + str(row["what_to_do_next"]))[:420])
            if not ok:
                problems.append(row)
    return rows, problems


def transcript(call):
    lines = []
    for m in call.get("messages", []):
        role = m.get("role")
        if role in ("user", "assistant"):
            lines.append(("CALLER: " if role == "user" else "AGENT: ") + str(m.get("message")))
        elif role == "system":
            try:
                ev = json.loads(m["message"])
            except Exception:
                continue
            if ev.get("event") == "function_call_start":
                a = ev.get("args") or {}
                lines.append(f"  TOOL {ev.get('function')} " + json.dumps(a.get("body") if isinstance(a, dict) and "body" in a else a, ensure_ascii=False)[:300])
            elif ev.get("event") == "function_call_complete":
                res = ev.get("result") or {}
                lines.append(f"  RESULT {ev.get('function')} " + json.dumps(res.get("data") if isinstance(res, dict) and "data" in res else res, ensure_ascii=False)[:900])
            elif ev.get("event") in ("error", "node_transition", "transition"):
                lines.append("  " + json.dumps(ev, ensure_ascii=False)[:200])
    return "\n".join(lines)


def run_scenarios(agent_id, spec, log, state_path, max_seconds=300, limit=12):
    """Play the spec's scenarios against the agent. Returns rows with the transcript and the platform judge's verdict."""
    import freya
    scenarios = [s for s in spec.get("scenarios") or [] if isinstance(s, dict) and s.get("customer")][:limit]
    if not scenarios:
        return []
    lang = str(spec.get("language") or "English")
    defaults = {str(v.get("name")): str(v.get("example") or "") for v in spec.get("call_variables") or [] if isinstance(v, dict) and v.get("name")}
    store = pathlib.Path(state_path)
    ids = json.loads(store.read_text()) if store.exists() else {}
    personas, keys = [], []
    for i, s in enumerate(scenarios):
        p = {"name": f"case test {i + 1}: {str(s.get('name') or '')[:60]}", "prompt": PERSONA.format(language=lang, script=str(s["customer"]).strip()),
             "successCriteria": "All of these are true:\n- " + "\n- ".join(str(x) for x in (s.get("expect") or ["The assistant followed its procedure."])), "tags": ["builder-test"]}
        personas.append(p)
        keys.append(hashlib.sha1(json.dumps(p, sort_keys=True).encode()).hexdigest()[:16])
    new = [(k, p) for k, p in zip(keys, personas) if k not in ids]
    if new:
        made = freya.create_personas([p for _, p in new])["personas"]
        for (k, _), m in zip(new, made):
            ids[k] = m["id"]
        store.write_text(json.dumps(ids, indent=1))
    by_persona = {ids[k]: {**defaults, **{str(a): str(b) for a, b in (s.get("variables") or {}).items()}} for k, s in zip(keys, scenarios)}
    t0 = time.time()
    sim_id, it_id, status = freya.run_simulation(agent_id, f"builder test {time.strftime('%H:%M:%S')}", by_persona, max_seconds=max_seconds)
    log(f"simulation {sim_id} status={status} {time.time() - t0:.0f}s for {len(scenarios)} test conversations")
    runs = {r["personaId"]: r for r in freya.get_iteration(sim_id, it_id)["runs"]}
    rows = []
    for k, s in zip(keys, scenarios):
        r = runs.get(ids[k], {})
        text = ""
        if r.get("callId"):
            try:
                text = transcript(freya.get_call(r["callId"]))
            except Exception as e:
                text = "(transcript unavailable: " + str(e)[:100] + ")"
        rows.append({"name": s.get("name"), "variables": by_persona[ids[k]], "expect": s.get("expect") or [], "platform_verdict": r.get("outcome"), "platform_reason": " ".join(str(r.get("reason") or "").split())[:600],
                     "call_id": r.get("callId"), "transcript": text})
        log(f"TEST conversation '{s.get('name')}': platform judge={r.get('outcome')}  {rows[-1]['platform_reason'][:200]}")
    return rows
