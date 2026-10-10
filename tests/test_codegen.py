import json, pathlib, sys, datetime
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "builder"))
from codegen import snippet

SPEC = json.load(open(ROOT / "out" / "brief-a.spec.json")) if (ROOT / "out" / "brief-a.spec.json").exists() else json.load(open(ROOT / "fixtures" / "brief-a.spec.json"))
NOW = "2026-10-14T11:00"


def run(name, vars, libs=("calendar_lib", "dateparse_lib")):
    code = snippet(name, libs=libs, SPEC=SPEC)
    assert "{" not in code and "}" not in code
    g = {"vars": vars}
    exec(code, g)
    return vars


def facts(products, now=NOW):
    v = {"now": now, "get_account_response.data.products": json.dumps(products)}
    return run("facts", v)


def test_no_braces_in_all_snippets():
    for n in ("facts", "resolve_date", "tp_resolve", "finalize"):
        code = snippet(n, libs=("calendar_lib", "dateparse_lib"), SPEC=SPEC)
        assert "{" not in code and "}" not in code


def test_deadlines_pub04_pub07():
    v = facts([{"product_id": "p1", "type": "car_loan", "past_due": 1250, "days_late": 14, "instalment_amount": 400}])
    pf = json.loads(v["pf_json"])
    assert pf[0]["deadline"] == "2026-10-23" and pf[0]["band"] == "late" and pf[0]["attempts"] == 2
    assert pf[0]["floor"] == 400 and pf[0]["attempt1_date"] == "2026-10-16"
    v = facts([{"product_id": "p1", "type": "personal_loan", "past_due": 540, "days_late": 5, "instalment_amount": 180}])
    pf = json.loads(v["pf_json"])
    assert pf[0]["deadline"] == "2026-11-02" and pf[0]["band"] == "early"
    assert "LATEST PAYMENT DATE (deadline) Monday 2 November 2026" in v["facts"]
    assert "Monday 26 October 2026" in v["facts"]  # listed as holiday


def test_products_flattened_keys():
    v = {"now": NOW, "get_account_response.data.products.0.product_id": "p1", "get_account_response.data.products.0.type": "credit_card",
         "get_account_response.data.products.0.past_due": "420", "get_account_response.data.products.0.days_late": "6", "get_account_response.data.products.0.minimum_payment": "126",
         "get_account_response.data.products.0.card_last4": "4821"}
    run("facts", v)
    pf = json.loads(v["pf_json"])
    assert pf[0]["label"] == "credit card ending 4821" and pf[0]["floor"] == "126"


def test_resolve_holiday_then_next_business_day():
    v = facts([{"product_id": "p1", "type": "personal_loan", "past_due": 540, "days_late": 5, "instalment_amount": 180}])
    v["customer_date_text"] = "Monday the 26th"
    run("resolve_date", v)
    assert v["date_status"] == "not_business" and "Tuesday 27 October 2026" in v["date_verdict"]
    assert v["customer_date_text"] == "-"


def test_resolve_after_deadline():
    v = facts([{"product_id": "p1", "type": "car_loan", "past_due": 1250, "days_late": 14, "instalment_amount": 400}])
    v["customer_date_text"] = "6 November"
    run("resolve_date", v)
    assert v["date_status"] == "after_deadline" and "Friday 23 October 2026" in v["date_verdict"]


def test_resolve_two_products_one_after_deadline():
    v = facts([{"product_id": "p1", "type": "credit_card", "past_due": 300, "days_late": 4, "minimum_payment": 90, "card_last4": "6604"},
               {"product_id": "p2", "type": "personal_loan", "past_due": 900, "days_late": 20, "instalment_amount": 300}])
    v["customer_date_text"] = "30 October"
    run("resolve_date", v)
    assert v["date_status"] == "partly_after_deadline"
    assert "Friday 23 October 2026" in v["date_verdict"] and "p2" in v["date_verdict"]


def test_resolve_this_friday_and_words():
    v = facts([{"product_id": "p1", "type": "credit_card", "past_due": 365, "days_late": 8, "minimum_payment": 109.5, "card_last4": "7740"}])
    for text in ("this Friday", "Friday", "the sixteenth of October", "16th", "October 16", "friday the 16th"):
        v["customer_date_text"] = text
        run("resolve_date", v)
        assert v["resolved_date"] == "2026-10-16", text
        assert v["date_status"] == "ok", text
    v["customer_date_text"] = "next Friday"
    run("resolve_date", v)
    assert v["resolved_date"] == "2026-10-23"
    v["customer_date_text"] = "the week after next"
    run("resolve_date", v)
    assert v["date_status"] == "vague" and "Friday 23 October 2026" in v["date_verdict"]
    v["customer_date_text"] = "tomorrow"
    run("resolve_date", v)
    assert v["resolved_date"] == "2026-10-15"
    v["customer_date_text"] = "the twenty-second of October"
    run("resolve_date", v)
    assert v["resolved_date"] == "2026-10-22"
    for text in ("six hundred and thirty-seven dollars and fifty cents on Friday the sixteenth of October twenty twenty-six", "Friday the sixteenth of October twenty twenty-six", "October sixteenth", "the sixteenth of October 2026", "on the 16th of October", "I can pay it on Friday"):
        v["customer_date_text"] = text
        run("resolve_date", v)
        assert v["resolved_date"] == "2026-10-16", (text, v["date_verdict"])


def test_tp_callback_window():
    v = {"now": NOW, "callback_day_text": "tomorrow morning", "callback_time_text": "around eleven"}
    run("tp_resolve", v)
    assert v["tp_status"] == "ok" and v["callback_date"] == "2026-10-15" and v["callback_time"] == "11:00"
    v = {"now": NOW, "callback_day_text": "Saturday", "callback_time_text": "10 am"}
    run("tp_resolve", v)
    assert v["tp_status"] == "retry"
    v["callback_day_text"] = "tomorrow"; v["callback_time_text"] = "9 pm"
    run("tp_resolve", v)
    assert v["tp_status"] == "no"
    v = {"now": NOW, "callback_day_text": "today", "callback_time_text": "half past five"}
    run("tp_resolve", v)
    assert v["tp_status"] == "ok" and v["callback_time"] == "17:30"
    v = {"now": NOW, "callback_day_text": "today", "callback_time_text": "10:30"}
    run("tp_resolve", v)
    assert v["tp_status"] == "retry"  # not later than now


def test_finalize():
    base = {"now": NOW}
    v = dict(base, transfer_to_agent_success_count="1", transfer_queue="restructuring"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("transferred", "restructuring")
    v = dict(base, promises_log="p1;"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("promise", "")
    v = dict(base, paid_flag="paid"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("paid", "")
    v = dict(base, hardship_flag="hardship"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("no_promise", "hardship")
    v = dict(base, hardship_flag="hardship", promises_log="p1;"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("promise", "")
    v = dict(base, stance="already_paid"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("paid", "")
    v = dict(base, stance="hardship"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("no_promise", "hardship")
    v = dict(base, stance="dispute"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("no_promise", "dispute")
    v = dict(base, stance="refuses"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("no_promise", "refused")
    v = dict(base, create_promise_failure_count="2", create_promise_success_count="0", stance="names_date"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("no_promise", "service_error")
    v = dict(base, notes_log="p1:paid;p2:paid;"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("paid", "")
    v = dict(base, notes_log="p1:paid;p2:refused;p3:dispute;"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("no_promise", "refused")
    v = dict(base, notes_log="p1:refused;", hardship_flag="hardship", product_count="1"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("no_promise", "hardship")
    v = dict(base, promises_log="p1;", notes_log="p2:refused;"); run("finalize", v)
    assert (v["outcome"], v["reason"]) == ("promise", "")
