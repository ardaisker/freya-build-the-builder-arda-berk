"""Run OUR edge cases against an agent. Same scorer and judge as the kit, but each case opens a practice session
on a base public customer (`base`) and brings its own script, expected ledger and checks.

    python3 builder/run_custom.py <agent_id> --cases fixtures/edge-cases.json [--only E01,E02] [--reps 2] [--style talkative] [--out results/x.json]
"""
import argparse, hashlib, json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "builder"))
import freya
from score import http as _http, score_ledger
from run_cases import persona_for, STYLES


def http(path, body=None, tries=4):
    """The mock bank occasionally answers with an HTML error page; retry a few times before giving up."""
    for i in range(tries):
        try:
            return _http(path, body)
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"mock bank error on {path} ({type(e).__name__}), retrying in 15 s", flush=True); time.sleep(15)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("agent_id"); ap.add_argument("--cases", default=str(ROOT / "fixtures" / "edge-cases.json")); ap.add_argument("--only"); ap.add_argument("--reps", type=int, default=1); ap.add_argument("--style", choices=sorted(STYLES)); ap.add_argument("--out")
    a = ap.parse_args()
    cases = [c for c in json.load(open(a.cases)) if not a.only or c["id"] in a.only.split(",")]
    store = ROOT / ".personas-custom.json"; ids = json.load(open(store)) if store.exists() else {}
    spec = {c["id"]: persona_for(c, {"identity": c["identity"]}, a.style) for c in cases}
    key = {i: i + ":" + hashlib.sha1(json.dumps(p, sort_keys=True).encode()).hexdigest()[:10] for i, p in spec.items()}
    new = [c for c in cases if key[c["id"]] not in ids]
    if new:
        made = freya.create_personas([spec[c["id"]] for c in new])["personas"]
        ids.update({key[c["id"]]: p["id"] for c, p in zip(new, made)}); json.dump(ids, open(store, "w"), indent=1)
    ids = {c["id"]: ids[key[c["id"]]] for c in cases}
    import credits
    if not credits.allow(len(cases) * a.reps, f"{len(cases)} cases x {a.reps}"):
        sys.exit(2)
    reps, total_s = [], 0
    for rep in range(a.reps):
        rows, sim_id, took = run_once(a.agent_id, cases, ids)
        reps.append(rows); total_s += took
        if a.reps > 1: print(f"-- run {rep + 1} of {a.reps}: {sum(r['pass'] for r in rows)} / {len(rows)} passed, {took:.0f} s\n")
    final = [{"id": c["id"], "family": c["family"], "passes": sum(r[k]["pass"] for r in reps), "runs": a.reps, "pass": all(r[k]["pass"] for r in reps)} for k, c in enumerate(cases)]
    n = sum(f["pass"] for f in final)
    if a.reps > 1:
        for f in final: print(("PASS" if f["pass"] else "FAIL"), f["id"], f"{f['passes']}/{f['runs']}")
    print(f"\n{n} / {len(final)} passed. Last simulation {sim_id}, {total_s:.0f} s.")
    (ROOT / "results").mkdir(exist_ok=True)
    with open(ROOT / "results" / "log-custom.jsonl", "a") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "agent_id": a.agent_id, "style": a.style, "runs": a.reps, "passed": n, "total": len(final), "failed": [x["id"] for x in final if not x["pass"]]}) + "\n")
    if a.out:
        json.dump({"agent_id": a.agent_id, "passed": n, "total": len(final), "final": final, "rows": reps[-1], "all_rows": reps}, open(a.out, "w"), indent=1)


def run_once(agent_id, cases, ids):
    sessions = {c["id"]: http("/v1/practice/sessions", {"case": c["base"]})["variables"] for c in cases}
    t0 = time.time()
    sim_id, it_id, status = freya.run_simulation(agent_id, f"edge {time.strftime('%H:%M:%S')}", {ids[c["id"]]: sessions[c["id"]] for c in cases})
    took = time.time() - t0
    judge = {r["personaId"]: r for r in freya.get_iteration(sim_id, it_id)["runs"]}
    rows = []
    for c in cases:
        led = http("/v1/practice/ledger/" + sessions[c["id"]]["customer_id"])
        r = score_ledger(c, led)
        j = judge.get(ids[c["id"]], {})
        if j.get("outcome") != "pass": r["failed"].append("conversation: " + " ".join(str(j.get("reason") or "no verdict").split())[:400])
        r["pass"] = not r["failed"]
        rows.append({"id": c["id"], "family": c["family"], "pass": r["pass"], "failed": r["failed"], "call_id": j.get("callId"), "tools": [x["tool"] for x in led["calls"]], "customer_id": sessions[c["id"]]["customer_id"]})
        print(("PASS" if r["pass"] else "FAIL"), c["id"], f"{c['family']:<14}", c["title"][:40].ljust(40), "|", " > ".join(x["tool"].replace("verify_identity", "verify").replace("create_promise", "promise") for x in led["calls"]) or "(no tool calls)")
        for f in r["failed"]: print("       -", f[:260])
    return rows, sim_id, took


if __name__ == "__main__": main()
