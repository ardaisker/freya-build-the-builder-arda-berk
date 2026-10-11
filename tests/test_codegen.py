import json, pathlib, sys, datetime
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "builder"))
from codegen import snippet

SPEC = json.load(open(ROOT / "fixtures" / "brief-a.spec.json"))
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
    assert pf[0]["floor"] == 400 and [o["date"] for o in pf[0]["offers"]] == ["2026-10-16", "2026-10-23"]
    assert 'offer 1 = "1250.00 on Friday 16 October 2026" (use the floor 400.00 instead if the full amount was too much)' in v["facts"]
    assert 'offer 2 = "400.00 on Friday 23 October 2026"' in v["facts"]
    v = facts([{"product_id": "p1", "type": "personal_loan", "past_due": 540, "days_late": 5, "instalment_amount": 180}])
    pf = json.loads(v["pf_json"])
    assert pf[0]["deadline"] == "2026-11-02" and pf[0]["band"] == "early" and len(pf[0]["offers"]) == 1
    assert "STOP AT ONCE" in v["facts"]
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
    assert "ATTEMPT 1 = 1250.00 on Friday 16 October 2026" in v["date_verdict"] and "ATTEMPT 2 = 400.00 on Friday 23 October 2026" in v["date_verdict"]


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
    v["customer_date_text"] = "next week"
    run("resolve_date", v)
    assert v["date_status"] == "vague" and v["vague_hint"] == "next"
    v["customer_date_text"] = "Thursday"
    run("resolve_date", v)
    assert v["resolved_date"] == "2026-10-22" and v["vague_hint"] == ""
    v["customer_date_text"] = "Thursday"
    run("resolve_date", v)
    assert v["resolved_date"] == "2026-10-15"
    v["customer_date_text"] = "the twenty-second of October"
    run("resolve_date", v)
    assert v["resolved_date"] == "2026-10-22"
    v["customer_date_text"] = "the 21st, sorry, I mean the 22nd"
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
    assert v["callback_say"] == "Thursday 15 October 2026 at 11:00"
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
    for text, want in (("five p.m.", "17:00"), ("five thirty pm", "17:30"), ("at five", "17:00"), ("ten in the morning", "10:00"), ("quarter past three", "15:15")):
        v = {"now": NOW, "callback_day_text": "tomorrow", "callback_time_text": text}
        run("tp_resolve", v)
        assert v["callback_time"] == want, (text, v["tp_verdict"])
    v = {"now": NOW, "callback_day_text": "tomorrow", "callback_time_text": "eleven ten, sorry, I mean eleven"}
    run("tp_resolve", v)
    assert v["tp_status"] == "ok" and v["callback_time"] == "11:00"


def test_finalize():
    base = {"now": NOW}
    v = dict(base, transfer_to_agent_success_count="1", transfer_queue="restructuring"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("transferred", "restructuring")
    v = dict(base, promises_log="p1;"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("promise", "")
    v = dict(base, paid_flag="paid"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("paid", "")
    v = dict(base, hardship_flag="hardship"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("no_promise", "hardship")
    v = dict(base, hardship_flag="hardship", promises_log="p1;"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("promise", "")
    v = dict(base, stance="already_paid"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("paid", "")
    v = dict(base, stance="hardship"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("no_promise", "hardship")
    v = dict(base, stance="dispute"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("no_promise", "dispute")
    v = dict(base, stance="refuses"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("no_promise", "refused")
    v = dict(base, call_outcome="x", call_reason="y", promises_log="p1;"); run("finalize", v)
    assert v["call_outcome"] == "promise"
    v = dict(base, create_promise_failure_count="2", create_promise_success_count="0", stance="names_date"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("no_promise", "service_error")
    v = dict(base, notes_log="p1:paid;p2:paid;"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("paid", "")
    v = dict(base, notes_log="p1:paid;p2:refused;p3:dispute;"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("no_promise", "refused")
    v = dict(base, notes_log="p1:refused;", hardship_flag={"value": "hardship", "confidence": 0.9, "source": "extraction"}, product_count="1"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("no_promise", "hardship")
    v = dict(base, notes_log="p1:refused;", hardship_flag="hardship", product_count="1"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("no_promise", "hardship")
    v = dict(base, promises_log="p1;", notes_log="p2:refused;"); run("finalize", v)
    assert (v["call_outcome"], v["call_reason"]) == ("promise", "")


# ---- generalisation: nothing below uses Brief A's names or rules ----
import copy, apimap


def run_spec(name, vars, spec):
    code = snippet(name, libs=("calendar_lib", "dateparse_lib"), SPEC=spec)
    assert "{" not in code and "}" not in code
    exec(code, {"vars": vars})
    return vars


def test_renamed_api_end_to_end_offline():
    spec = json.load(open(ROOT / "fixtures" / "renamed.spec.json")); api = json.load(open(ROOT / "fixtures" / "renamed.openapi.json"))
    A = apimap.resolve(spec, api)
    assert A["tools"]["create_promise"] == {"customer": "client_ref", "product_id": "account_ref", "amount": "pledged_amount", "date": "pay_date"}
    assert A["tools"]["verify_identity"]["verified"] == "match" and A["tools"]["verify_identity"]["all_verified"] == "identity_complete"
    assert A["promise_outcome"] == "ptp" and A["transfer_outcome"] == "handed_over" and A["ok"] == "success"
    S = dict(spec, api=A)
    v = {"now": NOW, "get_account_response.data.accounts.0.account_ref": "a1", "get_account_response.data.accounts.0.kind": "card", "get_account_response.data.accounts.0.pan_last4": "1903",
         "get_account_response.data.accounts.0.arrears": "2125.1", "get_account_response.data.accounts.0.days_in_arrears": "12", "get_account_response.data.accounts.0.min_due": "637.5"}
    run_spec("facts", v, S)
    pf = json.loads(v["pf_json"])
    assert pf[0]["product_id"] == "a1" and pf[0]["floor"] == "637.5" and pf[0]["deadline"] == "2026-10-23" and "1903" in pf[0]["label"]
    v2 = run_spec("finalize", {"promises_log": "a1;"}, S)
    assert v2["call_outcome"] == "ptp"
    from compile import compile_workflow
    from lint import lint
    wf = compile_workflow(spec, api); assert lint(wf) == []
    body = [t for t in wf["nodes"]["negotiate"]["tools"] if t["function"]["name"] == "create_promise"][0]["function"]["parameters"]["properties"]["body"]["properties"]
    assert set(body) == {"client_ref", "account_ref", "pledged_amount", "pay_date"} and body["client_ref"]["default"] == "{{client_ref}}"
    close = wf["tools"][0]["function"]["parameters"]["properties"]["body"]["properties"]
    assert close["result"]["default"] == "{{call_outcome}}" and close["detail"]["default"] == "{{call_reason}}"


def test_heuristic_alone_maps_the_renamed_api():
    api = json.load(open(ROOT / "fixtures" / "renamed.openapi.json"))
    A = apimap.resolve({}, api)       # no model section at all
    assert A["tools"]["verify_identity"]["answer"] == "reply" and A["tools"]["verify_identity"]["field"] == "question"
    assert A["tools"]["get_account"]["products"] == "accounts" and A["tools"]["get_account"]["past_due"] == "arrears" and A["tools"]["get_account"]["days_late"] == "days_in_arrears"
    assert A["tools"]["close_call"]["outcome"] == "result" and A["tools"]["transfer_to_agent"]["queue"] == "team" and A["error"] == "problem"


def test_other_deadline_attempt_and_floor_rules():
    spec = copy.deepcopy(SPEC)
    spec["calendar"] = {"business_weekdays": ["Sun", "Mon", "Tue", "Wed", "Thu"], "holidays": ["2026-10-15"]}
    spec["bands"] = [{"name": "x", "days_late_min": 1, "days_late_max": 30, "deadline_rule": {"type": "calendar_days_after_today", "n": 10, "roll": "previous"}, "persuasion_attempts": 3},
                     {"name": "y", "days_late_min": 31, "days_late_max": 999, "deadline_business_days_after_today": 3, "persuasion_attempts": 0}]
    spec["persuasion"]["attempts"] = [{"n": 1, "amount": "full", "date_rule": {"type": "next_business_day"}, "bands": "all"},
                                      {"n": 2, "amount": "floor", "date_rule": {"type": "business_days_after_today", "n": 3}, "bands": "all"},
                                      {"n": 3, "amount": "floor", "date_rule": {"type": "end_of_month"}, "bands": ["x"]}]
    spec["amounts"]["floor_by_type"] = {}
    spec["amounts"]["floor_percent_of_past_due"] = 25
    v = {"now": NOW, "get_account_response.data.products": json.dumps([{"product_id": "p1", "type": "car_loan", "past_due": 1000, "days_late": 5}, {"product_id": "p2", "type": "car_loan", "past_due": 200, "days_late": 40}])}
    run_spec("facts", v, spec)
    pf = json.loads(v["pf_json"])
    # Wed 14 Oct + 10 calendar days = Sat 24 Oct -> previous business day Thu 22 Oct (Fri/Sat are the weekend here)
    assert pf[0]["deadline"] == "2026-10-22" and pf[0]["floor"] == 250.0
    # Thu 15 Oct is a holiday, Fri/Sat weekend -> next business day is Sun 18 Oct; 3 business days after today = 18, 19, 20; end of month capped at the deadline
    assert [o["date"] for o in pf[0]["offers"]] == ["2026-10-18", "2026-10-20", "2026-10-22"] and [o["amount"] for o in pf[0]["offers"]] == ["full", "floor", "floor"]
    assert pf[1]["offers"] == [] and "No persuasion offer for p2" in v["facts"]
    assert 'offer 3 = "250.00 on Thursday 22 October 2026"' in v["facts"]
    spec["date_rules"]["non_business_day_roll"] = "previous"
    v["customer_date_text"] = "Saturday the 17th"
    run_spec("resolve_date", v, spec)
    assert v["date_status"] == "not_business" and "Wednesday 14 October 2026" in v["date_verdict"]


def test_verify_hook_counts_wrong_answers_without_api_fields():
    from compile import VERIFY_HOOK
    code = VERIFY_HOOK
    for k, val in (("@@HINTS@@", "{}"), ("@@HINT@@", "hint"), ("@@VERIFIED@@", "match"), ("@@ALL@@", "__none__"), ("@@LEFT@@", "__none__"), ("@@OK@@", "success"), ("@@ERR@@", "problem"),
                   ("@@FMT@@", "x"), ("@@VSAY@@", "ok"), ("@@FIELD@@", "q2"), ("@@IS_LAST@@", "True"), ("@@MAXWRONG@@", "2")):
        code = code.replace(k, val)
    vars_ = {}
    r = {"data": {"success": True, "match": False}}; exec(code, {"result": r, "vars": vars_}); assert "1 wrong answer(s) left" in r["data"]["what_to_do_next"]
    r = {"data": {"success": True, "match": False}}; exec(code, {"result": r, "vars": vars_}); assert vars_["id_state"] == "failed"
    vars_ = {}
    r = {"data": {"success": True, "match": True}}; exec(code, {"result": r, "vars": vars_}); assert vars_["id_state"] == "verified"
    r = {"data": {"success": False, "problem": "unreadable"}}; vars_ = {}; exec(code, {"result": r, "vars": vars_}); assert "does not count as wrong" in r["data"]["what_to_do_next"] and "id_wrong_n" not in vars_


def test_words_that_only_look_like_days_or_months():
    v = facts([{"product_id": "p1", "type": "credit_card", "past_due": 365, "days_late": 8, "minimum_payment": 109.5, "card_last4": "7740"}])
    for text in ("next month", "sometime next month", "I may pay later", "after the wedding", "when the market opens", "in a month or so", "monthly"):
        v["customer_date_text"] = text
        run("resolve_date", v)
        assert v["resolved_date"] == "", (text, v["date_verdict"])
    for text, want in (("the 2nd of May", "2027-05-02"), ("May 3rd", "2027-05-03"), ("Wed", "2026-10-21"), ("Sept 30", "2026-09-30"), ("this Thurs", "2026-10-15")):
        v["customer_date_text"] = text
        run("resolve_date", v)
        assert v["resolved_date"] == want, (text, v["resolved_date"])


def test_callback_without_today():
    spec = copy.deepcopy(SPEC)
    spec["third_party"]["callback"].update({"allowed_days": "any_business_day_within_3", "max_days_ahead": 3, "include_today": False, "from": "08:30", "to": "17:30", "ask_again_once": False})
    v = run_spec("tp_resolve", {"now": NOW, "callback_day_text": "today", "callback_time_text": "3 pm"}, spec)
    assert v["tp_status"] == "no"
    v = run_spec("tp_resolve", {"now": NOW, "callback_day_text": "Monday", "callback_time_text": "9 am"}, spec)
    assert v["tp_status"] == "ok" and v["callback_date"] == "2026-10-19"
    v = run_spec("tp_resolve", {"now": NOW, "callback_day_text": "next Tuesday", "callback_time_text": "9 am"}, spec)
    assert v["tp_status"] == "no"      # the 4th business day ahead


def test_callback_in_two_parts_and_next_week_weekday():
    v = run("tp_resolve", {"now": NOW, "callback_day_text": "tomorrow", "callback_time_text": "-"})
    assert v["tp_status"] == "retry" and "not the time" in v["tp_verdict"] and v.get("tp_attempts") in (None, "0")
    v["callback_day_text"] = "-"; v["callback_time_text"] = "2 pm"
    run("tp_resolve", v)
    assert v["tp_status"] == "ok" and v["callback_date"] == "2026-10-15" and v["callback_time"] == "14:00"
    # a day outside the allowed days is already the one failed proposal, even without a time
    v = run("tp_resolve", {"now": NOW, "callback_day_text": "Sunday", "callback_time_text": "in the morning"})
    assert v["tp_status"] == "retry" and v["tp_attempts"] == "1" and "ONCE" in v["tp_verdict"]
    v["callback_day_text"] = "tomorrow"; v["callback_time_text"] = "2 pm"
    run("tp_resolve", v)
    assert v["tp_status"] == "ok" and v["callback_date"] == "2026-10-15"
    # tonight is today; a second proposal outside the window ends it
    v = run("tp_resolve", {"now": NOW, "callback_day_text": "-", "callback_time_text": "tonight at 9 pm"})
    assert v["tp_status"] == "retry" and v["tp_attempts"] == "1"
    v["callback_day_text"] = "Saturday"; v["callback_time_text"] = "noon"
    run("tp_resolve", v)
    assert v["tp_status"] == "no"
    w = facts([{"product_id": "p1", "type": "personal_loan", "past_due": 540, "days_late": 5, "instalment_amount": 180}])
    w["customer_date_text"] = "next week, on Thursday"
    run("resolve_date", w)
    assert w["resolved_date"] == "2026-10-22"
    w["customer_date_text"] = "next week Wednesday, sorry, I mean Thursday"
    run("resolve_date", w)
    assert w["resolved_date"] == "2026-10-22"


def test_notes_backstop_fills_missing_note():
    import compile as comp
    spec = json.load(open(ROOT / "fixtures" / "brief-ab.spec.json"))
    wf = comp.compile_workflow(spec, json.load(open(ROOT / "tools" / "openapi.json")))
    assert wf["nodes"]["finalize"]["passthrough_default_transition"] == "notes_backstop"
    code = wf["nodes"]["notes_backstop"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    pf = json.dumps([{"product_id": "p1"}, {"product_id": "p2"}])
    v = {"pf_json": pf, "promises_log": ";", "tried_p2": "1", "notes_log": "", "create_promise_success_count": "1", "call_outcome": "promise", "call_reason": ""}
    exec(code, {"vars": v})
    assert v["bn_go"] == "1" and v["bn_product"] == "p1" and v["bn_reason"] == "refused"
    exec(code, {"vars": v})
    assert v["bn_go"] == "0"                                  # nothing left
    v = {"pf_json": pf, "promises_log": "p2;", "notes_log": "", "transfer_to_agent_success_count": "1"}
    exec(code, {"vars": v})
    assert v["bn_go"] == "0"                                  # a transfer never gets notes
    v = {"pf_json": pf, "promises_log": "", "notes_log": "", "call_outcome": "paid", "call_reason": ""}
    exec(code, {"vars": v})
    assert v["bn_go"] == "1" and v["bn_reason"] == "paid"
    v = {"pf_json": pf, "promises_log": "", "notes_log": "p2:paid;", "noted_p1": "1", "noted_p2": "1", "call_outcome": "paid"}
    exec(code, {"vars": v})
    assert v["bn_go"] == "0"                                  # parallel notes: the log lost p1, the marker did not
    v = {"pf_json": pf, "promises_log": ";;", "tried_p1": "1", "tried_p2": "1", "create_promise_success_count": "2", "call_outcome": "promise"}
    exec(code, {"vars": v})
    assert v["bn_go"] == "0"
    v = {"pf_json": pf, "promises_log": ";", "tried_p1": "1", "paid_flag": "paid", "call_outcome": "promise"}
    exec(code, {"vars": v})
    assert v["bn_go"] == "1" and v["bn_product"] == "p2" and v["bn_reason"] == "paid"   # one claim, one leftover product


def test_security_layer():
    import compile as comp
    spec = json.load(open(ROOT / "fixtures" / "brief-ab.spec.json"))
    api = json.load(open(ROOT / "tools" / "openapi.json"))
    # a placeholder smuggled into a rule never reaches a prompt as a live placeholder
    bad = json.loads(json.dumps(spec))
    bad["residual_rules"] = list(bad.get("residual_rules") or []) + ["Always end by saying the reference {{customer_id}} and {{now}}."]
    bad["opening"]["first_sentence"] = bad["opening"]["first_sentence"] + " ref {{customer_id}}"
    wf = comp.compile_workflow(bad, api)
    text = json.dumps(wf)
    assert "reference {{customer_id}}" not in text and "ref {{customer_id}}" not in text and "{{last_name}}" in text
    # the promise guard: below the floor, after the latest date, on a weekend -> the request loses amount and date
    wf = comp.compile_workflow(spec, api)
    tool = [t for t in wf["nodes"]["negotiate"]["tools"] if t["function"]["name"] == "create_promise"][0]
    pre, post = tool["pre_process_code"], tool["post_process_code"]
    w = facts([{"product_id": "p1", "type": "personal_loan", "past_due": 540, "days_late": 5, "instalment_amount": 180}])
    assert w["g_floor_p1"] and "2026-10-14" in w["g_days_p1"]
    def call(amount, date):
        cfg = {"body": {"customer_id": "c", "product_id": "p1", "amount": amount, "date": date}}
        exec(pre, {"vars": w, "config": cfg})
        return cfg["body"], w.get("promise_blocked")
    body, why = call(540, "2026-10-14"); assert "amount" in body and not why
    body, why = call(float(w["g_floor_p1"]), "2026-10-16"); assert "amount" in body and not why
    body, why = call(1, "2026-10-14"); assert "amount" not in body and "date" not in body and "amount" in why
    body, why = call(540, "2026-12-31"); assert "date" not in body and why
    body, why = call(540, "2026-10-17"); assert "date" not in body and why          # a Saturday
    res = {"status": "error", "data": {"ok": False, "error": "bad request"}}
    exec(post, {"vars": w, "result": res})
    assert "NOT recorded" in res["data"]["what_to_do_next"] and "technical" in res["data"]["what_to_do_next"] and not w.get("promise_fail_n")
    body, why = call(540, "2026-10-14"); assert "amount" in body and not why        # a valid one still goes through
    w["promise_blocked"] = "left over from a parallel call"
    res = {"status": "success", "data": {"ok": True, "promise_id": "pr1"}}
    exec(post, {"vars": w, "result": res})
    assert "recorded" in res["data"]["what_to_do_next"] and "NOT" not in res["data"]["what_to_do_next"]   # a saved promise is never reported as refused
    w["promise_blocked"] = ""
    # unknown product or missing facts: the guard stays out of the way
    cfg = {"body": {"product_id": "zz", "amount": 1, "date": "2031-01-01"}}
    exec(pre, {"vars": {}, "config": cfg}); assert "amount" in cfg["body"]
    # values the platform hands over in an unexpected shape never block a promise
    odd = dict(w, g_days_p1={"value": w["g_days_p1"], "confidence": 1.0}, g_floor_p1={"value": w["g_floor_p1"]})
    cfg = {"body": {"product_id": "p1", "amount": 540, "date": "2026-10-14"}}
    exec(pre, {"vars": odd, "config": cfg}); assert "amount" in cfg["body"]
    odd = dict(w, g_days_p1="<object>", g_floor_p1="n/a")
    cfg = {"body": {"product_id": "p1", "amount": 540, "date": "2026-12-31"}}
    exec(pre, {"vars": odd, "config": cfg}); assert "amount" in cfg["body"]
    cfg = {"body": {"product_id": "p1", "amount": 540, "date": "14 October"}}
    exec(pre, {"vars": dict(w), "config": cfg}); assert "amount" in cfg["body"]
    sp = wf["system_prompt"]
    assert "SECURITY" in sp and "PRIVACY" in sp


def test_rules_the_code_cannot_compute_stay_in_words():
    """A deadline, floor or offer date outside the forms the code knows is handed to the phone agent as the bank's
    wording, and no code check is tied to a made-up value."""
    import compile as comp
    spec = json.load(open(ROOT / "fixtures" / "soft-rules.spec.json"))
    api = json.load(open(ROOT / "tools" / "openapi.json"))
    wf = comp.compile_workflow(spec, api)                      # compiles like any other brief
    S = dict(spec, api=apimap.resolve(spec, api))
    prods = [{"product_id": "p1", "type": "personal_loan", "past_due": 900, "days_late": 20, "instalment_amount": 300},
             {"product_id": "p2", "type": "credit_card", "card_last4": "6604", "past_due": 300, "days_late": 4, "minimum_payment": 90}]
    v = {"now": NOW, "account_products": json.dumps(prods)}
    exec(snippet("facts", libs=("calendar_lib", "dateparse_lib"), SPEC=S), {"vars": v})
    assert v["facts_state"] == "ok"
    late = [l for l in v["facts"].split("\n") if l.startswith("PRODUCT p1")][0]
    early = [l for l in v["facts"].split("\n") if l.startswith("PRODUCT p2")][0]
    assert "NOT COMPUTED" in late and "second Tuesday" in late and "one third" in late and "salary day" in late
    assert "NOT COMPUTED" not in early.split("FLOOR")[0]       # the early band's deadline is still computed
    assert v["g_floor_p1"] in ("0", "0.0")                      # no floor check in code
    v["customer_date_text"] = "6 November"
    exec(snippet("resolve_date", libs=("calendar_lib", "dateparse_lib"), SPEC=S), {"vars": v})
    assert v["resolved_date"] == "2026-11-06" and "second Tuesday" in v["date_verdict"] and "check the day yourself" in v["date_verdict"]
    tool = [t for t in wf["nodes"]["negotiate_multi"]["tools"] if t["function"]["name"] == "create_promise"][0]
    cfg = {"body": {"product_id": "p1", "amount": 55, "date": "2026-11-06"}}
    exec(tool["pre_process_code"], {"vars": v, "config": cfg})
    assert "amount" in cfg["body"] and not v.get("promise_blocked")            # the guard does not block on an unknown rule
    cfg = {"body": {"product_id": "p1", "amount": 55, "date": "2026-11-07"}}    # a Saturday is still refused
    exec(tool["pre_process_code"], {"vars": v, "config": cfg})
    assert "date" not in cfg["body"]
    # a brief that names no callback day limit does not inherit one
    S2 = json.loads(json.dumps(S)); S2["third_party"]["callback"]["allowed_days"] = ""; S2["third_party"]["callback"].pop("max_days_ahead", None)
    w = {"now": NOW, "callback_day_text": "Monday", "callback_time_text": "2 pm"}
    exec(snippet("tp_resolve", libs=("calendar_lib", "dateparse_lib"), SPEC=S2), {"vars": w})
    assert w["tp_status"] == "ok" and w["callback_date"] == "2026-10-19"


def test_yesterday_is_past():
    v = facts([{"product_id": "p1", "type": "car_loan", "past_due": 1250, "days_late": 14, "instalment_amount": 400}])
    v["customer_date_text"] = "yesterday"
    run("resolve_date", v)
    assert v["date_status"] == "past" and v["resolved_date"] == "2026-10-13"


def test_oracle_runs_cases_locally_and_spots_a_wrong_spec():
    import copy, oracle
    api = json.load(open(ROOT / "tools" / "openapi.json"))
    case = {"id": "T1", "now": NOW, "product": {"product_id": "p1", "type": "car_loan", "past_due": 1250, "days_late": 14, "instalment_amount": 400},
            "expect": {"deadline": "2026-10-23", "floor": 400, "attempts": 2, "offers": [{"amount": 1250, "date": "2026-10-16"}, {"amount": 400, "date": "2026-10-23"}]},
            "date_text": "Monday the 26th", "expect_date": {"status": "not_business", "date": "2026-10-26", "offer": "2026-10-27"}}
    assert oracle.run_cases(SPEC, api, [case]) == {"T1": []}
    bad = copy.deepcopy(SPEC)
    bad["calendar"]["holidays"] = [h for h in bad["calendar"]["holidays"] if h != "2026-10-26"]
    problems = oracle.run_cases(bad, api, [case])["T1"]
    assert any("deadline" in p for p in problems) and any("Monday the 26th" in p for p in problems)


def test_counts_come_from_the_spec():
    import copy
    from compile import compile_workflow
    api = json.load(open(ROOT / "tools" / "openapi.json"))
    s = copy.deepcopy(SPEC)
    s["identity"]["decline"]["refusals_to_close"] = 1
    s["opening"]["max_asks"] = 3
    s["confirm_record"]["retry_on_failure"] = 2
    wf = json.dumps(compile_workflow(s, api))
    assert "for the FIRST time" in wf and "SECOND real refusal" not in wf and "These questions protect your account" not in wf
    assert "after the third ask" in wf and "after three asks" in wf
    assert "fails three times" in wf


def test_weekday_with_day_number_picks_the_matching_month():
    v = facts([{"product_id": "p1", "type": "car_loan", "past_due": 1250, "days_late": 14, "instalment_amount": 400}], now="2026-10-22T11:00")
    for text, want, status in (("Monday the 19th", "2026-10-19", "past"), ("Friday the 23rd", "2026-10-23", "ok"), ("Monday the 26th", "2026-10-26", "not_business")):
        v["customer_date_text"] = text
        run("resolve_date", v)
        assert (v["resolved_date"], v["date_status"]) == (want, status), (text, v["resolved_date"], v["date_status"])


def test_floor_combinations_band_full_and_month_end():
    import copy
    global SPEC
    keep = SPEC
    try:
        SPEC = copy.deepcopy(keep)
        SPEC["amounts"].update({"floor_by_type": {}, "floor_percent_of_past_due": 15, "floor_fixed_amount": 50})
        SPEC["bands"] = [{"name": "S1", "days_late_min": 1, "days_late_max": 10, "deadline_rule": {"type": "end_of_month", "if_today_use_next_month": True}, "persuasion_attempts": 1},
                         {"name": "S4", "days_late_min": 61, "days_late_max": 90, "deadline_rule": {"type": "today"}, "persuasion_attempts": 0, "floor": "full"}]
        pf = lambda pd, dl, now=NOW: json.loads(facts([{"product_id": "p1", "type": "car_loan", "past_due": pd, "days_late": dl}], now=now)["pf_json"])[0]
        assert pf(200, 5)["floor"] == 50            # 15% = 30 < 50: the higher one
        assert pf(1000, 5)["floor"] == 150          # 15% = 150 > 50
        assert pf(40, 5)["floor"] == 40             # never above the past-due amount
        assert pf(1000, 70)["floor"] == 1000        # the band accepts only the full amount
        SPEC["amounts"]["floor_combine"] = "min"
        assert pf(200, 5)["floor"] == 30
        assert pf(200, 5)["deadline"] == "2026-10-30"                                  # last business day of October
        assert pf(200, 5, now="2026-10-30T10:00")["deadline"] == "2026-11-30"          # today is that day: next month
    finally:
        SPEC = keep


def test_last_weekday_is_in_the_past():
    v = facts([{"product_id": "p1", "type": "car_loan", "past_due": 1250, "days_late": 14, "instalment_amount": 400}], now="2026-10-22T11:00")
    v["customer_date_text"] = "last Friday"
    run("resolve_date", v)
    assert (v["resolved_date"], v["date_status"]) == ("2026-10-16", "past")


def test_validate_reads_the_outcome_property_from_the_api_map():
    from extract import validate
    spec = json.load(open(ROOT / "fixtures" / "rehearsal-biz.spec.json")) if (ROOT / "fixtures" / "rehearsal-biz.spec.json").exists() else None
    if spec is None:
        return
    api = json.load(open(ROOT / "fixtures" / "rehearsal-biz.openapi.json"))
    assert not [p for p in validate(spec, api) if "not in API enum" in p]


def test_offsets_named_days_and_coming_weekday():
    # 2026-10-14 is a Wednesday. An offset is counted from today, never read as a day of the month.
    v = facts([{"product_id": "p1", "type": "car_loan", "past_due": 1250, "days_late": 14, "instalment_amount": 400}])
    for text, day, status in [("in two weeks", "2026-10-28", "ok"), ("in 3 days", "2026-10-17", "ok"), ("a week from today", "2026-10-21", "ok"),
                              ("two days from now", "2026-10-16", "ok"), ("in ten days", "2026-10-24", "ok"), ("this coming Monday", "2026-10-19", "ok"),
                              ("Christmas Eve", "2026-12-24", "ok"), ("new year's eve", "2026-12-31", "ok")]:
        w = dict(v, customer_date_text=text)
        run("resolve_date", w)
        assert w["resolved_date"] == day, (text, w["resolved_date"])


def test_floor_percent_per_product_type_and_text_in_a_field_name():
    spec = dict(SPEC, amounts=dict(SPEC["amounts"], floor_by_type={}, floor_percent_of_past_due=0, floor_fixed_amount=0,
                                   floor_percent_by_type={"car_loan": 30, "credit_card": 50}))
    def floor(sp, ty, due):
        v = {"now": NOW, "get_account_response.data.products": json.dumps([{"product_id": "p1", "type": ty, "past_due": due, "days_late": 14, "instalment_amount": 400}])}
        g = {"vars": v}
        exec(snippet("facts", libs=("calendar_lib", "dateparse_lib"), SPEC=sp), g)
        return float(json.loads(v["pf_json"])[0]["floor"])
    assert floor(spec, "car_loan", 1000) == 300 and floor(spec, "credit_card", 1000) == 500
    # a sentence where a field name belongs (an extraction slip) still gives the percentage
    slip = dict(spec, amounts=dict(spec["amounts"], floor_percent_by_type={}, floor_by_type={"car_loan": "30 percent of overdue_amount"}))
    assert floor(slip, "car_loan", 1000) == 300


def test_no_security_check_builds_without_identity_exits():
    from compile import compile_workflow
    from lint import lint
    api = json.load(open(ROOT / "fixtures" / "variant.openapi.json"))
    spec = json.load(open(ROOT / "fixtures" / "variant.spec.json"))
    spec["identity"] = dict(spec["identity"], questions=[])
    wf = compile_workflow(spec, api)
    assert lint(wf) == []
    assert "set_declined" not in wf["nodes"] and "end_failed" not in wf["nodes"]
    assert wf["nodes"]["mark_reached"]["transitions"][0]["target_node"] == "get_account"


def test_fallback_moves_optional_sections_into_the_prompt_rules():
    from fallback import compile_with_fallback, degrade
    spec = {"special_cases": [{"name": "x"}], "multi_product": {"a": 1}, "third_party": {"b": 2}, "residual_rules": ["r1"], "identity": {"questions": [1]}}
    d1 = degrade(spec, 1)
    assert d1["special_cases"] == [] and d1["multi_product"] == {"a": 1} and any(r.startswith("[special_cases]") for r in d1["residual_rules"]) and d1["residual_rules"][0] == "r1"
    assert d1["identity"] == spec["identity"] and spec["special_cases"]            # the core stays, the input is not changed
    calls = []
    def build(s):
        calls.append(len(s["special_cases"]))
        if s["special_cases"] or s["multi_product"]:
            raise RuntimeError("lint failed: x")
        return "wf"
    wf, used, level = compile_with_fallback(spec, build, log=lambda *_: None)
    assert (wf, level, calls) == ("wf", 2, [1, 0, 0]) and used["third_party"] == {"b": 2}
    def never(s):
        raise ValueError("no tool")
    try:
        compile_with_fallback(spec, never, log=lambda *_: None); assert False
    except ValueError as e:
        assert str(e) == "no tool"


def test_a_rule_the_code_cannot_express_goes_to_the_model():
    import copy, oracle
    # the oracle marks a dimension soft only when several situations still disagree and the judge blamed the spec
    res = {"O1": ["floor: code 400, test 120"], "O2": ["floor: code 300, test 150"], "O3": ["deadline: code 2026-10-29, test 2026-10-28"], "O4": []}
    cases = [{"id": "O1", "rule": "30 percent for credit cards"}, {"id": "O2", "rule": "50 percent for overdrafts"}, {"id": "O3", "rule": "within 7 days"}, {"id": "O4"}]
    soft = oracle.soft_dimensions(res, cases, {"O1": {"wrong": "spec"}, "O3": {"wrong": "spec"}})
    assert soft == {"floor": ["30 percent for credit cards", "50 percent for overdrafts"]}
    assert oracle.soft_dimensions(res, cases, {"O1": {"wrong": "test"}, "O2": {"wrong": "unclear"}}) == {}
    # a soft dimension: the computed value is a hint, the quoted rule is in the facts, the guard no longer blocks on it
    s = copy.deepcopy(SPEC)
    s["soft"] = {"floor": ["Smallest promise: 30 percent of the overdue amount."], "deadline": ["Pay within 7 calendar days."]}
    p = [{"product_id": "p1", "type": "car_loan", "past_due": 1250, "days_late": 14, "instalment_amount": 400}]
    v = {"now": NOW, "get_account_response.data.products": json.dumps(p)}
    code = snippet("facts", libs=("calendar_lib", "dateparse_lib"), SPEC=s)
    assert "{" not in code and "}" not in code
    exec(code, {"vars": v})
    assert "BANK RULE on amounts" in v["facts"] and "30 percent" in v["facts"] and "only a hint" in v["facts"]
    assert v["g_floor_p1"] == "0"
    assert "2026-11-20" in v["g_days_p1"] and "2026-10-17" not in v["g_days_p1"]      # far days allowed, weekends still out
    v["customer_date_text"] = "next Friday"
    exec(snippet("resolve_date", libs=("calendar_lib", "dateparse_lib"), SPEC=s), {"vars": v})
    assert "BANK RULE on dates" in v["date_verdict"] and "7 calendar days" in v["date_verdict"]
    # without soft nothing changes
    hard = facts(p)
    assert "BANK RULE" not in hard["facts"] and hard["g_floor_p1"] == "400" and "2026-11-20" not in hard["g_days_p1"]
