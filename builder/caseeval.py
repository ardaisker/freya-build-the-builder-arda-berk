"""Play a file of test conversations against a published agent and print the platform judge's verdicts.
The file has the shape of a case spec's test part: {"language", "call_variables": [...], "scenarios": [...]}.

    python3 builder/caseeval.py <agent_id> <scenarios.json> [--only name-prefix,name-prefix] [--out results/x.json]
"""
import argparse, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))
from casetest import run_scenarios  # noqa: E402


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("agent_id"); ap.add_argument("scenarios"); ap.add_argument("--only", default=""); ap.add_argument("--out", default="")
    a = ap.parse_args()
    import resilient
    resilient.install(); resilient.install_watchdog()
    spec = json.load(open(a.scenarios))
    if a.only:
        keep = tuple(x.strip() for x in a.only.split(","))
        spec["scenarios"] = [s for s in spec["scenarios"] if str(s.get("name", "")).startswith(keep)]
    rows = run_scenarios(a.agent_id, spec, lambda line: None, ROOT / ".personas-case.json", max_seconds=300, limit=60)
    for r in rows:
        print(("PASS " if r["platform_verdict"] == "pass" else "FAIL ") + str(r["name"])[:60].ljust(60) + ("" if r["platform_verdict"] == "pass" else " | " + r["platform_reason"][:240]))
    n = sum(1 for r in rows if r["platform_verdict"] == "pass")
    print(f"\n{n} / {len(rows)} passed")
    if a.out:
        pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        json.dump({"agent_id": a.agent_id, "passed": n, "total": len(rows), "rows": rows}, open(a.out, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
