"""Check the deployed mock against test-customers.json: every listed answer must come back with the same status and body.
    python3 mock/check_mock.py https://<worker>.workers.dev briefs/final/test-environment/test-customers.json"""
import json, sys, time, urllib.request, urllib.error
BASE = sys.argv[1].rstrip("/") + "/voice/v1/"
D = json.load(open(sys.argv[2]))


def call(svc, data):
    req = urllib.request.Request(BASE + svc, data=json.dumps({"data": data, "call": {"ani": "", "lang": "tr"}}).encode(), method="POST", headers={"Content-Type": "application/json", "User-Agent": "mock-check/1"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


ok = bad = 0
t0 = time.time()
for c in D["customers"]:
    no, S, checks = c["customerNo"], c["services"], []
    for svc in ("cards.list", "contact.email.get", "statement.pdf.send"):
        if svc in S:
            data = {"customerNo": no if svc != "contact.email.get" else int(no)}
            if svc == "contact.email.get":
                data["intAddressInfoType"] = "E"
            if svc == "statement.pdf.send":
                data.update(cardNumber="x", currencyType="TL", statementDate="05.10.2026", emailAddress="a@b.example")
            checks.append((svc, data, S[svc]))
    for svc in ("cards.balance", "statement.week.get"):
        for card, e in S.get(svc, {}).items():
            checks.append((svc, {"cardNumber": card}, e))
    for svc in ("statement.week.decide", "statement.week.change"):
        for card, weeks in S.get(svc, {}).items():
            for w, e in weeks.items():
                checks.append((svc, {"cardNumber": card, "newStatementWeek": int(w) if svc.endswith("decide") else w, "statementDay": 5}, e))
    for svc, data, e in checks:
        if e.get("delaySeconds") and "--with-delay" not in sys.argv:
            continue
        st, body = call(svc, data)
        if st == e["http"] and body == e["response"]:
            ok += 1
        else:
            bad += 1
            print("MISMATCH", no, svc, data, st, e["http"])
print("exact matches:", ok, "mismatches:", bad, f"{time.time() - t0:.0f}s")
for svc, data in [("cards.list", {"customerNo": "11111111"}), ("cards.balance", {"cardNumber": "999"}), ("cards.balance", {"cardNumber": ""}), ("statement.week.get", {"cardNumber": "999"}),
                  ("statement.week.decide", {"cardNumber": "540000******1234", "newStatementWeek": 1, "statementDay": 5}), ("contact.email.get", {"customerNo": 90000001, "intAddressInfoType": ""}),
                  ("statement.pdf.send", {"customerNo": "94907600", "cardNumber": "540000******7211", "currencyType": "TL", "statementDate": "x", "emailAddress": "a@b"})]:
    st, body = call(svc, data)
    print("not in the file:", svc, data, "->", st, body["result"]["code"], body["result"]["type"])
sys.exit(1 if bad else 0)
