"""The case-folder road: request routing, computed values and result rules, on made-up data."""
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "builder"))

import casecompile as cc  # noqa: E402
from casespec import apply_edits, validate  # noqa: E402
from lint import lint  # noqa: E402

SPEC = json.loads((ROOT / "fixtures" / "case-parcel.spec.json").read_text())


def env(lib):
    e = {}
    exec("import json, re, datetime\n" + lib, e)
    return e


def test_route_request_path_query_body():
    r = env(cc.ROUTE_LIB)["route_request"]
    url, headers, body = r("GET", "https://x.test/a/{id}/b", [["id", "path", "string", "id"], ["lang", "query", "string", "lang"], ["n", "body", "integer", "box.count"], ["k", "header", "string", "X-Key"]],
                           {"id": "T 1/é", "lang": "en", "n": "3", "k": "abc", "other": "{{unset}}"})
    assert url == "https://x.test/a/T%201%2F%C3%A9/b?lang=en"
    assert body == {"box": {"count": 3}} and headers == {"X-Key": "abc"}


def test_unset_placeholder_is_not_sent():
    r = env(cc.ROUTE_LIB)["route_request"]
    url, _, body = r("POST", "https://x.test/p", [["a", "body", "string", "a"], ["b", "body", "string", "b"]], {"a": "{{a}}", "b": "v"})
    assert body == {"b": "v"}


def test_derive_and_rules():
    e = env(cc.RESULT_LIB)
    d = {"total": "1250.50", "paid": 250, "due": "2026-03-10", "items": [{"no": "1234567890", "amt": 5}, {"no": "0000002468", "amt": 0}]}
    e["derive"]([{"name": "left", "op": "sub", "a": "total", "b": "paid"}, {"name": "left_text", "op": "format_number", "a": "computed.left", "decimal": ",", "thousands": "."},
                 {"name": "days", "op": "days_from_today", "a": "due"}, {"name": "due_text", "op": "format_date", "a": "due", "pattern": "D MMMM YYYY", "months": ["m" + str(i) for i in range(1, 13)]},
                 {"name": "vs", "op": "compare", "a": "paid", "b": 300}, {"name": "tail", "op": "last_chars", "a": "no", "b": 4, "each": "items"}], d, datetime.date(2026, 3, 2))
    assert d["computed"] == {"left": 1000.5, "left_text": "1.000,50", "days": 8, "due_text": "10 m3 2026", "vs": "less"}
    assert [i["computed"]["tail"] for i in d["items"]] == ["7890", "2468"]
    rules = [{"status": "ok", "when": [{"path": "items", "op": "count_gt", "value": 1}, {"path": "computed.vs", "op": "eq", "value": "less"}], "then": "Say [[computed.left_text]] by [[computed.due_text]], first [[items.0.computed.tail]]."},
             {"status": 404, "then": "not found"}, {"status": "error", "then": "failed"}]
    assert e["guidance"](rules, 200, d, "ok", "err")[0] == "Say 1.000,50 by 10 m3 2026, first 7890."
    assert e["guidance"](rules, 404, {}, "ok", "err")[0] == "not found"
    assert e["guidance"](rules, 500, None, "ok", "err")[0] == "failed"
    assert e["guidance"]([], 200, d, "ok", "err")[0] == "ok" and e["guidance"]([], 503, d, "ok", "err")[0] == "err"
    assert e["guidance"]([{"status": "ok", "go": "bye", "say": "Total [[total]]."}], 200, d, "ok", "err") == ("", "bye", "Total 1250.50.")


def test_compile_parcel_case_is_clean_and_brace_free():
    assert validate(SPEC) == []
    wf = cc.compile_case(SPEC, "https://x.test")
    assert lint(wf) == []
    assert wf["initial_node"] == "setup" and "fetch_get_member" in wf["nodes"] and wf["nodes"]["main"]["node_type"] == "conversation"
    for n in wf["nodes"].values():
        for t in (n.get("tools") or []) + (n.get("pre_actions") or []):
            for hook in ("pre_process_code", "post_process_code"):
                assert "{" not in t.get(hook, "") and "}" not in t.get(hook, "")
    names = [t["function"]["name"] for t in wf["nodes"]["main"]["tools"]]
    assert names == ["get_parcel", "book_redelivery"]          # the start-of-call service is not offered to the model again
    assert [t["target_node"] for t in wf["nodes"]["main"]["transitions"]] == ["end_finished", "end_to_person"]


def test_post_hook_runs_like_the_platform():
    _, tool = cc.case_tool({"name": "t", "path": "/p", "method": "GET", "params": [], "derive": [{"name": "d", "op": "days_from_today", "a": "when"}],
                            "result_rules": [{"status": "ok", "when": [{"path": "computed.d", "op": "lt", "value": 0}], "then": "past"}, {"status": "ok", "then": "future"}]}, "https://x.test", [])
    result = {"status": "success", "status_code": 200, "data": {"when": "2026-01-01"}, "header": {"a": "b"}}
    v = {"today_iso": "2026-01-05"}
    exec(tool["post_process_code"], {"result": result, "vars": v})
    assert "header" not in result and result["data"]["what_to_do_next"] == "past" and v["t_state"] == "ok" and json.loads(v["t_result"])["computed"]["d"] == -4
    result = {"status": "error", "status_code": 500, "data": "broken"}
    exec(tool["post_process_code"], {"result": result, "vars": {}})
    assert result["data"]["result"] == "broken" and "NOT work" in result["data"]["what_to_do_next"]


def test_a_broken_spec_still_compiles():
    wf = cc.compile_case({"language": "X", "procedure": ["Say hello."], "tools": [{"name": "Bad Name!", "path": "/a/{id}", "params": [{"name": "id", "in": "nowhere"}, "junk"], "result_rules": "junk"}, "junk"], "endings": "junk"}, "https://x.test/")
    assert lint(wf) == [] and "end_done" in wf["nodes"]


def test_a_result_can_end_the_call_by_code():
    spec = json.loads(json.dumps(SPEC))
    spec["tools"][0]["result_rules"].insert(0, {"status": 404, "go": "to_person", "say": "No member [[code]]."})
    spec["tools"][1]["result_rules"].insert(0, {"status": "ok", "when": [{"path": "lost", "op": "eq", "value": True}], "go": "finished", "say": "Parcel [[no]] is lost."})
    wf = cc.compile_case(spec, "https://x.test")
    assert lint(wf) == []
    assert wf["nodes"]["fetch_get_member"]["transitions"][0]["target_node"] == "auto_to_person"
    assert wf["nodes"]["main"]["transitions"][0]["target_node"] == "auto_finished"
    assert wf["nodes"]["auto_finished"]["terminal"]["function"]["parameters"]["properties"]["spoken_message"]["default"] == "{{say_finished}}"
    tool = wf["nodes"]["main"]["tools"][0]
    v = {}
    result = {"status": "success", "status_code": 200, "data": {"lost": True, "no": "T9"}}
    exec(tool["post_process_code"], {"result": result, "vars": v})
    assert v["get_parcel_go"] == "finished" and v["say_finished"] == "Parcel T9 is lost."
    result = {"status": "success", "status_code": 200, "data": {"lost": False, "no": "T9"}}
    exec(tool["post_process_code"], {"result": result, "vars": v})
    assert v["get_parcel_go"] == ""


def test_rules_can_add_up():
    e = env(cc.RESULT_LIB)
    rules = [{"status": "ok", "when": [{"path": "a", "op": "gt", "value": 0}], "then": "A is [[a]].", "continue": True}, {"status": "ok", "when": [{"path": "b", "op": "gt", "value": 0}], "then": "B is [[b]].", "continue": True},
             {"status": "ok", "then": "Then ask."}, {"status": "ok", "then": "never reached"}]
    assert e["guidance"](rules, 200, {"a": 1, "b": 0}, "ok", "err")[0] == "A is 1. Then ask."
    assert e["guidance"](rules, 200, {"a": 1, "b": 2}, "ok", "err")[0] == "A is 1. B is 2. Then ask."


def test_whole_numbers_drop_their_decimals_when_asked():
    e = env(cc.RESULT_LIB)
    d = {"x": 31000.0, "y": 47.3}
    e["derive"]([{"name": "x", "op": "format_number", "a": "x", "decimal": ",", "thousands": ".", "trim": True}, {"name": "y", "op": "format_number", "a": "y", "decimal": ",", "thousands": ".", "trim": True}], d, None)
    assert d["computed"] == {"x": "31.000", "y": "47,30"}


def test_a_copied_value_is_snapped_to_the_real_one():
    e = env(cc.ROUTE_LIB)
    cands = e["collect"]({"items": [{"id": "AB00**77"}, {"id": "AB01**77"}, {"id": "AB00**58"}]}, "items.*.id")
    assert cands == ["AB00**77", "AB01**77", "AB00**58"]
    assert e["snap"]("AB00**58", cands) == "AB00**58"
    assert e["snap"]("AB00 ****** 58", cands) == "AB00**58"          # mask and spacing differ
    assert e["snap"]("0058", cands) == "AB00**58"                    # only the tail, and it is unique
    assert e["snap"]("77", cands) == "77"                            # ambiguous or too short: left alone
    _, tool = cc.case_tool({"name": "t2", "path": "/p", "method": "POST", "params": [{"name": "box.id", "in": "body", "source": "model", "from_result": {"tool": "t1", "path": "items.*.id"}}], "result_rules": []}, "https://x.test", [])
    config = {"body": {"box_id": "AB01 **77"}, "headers": {}}
    exec(tool["pre_process_code"], {"config": config, "vars": {"t1_json": json.dumps({"items": [{"id": "AB00**77"}, {"id": "AB01**77"}]})}})
    assert config["body"] == {"box": {"id": "AB01**77"}} and config["url"] == "https://x.test/p" and config["method"] == "POST"


def test_large_data_files_are_abridged_for_the_model():
    import casefolder
    rows = [{"id": i, "name": "n" * 50, "answers": {"a": {"status": 200, "body": {"k": "v" * 400}}, "b": {"status": 404, "body": {"k": "w" * 400}}}} for i in range(400)]
    text = json.dumps({"description": "made up", "rows": rows})
    assert len(text) > casefolder.BIG_DATA
    out = casefolder._big_json(text)
    assert len(out) < 90_000 and "abridged" in out and '"description": "made up"' in out
    cut = json.loads(out.split("\n", 1)[1])
    assert cut["rows"][0] == rows[0] and cut["rows"][1] == rows[1] and "more entries" in str(cut["rows"][-1])      # the first rows whole, the tail left out


def test_spoken_amounts_digits_and_lists():
    e = env(cc.RESULT_LIB)
    d = {"a": 3170.0, "b": 9321.5, "c": 2345678.91, "tail": "7006", "x": {"owes": 0}, "y": {"owes": 5}, "z": {"owes": 0}}
    e["derive"]([{"name": "a", "op": "amount_text", "a": "a", "unit": "krone", "subunit": "ore", "thousands": "."},
                 {"name": "b", "op": "amount_text", "a": "b", "unit": "krone", "subunit": "ore", "thousands": "."},
                 {"name": "c", "op": "amount_text", "a": "c", "unit": "krone", "subunit": "ore", "thousands": "."},
                 {"name": "tail", "op": "spell_digits", "a": "tail", "names": ["nul", "en", "to", "tre", "fire", "fem", "seks", "syv", "otte", "ni"]},
                 {"name": "clear", "op": "join_if", "sep": ", ", "last_sep": " og ", "items": [{"when": [{"path": "x.owes", "op": "le", "value": 0}], "text": "X"}, {"when": [{"path": "y.owes", "op": "le", "value": 0}], "text": "Y"},
                                                                                             {"when": [{"path": "z.owes", "op": "le", "value": 0}], "text": "Z"}, {"when": [{"path": "w", "op": "present"}, {"path": "w.owes", "op": "le", "value": 0}], "text": "W"}]},
                 {"name": "case", "op": "first_of", "default": "none", "items": [{"when": [{"path": "y.owes", "op": "gt", "value": 9}], "text": "big"}, {"when": [{"path": "y.owes", "op": "gt", "value": 0}], "text": "small [[y.owes]]"}]}], d, None)
    assert d["computed"] == {"a": "3.170 krone", "b": "9.321 krone 50 ore", "c": "2.345.678 krone 91 ore", "tail": "syv nul nul seks", "clear": "X og Z", "case": "small 5"}


def test_a_masked_value_is_matched_position_by_position():
    e = env(cc.ROUTE_LIB)
    cands = ["310000******6839", "310090******6839"]
    assert e["snap"]("3100901234566839", cands) == "310090******6839"
    assert e["snap"]("3100 0000 0000 6839", cands) == "310000******6839"


def test_a_rule_can_read_another_services_answer():
    _, tool = cc.case_tool({"name": "second", "path": "/p", "method": "POST", "params": [], "derive": [{"name": "who", "op": "first_of", "default": "nobody", "items": [{"when": [{"path": "@First Lookup.owner", "op": "nonempty"}], "text": "[[@first_lookup.owner]]"}]}],
                            "result_rules": [{"status": "ok", "when": [{"path": "@first_lookup.items", "op": "count_gt", "value": 1}], "then": "Several, owner [[computed.who]]."}, {"status": "ok", "then": "One."}]}, "https://x.test", [])
    v = {"first_lookup_json": json.dumps({"owner": "Kim", "items": [1, 2]})}
    result = {"status": "success", "status_code": 200, "data": {}}
    exec(tool["post_process_code"], {"result": result, "vars": v})
    assert result["data"]["what_to_do_next"] == "Several, owner Kim."
    result = {"status": "success", "status_code": 200, "data": {}}
    exec(tool["post_process_code"], {"result": result, "vars": {}})
    assert result["data"]["what_to_do_next"] == "One."


def test_edits_change_only_what_they_name():
    spec = json.loads(json.dumps(SPEC))
    out = apply_edits(spec, [
        {"op": "set", "path": "tools/get_parcel/result_rules", "value": [{"status": "ok", "then": "new"}]},
        {"op": "set", "path": "tools/book_redelivery/timeout_seconds", "value": 20},
        {"op": "append", "path": "rules", "value": "one more"},
        {"op": "insert", "path": "procedure/Second attempt", "value": {"title": "Between", "do": "x"}},
        {"op": "delete", "path": "endings/to_person"},
        {"op": "set", "path": "procedure/Find the parcel/do", "value": "changed"},
        {"op": "set", "path": "nowhere/deep/thing", "value": 1},
        {"op": "delete", "path": "tools/no_such_tool"},
    ], log=lambda line: None)
    assert out["tools"][1]["result_rules"] == [{"status": "ok", "then": "new"}] and out["tools"][2]["timeout_seconds"] == 20
    assert out["rules"][-1] == "one more" and [p["title"] for p in out["procedure"]] == ["Find the parcel", "Between", "Second attempt"]
    assert [e["id"] for e in out["endings"]] == ["finished"] and out["procedure"][0]["do"] == "changed" and out["nowhere"] == {"deep": {"thing": 1}}
    assert spec == SPEC and out["tools"][0] == SPEC["tools"][0]          # the original is untouched, the rest unchanged


def test_duplicates_in_a_list_are_counted_by_code():
    e = env(cc.RESULT_LIB)
    d = {"items": [{"kind": "A", "tail": "11"}, {"kind": "A", "tail": "11"}, {"kind": "a ", "tail": "22"}, {"kind": "B", "tail": "22"}]}
    e["derive"]([{"name": "same_kind", "op": "count_same", "each": "items", "a": "kind"}, {"name": "same_both", "op": "count_same", "each": "items", "a": ["kind", "tail"]},
                 {"name": "how", "op": "first_of", "each": "items", "default": "ask more", "items": [{"when": [{"path": "computed.same_kind", "op": "eq", "value": 1}], "text": "take it"}, {"when": [{"path": "computed.same_both", "op": "eq", "value": 1}], "text": "ask tail"}]}], d, None)
    assert [(i["computed"]["same_kind"], i["computed"]["same_both"], i["computed"]["how"]) for i in d["items"]] == [(3, 2, "ask more"), (3, 2, "ask more"), (3, 1, "ask tail"), (1, 1, "take it")]
    e["derive"]([{"name": "guide", "op": "lines", "a": "items", "template": "[[kind]]/[[tail]]: [[computed.how]]", "sep": "; "}], d, None)
    assert d["computed"]["guide"] == "A/11: ask more; A/11: ask more; a /22: ask tail; B/22: take it"


def test_error_answers_are_routed_by_the_engine_and_named_in_the_prompt():
    spec = json.loads(json.dumps(SPEC))
    spec["tools"][0]["result_rules"] = [{"status": 404, "when": [{"path": "code", "op": "eq", "value": "NONE_3"}], "go": "to_person", "say": "No member on file."}, {"status": "error", "go": "finished", "say": "Technical problem."}, {"status": "ok", "then": "fine"}]
    spec["tools"][1]["result_rules"] = [{"status": 404, "when": [{"path": "code", "op": "eq", "value": "GONE_7"}], "then": "Say the parcel is gone."}, {"status": [404, 410], "then": "Ask for the number again."},
                                        {"status": "error", "go": "to_person"}, {"status": "ok", "then": "fine"}]
    wf = cc.compile_case(spec, "https://x.test")
    assert lint(wf) == []
    f = [t for t in wf["nodes"]["fetch_get_member"]["transitions"] if t["target_node"].startswith("err_")]
    assert [t["target_node"] for t in f] == ["err_get_member_0", "err_get_member_1"]          # one transition per rule, in rule order
    assert f[0]["condition"]["conditions"] == [{"logic": "and", "conditions": [{"variable": "fetch_get_member_status_code", "operator": "equals", "operand": "404"}, {"variable": "fetch_get_member_response.message", "operator": "contains", "operand": "NONE_3"}]}]
    assert f[1]["condition"]["conditions"] == [{"logic": "and", "conditions": [{"variable": "fetch_get_member_response.status", "operator": "equals", "operand": "error"}]}]
    assert wf["nodes"]["fetch_get_member"]["transitions"][-1]["condition"] == {"operator": "always"}
    assert wf["nodes"]["err_get_member_0"]["terminal"]["function"]["parameters"]["properties"]["spoken_message"]["default"] == "No member on file."
    m = wf["nodes"]["main"]
    e = [t for t in m["transitions"] if t["target_node"].startswith("err_get_parcel")]
    assert len(e) == 1 and e[0]["condition"]["conditions"][0]["conditions"] == [{"variable": "get_parcel_response.status", "operator": "equals", "operand": "error"},
                                                                                  {"variable": "get_parcel_status_code", "operator": "not_equals", "operand": "404"}, {"variable": "get_parcel_status_code", "operator": "not_equals", "operand": "410"}]
    assert wf["nodes"][e[0]["target_node"]]["terminal"]["function"]["parameters"]["properties"]["spoken_message"]["default"] == "I am handing you over to a colleague now."
    assert "IF A SERVICE CALL FAILS" in m["task_message"] and "get_parcel fails with status 404 and the answer contains GONE_7: Say the parcel is gone." in m["task_message"] and "Ask for the number again." in m["task_message"]


def test_look_alike_records_are_told_apart_by_code():
    e = env(cc.ROUTE_LIB)
    recs = [{"id": "310000******6839", "kind": "Blue"}, {"id": "310090******6839", "kind": "Blue"}, {"id": "310000******7001", "kind": "Blue"}, {"id": "310000******5550", "kind": "Red"}]
    n = lambda chosen, said: (lambda st, m: (st, [r["id"] for r in m]))(*e["narrow"](chosen, said, recs, "id", "kind"))
    assert n("310000******5550", "") == ("ok", ["310000******5550"])                                   # a unique name needs no digits
    assert n("310000******6839", "")[0] == "many" and len(n("310000******6839", "")[1]) == 3            # three share the name
    assert n("310000******6839", "7001") == ("one", ["310000******7001"])                               # the digits decide, not the pick
    assert n("310000******6839", "6839") == ("many", ["310000******6839", "310090******6839"])
    assert n("310000******6839", "126839")[0] == "many"                                                 # the masked part fits anything
    assert n("310000******6839", "3100901234566839") == ("one", ["310090******6839"])                   # the whole number settles it
    assert n("310000******6839", "9991") == ("none", [])                                                # digits that fit no record
    assert n("310000******6839", "6839" + "126839" + "3100901234566839") == ("one", ["310090******6839"])   # answers joined by mistake: the last whole number counts
    assert e["narrow"]("x", "6839", recs[:1], "id", "kind")[0] == "ok"                                  # a single record is never held back


def test_an_unsettled_choice_reads_nothing_and_tells_the_agent_what_to_ask():
    spec = json.loads(json.dumps(SPEC))
    spec["tools"][1]["params"][0]["from_result"] = {"tool": "get_member", "path": "parcels.*.no", "tell_apart": {"list": "parcels", "value": "no", "label": "kind",
        "steps": [{"digits_up_to": 0, "then": "Ask the last three digits of the [[label]] parcel."}, {"digits_up_to": 3, "then": "[[count]] parcels end in [[digits]]: ask for the whole number."}], "no_match": "Say no parcel has these digits."}}
    wf = cc.compile_case(spec, "https://x.test")
    assert lint(wf) == []
    tool = wf["nodes"]["main"]["tools"][0]
    assert "digits_said" in tool["function"]["parameters"]["properties"]["body"]["properties"]
    listing = json.dumps({"parcels": [{"no": "77**123", "kind": "Box"}, {"no": "78**123", "kind": "Box"}, {"no": "77**999", "kind": "Tube"}]})
    def call(body):
        v = {"get_member_json": listing, "memberId": "M-1"}
        config = {"body": dict(body), "headers": {}}
        exec(tool["pre_process_code"], {"config": config, "vars": v})
        result = {"status": "success", "status_code": 200, "data": {"anything": 1}}
        exec(tool["post_process_code"], {"result": result, "vars": v})
        return config, result["data"], v
    config, data, v = call({"trackingno": "77**123", "digits_said": ""})
    assert config["url"] == "https://x.test/_echo/members/M-1" and config["method"] == "GET"            # the earlier read is repeated, the parcel is not read
    assert data["what_to_do_next"] == "Ask the last three digits of the Box parcel." and v["get_parcel_blocked"] == ""
    config, data, v = call({"trackingno": "77**123", "digits_said": "123"})
    assert data["what_to_do_next"] == "2 parcels end in 123: ask for the whole number."
    config, data, v = call({"trackingno": "77**123", "digits_said": "7855123"})
    assert config["url"].startswith("https://x.test/_echo/parcels/78%2A%2A123") and "not_read" not in data        # the digits picked the other record
    config, data, v = call({"trackingno": "77**999", "digits_said": ""})
    assert config["url"].startswith("https://x.test/_echo/parcels/77") and "not_read" not in data          # a unique name goes straight through
    config, data, v = call({"trackingno": "77**123", "digits_said": "555"})
    assert data["what_to_do_next"] == "Say no parcel has these digits."
