"""The case-folder road: request routing, computed values and result rules, on made-up data."""
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "builder"))

import casecompile as cc  # noqa: E402
from casespec import validate  # noqa: E402
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
    d = {"total": "1250.50", "paid": 250, "due": "2026-03-10", "items": [{"no": "1234567890", "amt": 5}, {"no": "0000001111", "amt": 0}]}
    e["derive"]([{"name": "left", "op": "sub", "a": "total", "b": "paid"}, {"name": "left_text", "op": "format_number", "a": "computed.left", "decimal": ",", "thousands": "."},
                 {"name": "days", "op": "days_from_today", "a": "due"}, {"name": "due_text", "op": "format_date", "a": "due", "pattern": "D MMMM YYYY", "months": ["m" + str(i) for i in range(1, 13)]},
                 {"name": "vs", "op": "compare", "a": "paid", "b": 300}, {"name": "tail", "op": "last_chars", "a": "no", "b": 4, "each": "items"}], d, datetime.date(2026, 3, 2))
    assert d["computed"] == {"left": 1000.5, "left_text": "1.000,50", "days": 8, "due_text": "10 m3 2026", "vs": "less"}
    assert [i["computed"]["tail"] for i in d["items"]] == ["7890", "1111"]
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
    result = {"status": "error", "status_code": 500, "data": "oops"}
    exec(tool["post_process_code"], {"result": result, "vars": {}})
    assert result["data"]["result"] == "oops" and "NOT work" in result["data"]["what_to_do_next"]


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
    d = {"x": 12000.0, "y": 85.2}
    e["derive"]([{"name": "x", "op": "format_number", "a": "x", "decimal": ",", "thousands": ".", "trim": True}, {"name": "y", "op": "format_number", "a": "y", "decimal": ",", "thousands": ".", "trim": True}], d, None)
    assert d["computed"] == {"x": "12.000", "y": "85,20"}


def test_a_copied_value_is_snapped_to_the_real_one():
    e = env(cc.ROUTE_LIB)
    cands = e["collect"]({"items": [{"id": "AB00**77"}, {"id": "AB01**77"}, {"id": "AB00**12"}]}, "items.*.id")
    assert cands == ["AB00**77", "AB01**77", "AB00**12"]
    assert e["snap"]("AB00**12", cands) == "AB00**12"
    assert e["snap"]("AB00 ****** 12", cands) == "AB00**12"          # mask and spacing differ
    assert e["snap"]("0012", cands) == "AB00**12"                    # only the tail, and it is unique
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
    d = {"a": 2500.0, "b": 7666.5, "c": 1234567.89, "tail": "1003", "x": {"owes": 0}, "y": {"owes": 5}, "z": {"owes": 0}}
    e["derive"]([{"name": "a", "op": "amount_text", "a": "a", "unit": "krone", "subunit": "ore", "thousands": "."},
                 {"name": "b", "op": "amount_text", "a": "b", "unit": "krone", "subunit": "ore", "thousands": "."},
                 {"name": "c", "op": "amount_text", "a": "c", "unit": "krone", "subunit": "ore", "thousands": "."},
                 {"name": "tail", "op": "spell_digits", "a": "tail", "names": ["nul", "en", "to", "tre", "fire", "fem", "seks", "syv", "otte", "ni"]},
                 {"name": "clear", "op": "join_if", "sep": ", ", "last_sep": " og ", "items": [{"when": [{"path": "x.owes", "op": "le", "value": 0}], "text": "X"}, {"when": [{"path": "y.owes", "op": "le", "value": 0}], "text": "Y"},
                                                                                             {"when": [{"path": "z.owes", "op": "le", "value": 0}], "text": "Z"}, {"when": [{"path": "w", "op": "present"}, {"path": "w.owes", "op": "le", "value": 0}], "text": "W"}]},
                 {"name": "case", "op": "first_of", "default": "none", "items": [{"when": [{"path": "y.owes", "op": "gt", "value": 9}], "text": "big"}, {"when": [{"path": "y.owes", "op": "gt", "value": 0}], "text": "small [[y.owes]]"}]}], d, None)
    assert d["computed"] == {"a": "2.500 krone", "b": "7.666 krone 50 ore", "c": "1.234.567 krone 89 ore", "tail": "en nul nul tre", "clear": "X og Z", "case": "small 5"}


def test_a_masked_value_is_matched_position_by_position():
    e = env(cc.ROUTE_LIB)
    cands = ["AB0000******4253", "AB0010******4253"]
    assert e["snap"]("AB00101234564253", cands) == "AB0010******4253"
    assert e["snap"]("AB00 0000 0000 4253", cands) == "AB0000******4253"
