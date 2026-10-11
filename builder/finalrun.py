"""Several complete builder runs on one brief, side by side. The rules allow running the builder more than once and
submitting the phone agent of one run; this starts K runs in parallel (each is the plain one-command build with its
own slot, state file and trace) and prints what tells them apart, so the choice rests on evidence.

  python3 builder/finalrun.py --name hidden-1 --runs 3 briefs/hidden-1.md briefs/hidden-1.openapi.json [--offline]

It changes nothing in a run and nothing in an agent; it only starts runs and reads their output."""
from __future__ import annotations

import argparse, collections, json, os, pathlib, re, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent


def flat(o, p=""):
    """Leaves of the spec that drive computed behaviour: numbers, booleans, short strings (long strings are wording)."""
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            if not str(k).startswith("_"):
                out.update(flat(v, p + "." + str(k)))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            key = str(v.get("name") or v.get("field") or v.get("n") or v.get("outcome") or i) if isinstance(v, dict) else str(i)
            out.update(flat(v, p + "[" + key + "]"))
    elif not isinstance(o, str) or len(o) <= 48:
        out[p] = o
    return out


def read_run(name, i, started):
    slot = f"{name}-r{i}"
    log = (ROOT / "traces" / f"final-{slot}.out")
    text = log.read_text() if log.exists() else ""
    r = {"run": i, "slot": slot, "log": str(log.relative_to(ROOT)), "status": "no END line", "seconds": None, "oracle": "", "oracle_ratio": -1.0, "audit": "", "in_words": "", "lint": "", "exported": "", "spec": None}
    m = re.search(r"END status=(\S+) total=(\d+)s", text)
    if m:
        r["status"], r["seconds"] = m.group(1), int(m.group(2))
    m = re.search(r"TEST oracle[^:]*: (\d+) / (\d+)", text)
    if m:
        r["oracle"] = f"{m.group(1)}/{m.group(2)}"; r["oracle_ratio"] = int(m.group(1)) / max(1, int(m.group(2)))
    m = re.search(r"audit: (\d+) correction", text)
    r["audit"] = m.group(1) if m else ""
    m = re.search(r"rules (computed in code: all|left in the bank's words[^\n]*)", text)
    r["in_words"] = "" if not m or m.group(1).startswith("computed") else m.group(1).split("): ", 1)[-1]
    m = re.search(r"lint problems=(\d+)", text)
    r["lint"] = m.group(1) if m else ""
    m = re.search(r"exported (\S+)", text)
    r["exported"] = m.group(1) if m else ""
    m = re.search(r"RESULT workflow_id=(\S+) agent_id=(\S+)", text)
    r["workflow_id"], r["agent_id"] = (m.group(1), m.group(2)) if m else ("", "")
    sp = ROOT / "out" / slot / "spec.json"
    if sp.exists() and sp.stat().st_mtime >= started - 5:
        try:
            r["spec"] = json.loads(sp.read_text())
        except Exception:
            pass
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--name", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--offline", action="store_true", help="pass --no-freya to every run (comparison only, nothing is saved on Freya)")
    ap.add_argument("--extra", default="", help="extra arguments for build.py, in one string")
    a = ap.parse_args()
    (ROOT / "traces").mkdir(exist_ok=True); (ROOT / "out" / "final").mkdir(parents=True, exist_ok=True)
    started = time.time()
    procs = []
    for i in range(1, a.runs + 1):
        slot = f"{a.name}-r{i}"
        env = dict(os.environ, FREYA_STATE_FILE=str(ROOT / f".freya-final-{slot}.json"))
        cmd = [sys.executable, str(ROOT / "builder" / "build.py"), *a.files, "--slot", slot] + (["--no-freya"] if a.offline else []) + a.extra.split()
        out = open(ROOT / "traces" / f"final-{slot}.out", "w")
        procs.append((i, subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, env=env, cwd=str(ROOT)), out))
        time.sleep(2)                                   # the runs do not start in the same second
    for i, p, out in procs:
        try:
            p.wait(timeout=31 * 60)
        except subprocess.TimeoutExpired:
            p.kill()
        out.close()
    runs = [read_run(a.name, i, started) for i in range(1, a.runs + 1)]
    # where do the readings differ?
    flats = {r["run"]: flat({k: v for k, v in (r["spec"] or {}).items()}) for r in runs if r["spec"]}
    keys = sorted(set().union(*flats.values())) if flats else []
    rows, minority = [], collections.Counter()
    for k in keys:
        vals = {i: json.dumps(f.get(k, "<missing>"), sort_keys=True) for i, f in flats.items()}
        if len(set(vals.values())) > 1:
            common, n = collections.Counter(vals.values()).most_common(1)[0]
            for i, v in vals.items():
                if v != common or n == 1:
                    minority[i] += 1
            rows.append((k, vals))
    for r in runs:
        r["minority"] = minority.get(r["run"], 0) if r["spec"] else 999
    ok = lambda r: r["status"] in ("ok", "offline-ok")
    ranked = sorted(runs, key=lambda r: (not ok(r), -r["oracle_ratio"], r["minority"], len(r["in_words"]), r["seconds"] or 9999))
    lines = [f"# {a.name}: {a.runs} builder runs, {time.strftime('%Y-%m-%d %H:%M')}", "",
             "| run | status | seconds | oracle | audit fixes | lint | fields where this run is the odd one | rules left in words | exported |", "|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        lines.append(f"| r{r['run']} | {r['status']} | {r['seconds']} | {r['oracle']} | {r['audit']} | {r['lint']} | {r['minority'] if r['spec'] else 'no spec'} | {r['in_words'] or '-'} | {pathlib.Path(r['exported']).name if r['exported'] else '-'} |")
    lines += ["", "Order by the evidence (complete, oracle agreement, agreement with the other runs, fewer rules in words, shorter): " + " > ".join("r" + str(r["run"]) for r in ranked), "",
              f"## Fields the runs read differently ({len(rows)} of {len(keys)})", ""]
    for k, vals in rows:
        lines.append(f"- `{k}`: " + "; ".join(f"r{i}={v[:90]}" for i, v in sorted(vals.items())))
    text = "\n".join(lines) + "\n"
    (ROOT / "out" / "final" / f"{a.name}-compare.md").write_text(text)
    json.dump([{k: v for k, v in r.items() if k != "spec"} for r in runs], open(ROOT / "out" / "final" / f"{a.name}-runs.json", "w"), indent=1)
    print(text)


if __name__ == "__main__":
    main()
