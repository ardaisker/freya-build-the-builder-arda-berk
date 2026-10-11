"""The builder. One command, a brief (or two) and a tool API file in, a phone agent on Freya out.

    python3 builder/build.py briefs/brief-a.md tools/openapi.json
    python3 builder/build.py briefs/brief-a.md briefs/brief-b.md tools/openapi.json --cases public-test-set.json --brief B

Steps: extract (model) -> compile (code) -> lint -> dry-run validate -> save/publish -> smoke (chat) -> test (practice
cases, if given, within the time budget) -> patch the spec from failures (model, bounded) -> export. Every step is traced.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import tempfile
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))

from trace import Trace  # noqa: E402
from llm import LLM  # noqa: E402
from extract import audit, extract, validate  # noqa: E402
from compile import compile_workflow  # noqa: E402
from lint import lint  # noqa: E402
from patch import patch_spec  # noqa: E402
from fallback import compile_with_fallback  # noqa: E402


def yaml_to_json(path):
    """Write a JSON copy of a YAML tool API next to the outputs and return its path (installs PyYAML if needed)."""
    try:
        import yaml
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pyyaml"], check=False)
        import yaml
    out = pathlib.Path(tempfile.gettempdir()) / (pathlib.Path(path).stem + ".from-yaml.json")
    out.write_text(json.dumps(yaml.safe_load(pathlib.Path(path).read_text(errors="replace")), indent=1, default=str))
    return str(out)


def classify(paths):
    """Sort the command-line paths into brief texts and the tool API file. A folder is read file by file.
    The tool API is the file that parses as an OpenAPI document, whatever its name."""
    files = []
    for p in paths:
        pp = pathlib.Path(p)
        if pp.is_dir():
            files += sorted(str(x) for x in pp.rglob("*") if x.is_file() and not x.name.startswith(".") and x.suffix.lower() in (".md", ".txt", ".json", ".eml", ".csv", ".yaml", ".yml", ""))
        else:
            files.append(str(pp))
    briefs, apis = [], []
    for f in files:
        is_api = False
        try:
            text = pathlib.Path(f).read_text(errors="replace")
            if f.lower().endswith((".yaml", ".yml")) and "paths:" in text and "openapi" in text:
                f = yaml_to_json(f)          # a YAML tool API is converted, never a manual step
                text = pathlib.Path(f).read_text(errors="replace")
            doc = json.loads(text)
            is_api = isinstance(doc, dict) and isinstance(doc.get("paths"), dict)
        except (ValueError, OSError):
            is_api = False
        (apis if is_api else briefs).append(f)
    return briefs, apis


def self_check(spec, openapi, wf, trace):
    """Run every code step of the phone agent locally on a made-up customer built from the tool API, so a step that
    cannot compute its facts is found before any call. Needs no network."""
    import apimap
    A = apimap.resolve(spec, openapi)
    g = A["tools"].get("get_account") or {}
    S = dict(spec, api=A)
    resp = apimap._resp(openapi, "get_account").get("properties") or {}
    items = ((resp.get(g.get("products", "products")) or {}).get("items") or {}).get("properties") or {}
    types = (items.get(g.get("type", "type")) or {}).get("enum") or ["product"]
    bands = spec.get("bands") or [{}]
    now = "2026-03-11T10:30"
    ok, total = 0, 0
    for i, ty in enumerate(types):
        for b in bands:
            p = {}
            for name, sch in items.items():
                p[name] = {"number": 100.0 + 10 * i, "integer": 1, "string": "1234", "boolean": True}.get(sch.get("type"), "x")
            p[g.get("product_id", "product_id")] = "p1"
            p[g.get("type", "type")] = ty
            p[g.get("past_due", "past_due")] = 900.0
            p[g.get("days_late", "days_late")] = int(b.get("days_late_min", 1) or 1)
            v = {A["call_vars"]["now"]: now, "get_account_response.data." + g.get("products", "products"): json.dumps([p])}
            total += 1
            try:
                from codegen import snippet
                exec(snippet("facts", libs=("calendar_lib", "dateparse_lib"), SPEC=S), {"vars": v})
                pf = json.loads(v.get("pf_json") or "[]")
                assert v.get("facts_state") == "ok" and pf and pf[0]["deadline"] and pf[0]["floor"] is not None, "facts not computed"
                v["customer_date_text"] = "tomorrow"
                exec(snippet("resolve_date", libs=("calendar_lib", "dateparse_lib"), SPEC=S), {"vars": v})
                assert v.get("date_status") in ("ok", "not_business", "after_deadline", "partly_after_deadline"), "date check failed"
                exec(snippet("finalize", libs=("calendar_lib", "dateparse_lib"), SPEC=S), {"vars": dict(v, promises_log="p1;")})
                ok += 1
            except Exception as e:
                trace.test(f"self-check {ty}/{b.get('name')}", "FAILED: " + str(e)[:200])
    v = {A["call_vars"]["now"]: now, "callback_day_text": "tomorrow", "callback_time_text": "3 pm"}
    try:
        from codegen import snippet
        exec(snippet("tp_resolve", libs=("calendar_lib", "dateparse_lib"), SPEC=S), {"vars": v})
        cb = v.get("tp_status")
    except Exception as e:
        cb = "error " + str(e)[:80]
    trace.test("self-check code steps", f"{ok} / {total} product type x band combinations computed deadline, floor, offers and outcome; callback check: {cb}")
    outs = set(A["outcomes"])
    used = set(re.findall(r"vars\['call_outcome'\] = '([^']*)'", json.dumps(wf).replace("\\'", "'")))
    bad = sorted(o for o in used if outs and o and o not in outs)
    trace.test("self-check outcomes", "every outcome the workflow can record is a value of the tool API" if not bad else "NOT in the tool API: " + ", ".join(bad))
    return ok == total and not bad


def fits_collection(api_path) -> bool:
    """True when the tool API file brings the tools the fixed collection topology is built on."""
    try:
        doc = json.load(open(api_path))
        names = {p.strip("/").split("/")[-1] for p in (doc.get("paths") or {})}
        return {"verify_identity", "get_account", "create_promise", "close_call"} <= names
    except Exception:
        return False


def slug(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", pathlib.Path(path).stem.lower()).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="brief .md file(s) and one tool API .json")
    ap.add_argument("--cases", default="", help="practice cases JSON to test against (optional)")
    ap.add_argument("--brief", default="", help="restrict practice cases to this brief letter (A/B)")
    ap.add_argument("--spec", default="", help="use this spec JSON instead of calling the model")
    ap.add_argument("--max-test-rounds", type=int, default=int(os.environ.get("BUILDER_TEST_ROUNDS", "2")))
    ap.add_argument("--budget-min", type=float, default=27.0, help="hard stop for the whole run, minutes")
    ap.add_argument("--slot", default="")
    ap.add_argument("--no-freya", action="store_true", help="stop after lint (offline)")
    ap.add_argument("--no-audit", action="store_true", help="skip the second model pass that checks the spec against the brief")
    ap.add_argument("--no-oracle", action="store_true", help="skip the independent test situations that check the code steps against the brief")
    ap.add_argument("--tool-url", default="", help="base address of the case's services, for a case folder that brings no tool API file of the collection kind")
    a = ap.parse_args()
    t_start = time.time()
    deadline = t_start + a.budget_min * 60

    briefs, apis = classify(a.files)
    if a.tool_url or len(apis) != 1 or not fits_collection(apis[0]):
        # not a collection call with the kit's tool API: the case-folder road reads everything and builds from that
        from casebuild import build_case
        slot = a.slot or ("team-" + "-".join(slug(f) for f in a.files))[:60]
        trace = Trace(ROOT / "traces" / f"{slot}-{time.strftime('%Y%m%d-%H%M%S')}.log")
        trace.section(f"BUILD START (case folder) slot={slot} input={a.files} budget={a.budget_min}min")
        trace.log("command: " + " ".join(sys.argv))
        llm = LLM(trace=trace)
        trace.log(f"model backend={llm.backend} model={llm.model}")
        return build_case(a, a.files, trace, llm, ROOT, slot, deadline)
    if not briefs:
        sys.exit("give the brief (one or more text files, or a folder of them) and exactly one tool API file")
    slot = a.slot or ("team-" + "-".join(slug(b) for b in briefs))[:60]   # own prefix: never the kit example's slot
    out_dir = ROOT / "out" / slot
    out_dir.mkdir(parents=True, exist_ok=True)
    trace = Trace(ROOT / "traces" / f"{slot}-{time.strftime('%Y%m%d-%H%M%S')}.log")
    trace.section(f"BUILD START slot={slot} briefs={briefs} api={apis[0]} budget={a.budget_min}min")
    trace.log("command: " + " ".join(sys.argv))
    openapi = json.load(open(apis[0]))
    llm = LLM(trace=trace)
    trace.log(f"model backend={llm.backend} model={llm.model}")

    # 1. extract
    trace.section("1 EXTRACT: brief -> policy spec")
    if a.spec:
        spec = json.load(open(a.spec))
        trace.log(f"spec loaded from {a.spec} (no model call)")
    else:
        material = [(pathlib.Path(b).name, pathlib.Path(b).read_text(errors="replace")) for b in briefs]
        spec = extract(llm, material, openapi)
        if not a.no_audit:
            trace.section("1b AUDIT: spec checked against the material")
            spec = audit(llm, spec, material, openapi, log=trace.log)
        if not a.no_oracle:
            trace.section("1c ORACLE: independent test situations from the material, run on the code steps")
            import oracle
            spec, summary = oracle.check(llm, spec, material, openapi, log=trace.log)
            trace.test("oracle (local, no Freya)", summary)
    (out_dir / "spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    trace.log(f"spec written: {out_dir / 'spec.json'}  identity questions={len(spec.get('identity', {}).get('questions', []))} bands={len(spec.get('bands', []))} holidays={len(spec.get('calendar', {}).get('holidays', []))} special_cases={len(spec.get('special_cases', []))} residual_rules={len(spec.get('residual_rules', []))} multi_product={spec.get('multi_product', {}).get('enabled')}")
    # rules the code steps cannot compute stay in the bank's words for the phone agent; say so in the trace
    in_words = []
    for b in spec.get("bands") or []:
        r = b.get("deadline_rule") if isinstance(b, dict) else None
        if isinstance(r, dict) and r.get("type") == "text":
            in_words.append(f"latest payment date of band {b.get('name')}")
    for at in (spec.get("persuasion") or {}).get("attempts") or []:
        r = at.get("date_rule") if isinstance(at, dict) else None
        if isinstance(r, dict) and r.get("type") == "text":
            in_words.append(f"date of persuasion attempt {at.get('n')}")
    if (spec.get("amounts") or {}).get("floor_rule_text"):
        in_words.append("lowest acceptable amount (if no computable form applies)")
    trace.log("rules computed in code: all" if not in_words else "rules left in the bank's words for the phone agent (not computed in code): " + "; ".join(in_words))

    # 2. compile + lint
    built_with = {}

    def compile_checked(s):
        wf = compile_workflow(s, openapi)
        problems = lint(wf)
        if problems:
            raise RuntimeError("lint failed: " + "; ".join(problems[:5]))
        return wf

    def build_and_check(spec, tag):
        trace.section(f"2 COMPILE ({tag}): spec -> workflow")
        wf, used, level = compile_with_fallback(spec, compile_checked, log=trace.log)
        if level:
            trace.log(f"WARNING: the spec did not compile; built at fallback level {level} (optional sections kept as prompt rules only)")
        built_with["spec"] = used
        problems = lint(wf)
        n_tools = sum(len(n.get("tools", [])) + len(n.get("pre_actions", [])) for n in wf["nodes"].values()) + len(wf.get("tools", []))
        trace.log(f"workflow: {len(wf['nodes'])} nodes, {n_tools} tools, lint problems={len(problems)}")
        for pr in problems:
            trace.log("  lint: " + pr)
        (out_dir / f"workflow-{tag}.json").write_text(json.dumps(wf, indent=1, ensure_ascii=False))
        return wf

    wf = build_and_check(spec, "v1")
    trace.section("2b SELF-CHECK: code steps run locally on made-up customers")
    self_check(built_with["spec"], openapi, wf, trace)
    if a.no_freya:
        trace.end("offline-ok"); return

    import freya  # noqa: E402  (needs FREYA_API_KEY)
    import resilient
    resilient.install(log=trace.log)
    resilient.install_watchdog(log=trace.log)
    trace.section("3 VALIDATE + SAVE on Freya")
    r = freya.validate_workflow(slot, wf)
    trace.log(f"dry-run: {r}")
    state_file = os.environ.get("FREYA_STATE_FILE") or str(ROOT / ".freya-agents.json")   # parallel runs keep separate state files
    saved = freya.save_workflow(slot, wf, state_file=state_file)
    trace.created("workflow", workflow_id=saved["workflow_id"], agent_id=saved["agent_id"], version=saved.get("version", 1), nodes=len(wf["nodes"]))
    json.dump(saved, open(out_dir / "ids.json", "w"))

    # 4. smoke: one chat turn proves the workflow can start a call
    trace.section("4 SMOKE: one chat turn")
    try:
        cv = dict(wf.get("test_variables") or {})
        r = freya.api("POST", "/api/v2/chat/message", {"workflowId": saved["workflow_id"], "message": "Hello?", "customerVariables": cv})
        trace.test("smoke chat turn", "ok: " + str(r.get("response"))[:160].replace("\n", " "))
        try:
            freya.api("POST", "/api/v2/chat/end", {"callId": r.get("callId")})
        except Exception:
            pass
    except Exception as e:
        trace.test("smoke chat turn", "FAILED: " + str(e)[:300])

    # 5. test + patch rounds
    best = {"passed": -1, "version": saved.get("version", 1), "spec": spec}
    if a.cases:
        for rnd in range(1, a.max_test_rounds + 1):
            left = (deadline - time.time()) / 60
            if left < 9:
                trace.log(f"test round {rnd} skipped: only {left:.1f} min left in the budget"); break
            trace.section(f"5 TEST round {rnd}: practice cases")
            res = run_cases(saved["agent_id"], a.cases, a.brief, out_dir / f"test-{rnd}.json", trace, timeout=min(900, max(60, int((deadline - time.time()) - 120))))
            if res is None:
                break
            trace.test(f"round {rnd}", f"{res['passed']} / {res['total']} passed in {res['seconds']} s; failed: {[r['id'] for r in res['rows'] if not r['pass']]}")
            if res["passed"] > best["passed"]:
                best = {"passed": res["passed"], "version": saved.get("version", 1), "spec": spec}
            if res["passed"] == res["total"] or rnd == a.max_test_rounds:
                break
            if (deadline - time.time()) / 60 < 12:
                trace.log("no time for a patch round"); break
            trace.section(f"6 PATCH round {rnd}: failures -> spec")
            failures = collect_failures(res, trace)
            new_spec = patch_spec(llm, spec, failures, briefs_text=[(pathlib.Path(b).name, pathlib.Path(b).read_text(errors="replace")) for b in briefs], openapi=openapi)
            problems = validate(new_spec, openapi)
            if problems:
                trace.log("patched spec rejected: " + "; ".join(problems)); break
            spec = new_spec
            (out_dir / f"spec-v{rnd + 1}.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False))
            wf = build_and_check(spec, f"v{rnd + 1}")
            saved = freya.save_workflow(slot, wf, state_file=state_file)
            trace.created("workflow version", workflow_id=saved["workflow_id"], agent_id=saved["agent_id"], version=saved.get("version"), nodes=len(wf["nodes"]))
        if best["passed"] >= 0 and best["spec"] is not spec and best["passed"] > -1:
            # the last patch did not beat the best version: republish the best spec
            last = res["passed"] if res else -1
            if last < best["passed"]:
                trace.log(f"last version scored {last} < best {best['passed']}: republishing the best spec")
                wf = build_and_check(best["spec"], "best")
                saved = freya.save_workflow(slot, wf, state_file=state_file)
                trace.created("workflow version (best)", workflow_id=saved["workflow_id"], agent_id=saved["agent_id"], version=saved.get("version"))

    # 7. export
    trace.section("7 EXPORT")
    sub = ROOT / "submission"; sub.mkdir(exist_ok=True)
    path = freya.export_workflow(saved["workflow_id"], str(sub / f"{slot}.workflow.json"))
    trace.log(f"exported {path}")
    trace.log(f"RESULT workflow_id={saved['workflow_id']} agent_id={saved['agent_id']} best_passed={best['passed']}")
    trace.end("ok")


def run_cases(agent_id, cases, brief, out_json, trace, timeout):
    cmd = [sys.executable, str(ROOT / "tools" / "run_cases.py"), agent_id, "--cases", cases, "--out", str(out_json)]
    if brief:
        cmd += ["--brief", brief]
    trace.log("running: " + " ".join(cmd[1:]))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        trace.test("practice cases", "TIMEOUT"); return None
    for line in (p.stdout or "").splitlines():
        if line.startswith(("PASS", "FAIL")) or "passed" in line or "slowest" in line:
            trace.log("  " + line[:220])
    if p.returncode != 0 or not pathlib.Path(out_json).exists():
        trace.test("practice cases", "FAILED to run: " + (p.stderr or p.stdout)[-400:]); return None
    return json.load(open(out_json))


def collect_failures(res, trace):
    import freya
    out = []
    for row in res["rows"]:
        if row["pass"]:
            continue
        item = {"id": row["id"], "family": row["family"], "failed": row["failed"], "tools": row["tools"], "transcript": ""}
        if row.get("call_id"):
            try:
                call = freya.get_call(row["call_id"])
                lines = []
                for m in call.get("messages", []):
                    if m.get("role") in ("user", "assistant"):
                        lines.append(f"{m['role'].upper()} [{m.get('nodeId', '')}]: {m['message']}")
                    elif m.get("role") == "system":
                        try:
                            ev = json.loads(m["message"])
                            if ev.get("event") == "function_call_start":
                                lines.append(f"  TOOL {ev.get('function')} {json.dumps(ev.get('args', {}).get('body', ''))[:160]}")
                            elif ev.get("event") == "function_call_complete":
                                lines.append(f"  RESULT {ev.get('function')} {json.dumps(ev.get('result', {}).get('data', ''))[:200]}")
                        except Exception:
                            pass
                item["transcript"] = "\n".join(lines)[:6000]
            except Exception as e:
                item["transcript"] = "(transcript unavailable: " + str(e)[:100] + ")"
        out.append(item)
    trace.log(f"collected {len(out)} failed transcripts for the patch step")
    return out


if __name__ == "__main__":
    main()
