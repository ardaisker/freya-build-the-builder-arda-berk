"""Fast scripted chat against a workflow using a real practice session. Prints the transcript with engine events and the ledger.

    python3 builder/probe.py <workflow_id> PUB-01 "Yes, speaking." "14 March 1988" "4471" "Yes, today." "Yes, I confirm."
"""
import json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import freya
from score import http

def main():
    wid, case_id, turns = sys.argv[1], sys.argv[2], sys.argv[3:]
    cases = {c["id"]: c for c in json.load(open(ROOT / "public-test-set.json"))}
    case = cases[case_id]
    sess = http("/v1/practice/sessions", {"case": case_id})
    cv = sess["variables"]
    print("session vars:", {k: v for k, v in cv.items() if k != "customer_id"}, "| identity:", case.get("identity"))
    call_id = None
    for msg in turns:
        body = {"workflowId": wid, "message": msg, "customerVariables": cv}
        if call_id:
            body["callId"] = call_id
        t0 = time.time()
        try:
            r = freya.api("POST", "/api/v2/chat/message", body)
        except Exception as e:
            print("ERROR:", str(e)[:400]); break
        call_id = r.get("callId")
        print(f"[{time.time()-t0:4.1f}s] USER : {msg}")
        print(f"         AGENT: {r.get('response')}" + ("   <ended>" if r.get("endedByAgent") else ""))
        if r.get("endedByAgent"):
            break
    if call_id:
        try:
            call = freya.get_call(call_id)
            print("\n--- engine events ---")
            for m in call.get("messages", []):
                if m.get("role") == "system":
                    try:
                        ev = json.loads(m["message"])
                    except Exception:
                        continue
                    e = ev.get("event")
                    if e == "node_enter":
                        print(f"  node_enter {ev.get('from_node')} -> {ev.get('node')} ({ev.get('reason')})")
                    elif e == "function_call_start":
                        print(f"  call {ev.get('function')} args={json.dumps(ev.get('args', {}).get('body', ev.get('args')))[:200]}")
                    elif e == "function_call_complete":
                        print(f"  result {ev.get('function')} -> {json.dumps(ev.get('result'))[:300]}")
                    elif e == "route_evaluated" and ev.get("matched"):
                        print(f"  route {ev.get('from_node')} -> {ev.get('target')} ({str(ev.get('reason'))[:80]})")
                    elif e == "error":
                        print(f"  ERROR {ev.get('message')} {str(ev.get('details'))[:200]}")
            try:
                freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
            except Exception:
                pass
        except Exception as e:
            print("could not fetch call:", str(e)[:200])
    led = http("/v1/practice/ledger/" + cv["customer_id"])
    print("\n--- ledger ---", json.dumps({k: led.get(k) for k in ("outcome", "reason", "promises", "notes", "callbacks", "transfers")}))
    print("calls:", [c["tool"] for c in led.get("calls", [])])

if __name__ == "__main__":
    main()
