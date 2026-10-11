"""Proof that a change to the code steps alters nothing for the briefs we already handle: run the code steps (facts,
date check, callback check) for every test customer of every fixture spec on several calendar days and day phrases,
and save or compare all outputs.   python3 builder/golden.py save FILE   |   python3 builder/golden.py compare FILE"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "builder")]
import apimap
from codegen import snippet
LIBS = ("calendar_lib", "dateparse_lib")
TEXTS = ["today", "tomorrow", "this Friday", "next Friday", "Saturday", "the 30th", "6 November", "next week", "end of the month", "Monday the 26th", "in two weeks", "31 December", "next week Thursday", "23 October", "2 November"]
DAYS = ("2026-10-14T11:00", "2026-10-16T09:30", "2026-10-30T15:00", "2026-12-23T10:00")
CALLBACKS = (("tomorrow", "2 pm"), ("Sunday", "morning"), ("-", "tonight at 9 pm"), ("today", "5 pm"), ("Friday", "10"), ("in three days", "noon"))


def cases():
    out = []
    for f in ("public-test-set.json", "fixtures/edge-cases.json"):
        d = json.load(open(ROOT / f))
        out += list(d.get("cases", d) if isinstance(d, dict) else d)
    return out


def compute():
    out = {}
    for name in ("brief-ab", "variant", "renamed", "raw-bank-material"):
        spec = json.load(open(ROOT / "fixtures" / f"{name}.spec.json"))
        api = json.load(open(ROOT / "tools" / "openapi.json" if name == "brief-ab" else ROOT / "fixtures" / f"{name}.openapi.json"))
        S = dict(spec, api=apimap.resolve(spec, api))
        code = {k: snippet(k, libs=LIBS, SPEC=S) for k in ("facts", "resolve_date", "tp_resolve")}
        for c in cases():
            prods = [dict(p, product_id=p.get("product_id") or f"p{i + 1}") for i, p in enumerate(c.get("products") or [])]
            for now in DAYS:
                v = {"now": now, "account_products": json.dumps(prods)}
                try:
                    exec(code["facts"], {"vars": v})
                except Exception as e:
                    v = {"ERR": repr(e)}
                key = f"{name}|{c.get('id')}|{now}"
                out[key] = {k: v.get(k) for k in sorted(v) if k != "account_products"}
                for tx in TEXTS:
                    w = dict(v); w["customer_date_text"] = tx
                    try:
                        exec(code["resolve_date"], {"vars": w})
                        out[key + "|" + tx] = [w.get("resolved_date"), w.get("date_status"), w.get("date_verdict")]
                    except Exception as e:
                        out[key + "|" + tx] = repr(e)
        for cb in CALLBACKS:
            w = {"now": DAYS[0], "callback_day_text": cb[0], "callback_time_text": cb[1]}
            try:
                exec(code["tp_resolve"], {"vars": w})
            except Exception as e:
                w = {"ERR": repr(e)}
            out[f"{name}|cb|{cb}"] = {k: w.get(k) for k in sorted(w)}
    return out


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    now = compute()
    if mode == "save":
        json.dump(now, open(path, "w"), sort_keys=True)
        print(len(now), "outputs saved to", path)
    else:
        old = json.load(open(path))
        now = json.loads(json.dumps(now))
        diff = [k for k in old if old[k] != now.get(k)] + [k for k in now if k not in old]
        print(f"{len(old)} outputs compared, {len(diff)} different")
        for k in diff[:8]:
            print(" ", k, "\n    before:", str(old.get(k))[:240], "\n    now:   ", str(now.get(k))[:240])
        sys.exit(1 if diff else 0)
