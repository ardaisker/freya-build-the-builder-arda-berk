"""The builder's second road: a case folder that is not a collection call with the kit's tool API.

    python3 builder/build.py <case folder> --tool-url https://the-services.example

Steps: read every file -> case spec (model) -> audit (model) -> check every service with the material's test data ->
compile (code) -> lint -> validate + save on Freya -> smoke -> play the material's test conversations -> judge and
revise the spec (model) -> republish and replay -> keep the better version -> export. Every step is traced."""
from __future__ import annotations

import json
import os
import pathlib
import time

from casefolder import as_prompt, read_case
from casespec import audit_case, extract_case, revise_case, validate
from casecompile import compile_case
from casetest import check_tools, run_scenarios
from lint import lint


def compile_safely(spec, base_url, log):
    """A workflow from the spec, whatever the model wrote: optional parts are dropped one by one until it compiles and lints."""
    steps = [
        ("as written", lambda s: s),
        ("without the service calls at call start", lambda s: {**s, "tools": [{**t, "at_start": False} for t in s.get("tools") or [] if isinstance(t, dict)]}),
        ("without service calls at the endings", lambda s: {**s, "endings": [{**e, "before_tool": ""} for e in s.get("endings") or [] if isinstance(e, dict)]}),
        ("without result rules", lambda s: {**s, "tools": [{**t, "result_rules": [], "at_start": False} for t in s.get("tools") or [] if isinstance(t, dict)]}),
    ]
    cur, last = spec, None
    for label, change in steps:
        try:
            cur = change(cur)
            wf = compile_case(cur, base_url)
            problems = lint(wf)
            if problems:
                raise RuntimeError("lint: " + "; ".join(problems[:5]))
            if label != "as written":
                log(f"WARNING: the spec compiled only {label}")
            return wf, cur
        except Exception as e:
            last = e
            log(f"compile failed ({label}): {type(e).__name__}: {str(e)[:300]}")
    raise RuntimeError(f"the case spec could not be compiled: {last}")


def build_case(a, paths, trace, llm, ROOT, slot, deadline):
    base_url = (a.tool_url or os.environ.get("CASE_TOOL_URL") or "").strip()
    out_dir = ROOT / "out" / slot
    out_dir.mkdir(parents=True, exist_ok=True)
    left = lambda: (deadline - time.time()) / 60   # noqa: E731

    trace.section("1 READ: the case folder")
    material = read_case(paths)
    for rel, text in material:
        trace.log(f"  read {len(text):>7} chars  {rel}")
    text = as_prompt(material)
    trace.log(f"{len(material)} files, {len(text)} characters; services at {base_url or '(no address given: service checks and tests are skipped)'}")

    trace.section("2 CASE SPEC: material -> services, procedure, sentences, endings")
    if a.spec:
        spec = json.load(open(a.spec))
        trace.log(f"spec loaded from {a.spec} (no model call)")
    else:
        spec = extract_case(llm, text, base_url, log=trace.log)
        can_test = bool(base_url) and bool(spec.get("scenarios")) and not a.no_freya and int(a.max_test_rounds) > 0
        if not a.no_audit and not can_test:
            # with test conversations the second reading happens together with the judging of the tests (step 6b)
            trace.section("2b AUDIT: a second reading of the material against the spec")
            spec = audit_case(llm, spec, text, base_url, log=trace.log)
    for d in spec.get("decisions") or []:
        trace.log("decision on a contradiction: " + json.dumps(d, ensure_ascii=False)[:500])
    for o in spec.get("open_points") or []:
        trace.log("left open by the material: " + str(o)[:300])
    for pr in validate(spec):
        trace.log("spec warning: " + pr)
    (out_dir / "spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    trace.log(f"spec written: {out_dir / 'spec.json'}  language={spec.get('language')} services={len(spec.get('tools') or [])} steps={len(spec.get('procedure') or [])} rules={len(spec.get('rules') or [])} endings={len(spec.get('endings') or [])} test conversations={len(spec.get('scenarios') or [])}")

    tool_rows = []
    if base_url:
        trace.section("3 SERVICE CHECK: every service called with the material's test data")
        tool_rows, bad = check_tools(spec, base_url, trace.log)
        trace.test("service checks", f"{len(tool_rows) - len(bad)} / {len(tool_rows)} as the material says")
        if bad and not a.spec and left() > 14:
            trace.section("3b REVISE: service mismatches -> spec")
            new, _ = revise_case(llm, spec, text, base_url, tool_rows, [], log=trace.log)
            if new is not spec:
                rows2, bad2 = check_tools(new, base_url, trace.log)
                trace.test("service checks after the revision", f"{len(rows2) - len(bad2)} / {len(rows2)}")
                if len(bad2) <= len(bad):
                    spec, tool_rows = new, rows2
                    (out_dir / "spec-v2.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False))

    def publish(s, tag):
        trace.section(f"4 COMPILE ({tag}): spec -> workflow")
        wf, used = compile_safely(s, base_url, trace.log)
        n_tools = sum(len(n.get("tools", [])) + len(n.get("pre_actions", [])) for n in wf["nodes"].values())
        trace.log(f"workflow: {len(wf['nodes'])} nodes ({', '.join(wf['nodes'])}), {n_tools} tool slots, lint clean")
        (out_dir / f"workflow-{tag}.json").write_text(json.dumps(wf, indent=1, ensure_ascii=False))
        if a.no_freya:
            return wf, None
        import freya
        r = freya.validate_workflow(slot, wf)
        trace.log(f"dry-run: {r}")
        state_file = os.environ.get("FREYA_STATE_FILE") or str(ROOT / ".freya-agents.json")
        saved = freya.save_workflow(slot, wf, state_file=state_file)
        trace.created("workflow", workflow_id=saved["workflow_id"], agent_id=saved["agent_id"], version=saved.get("version", 1), nodes=len(wf["nodes"]))
        json.dump(saved, open(out_dir / "ids.json", "w"))
        return wf, saved

    if not a.no_freya:
        import resilient
        resilient.install(log=trace.log)
        resilient.install_watchdog(log=trace.log)
    wf, saved = publish(spec, "v1")
    if a.no_freya:
        trace.end("offline-ok"); return
    import freya

    trace.section("5 SMOKE: one chat turn")
    try:
        r = freya.api("POST", "/api/v2/chat/message", {"workflowId": saved["workflow_id"], "message": "?", "customerVariables": dict(wf.get("test_variables") or {})})
        trace.test("smoke chat turn", "ok: " + str(r.get("response"))[:200].replace("\n", " "))
        try:
            freya.api("POST", "/api/v2/chat/end", {"callId": r.get("callId")})
        except Exception:
            pass
    except Exception as e:
        trace.test("smoke chat turn", "FAILED: " + str(e)[:300])

    # 6. the material's test conversations are played against the agent; the builder's model judges them, reads the
    #    material a second time and edits the spec; the edited version is published and replayed; the better one stays
    best = {"spec": spec, "passed": -1, "total": 0, "tag": "v1"}
    current, tag = spec, "v1"
    rounds = max(0, int(a.max_test_rounds))
    for rnd in range(1, rounds + 1):
        if not base_url or not (current.get("scenarios") or []):
            trace.log("no test conversations to play"); break
        if left() < 3.5:
            trace.log(f"test round {rnd} skipped: {left():.1f} min left"); break
        trace.section(f"6 TEST round {rnd}: the material's test conversations against the agent ({tag})")
        try:
            conv = run_scenarios(saved["agent_id"], current, trace.log, ROOT / ".personas-case.json", max_seconds=240)
        except Exception as e:
            trace.test(f"round {rnd}", "FAILED to run: " + str(e)[:300]); break
        (out_dir / f"test-{rnd}.json").write_text(json.dumps(conv, indent=1, ensure_ascii=False))
        passed = sum(1 for c in conv if c.get("platform_verdict") == "pass")
        trace.test(f"round {rnd}", f"{passed} / {len(conv)} test conversations passed the platform judge for version {tag}")
        if passed >= best["passed"]:            # a tie goes to the later version: it carries the second reading's corrections
            best = {"spec": current, "passed": passed, "total": len(conv), "tag": tag}
        else:
            trace.log(f"version {tag} did worse than {best['tag']} ({passed} < {best['passed']}): going back")
            break
        if a.spec or rnd == rounds or passed == len(conv) and rnd > 1:
            break
        if left() < 9:
            trace.log(f"no time for a revision ({left():.1f} min left)"); break
        trace.section(f"6b JUDGE + SECOND READING + REVISE round {rnd}")
        new, verdicts = revise_case(llm, current, text, base_url, tool_rows, conv, log=trace.log)
        if verdicts:
            trace.test(f"round {rnd}, builder's own verdicts", f"{sum(1 for v in verdicts if isinstance(v, dict) and v.get('pass') is True)} / {len(verdicts)} for version {tag}")
        if new is current:
            trace.log("the revision changed nothing"); break
        if left() < 1.5:
            trace.log("no time to publish the revision"); break
        current, tag = new, f"v{rnd + 1}"
        (out_dir / f"spec-{tag}.json").write_text(json.dumps(current, indent=1, ensure_ascii=False))
        if base_url:
            rows2, bad2 = check_tools(current, base_url, lambda line: None)
            trace.test(f"service checks for {tag}", f"{len(rows2) - len(bad2)} / {len(rows2)} as the material says")
            tool_rows = rows2
        wf, saved = publish(current, tag)
        if rnd + 1 > rounds or left() < 3.5:      # published but not replayed: it still carries the corrections of the second reading
            best = {"spec": current, "passed": best["passed"], "total": best["total"], "tag": tag + " (not replayed)"}
    if best["spec"] is not current:
        trace.log(f"version {best['tag']} stays ({best['passed']} / {best['total']}): republishing it")
        wf, saved = publish(best["spec"], "best")
    (out_dir / "spec-final.json").write_text(json.dumps(best["spec"], indent=1, ensure_ascii=False))

    trace.section("7 EXPORT")
    sub = ROOT / "submission"; sub.mkdir(exist_ok=True)
    path = freya.export_workflow(saved["workflow_id"], str(sub / f"{slot}.workflow.json"))
    trace.log(f"exported {path}")
    trace.log(f"RESULT workflow_id={saved['workflow_id']} agent_id={saved['agent_id']} best_passed={best['passed']} of {best['total']}")
    trace.end("ok")
