"""The kit's scorer (tools/run_cases.py) with our retries and credit guard around it. Same arguments.

    python3 builder/gate.py <agent_id> --brief A --reps 3 --out results/x.json
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "tools", ROOT / "builder"):
    sys.path.insert(0, str(p))
import credits, resilient

if __name__ == "__main__":
    a = sys.argv[1:]
    reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 1
    n = len(json.load(open(ROOT / "public-test-set.json")))
    if not credits.allow(n * reps, "the practice set"):
        sys.exit(2)
    resilient.install()
    resilient.install_watchdog()
    import run_cases
    run_cases.main()
