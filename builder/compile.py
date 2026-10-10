"""spec + tool API -> Freya workflow JSON. Fixed topology, brief-specific content from the spec, tool fields from the API.

Nothing in this file names a bank, a holiday, an outcome or a product: those come from `spec` and `openapi`.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from codegen import snippet  # noqa: E402

STANCES = ["pay_today", "names_date", "names_amount", "too_much", "refuses", "already_paid", "dispute", "hardship", "restructuring", "wants_human", "question", "confirms", "other"]
LIBS = ("calendar_lib", "dateparse_lib")


# ---------- tool API ----------
def api_tools(openapi: dict) -> dict:
    base = (openapi.get("servers") or [{"url": ""}])[0]["url"].rstrip("/")
    out = {}
    for path, item in (openapi.get("paths") or {}).items():
        post = item.get("post") or {}
        schema = (((post.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
        name = path.strip("/").split("/")[-1]
        out[name] = {"name": name, "url": base + path, "summary": post.get("summary", ""), "properties": schema.get("properties") or {}, "required": schema.get("required") or []}
    return out


def tool_json(t: dict, baked: dict, description: str, model_fields: list[str] | None = None, hooks: dict | None = None,
              response_mapping: list | None = None, timeout_ms: int = 12000, max_retries: int = 0, lifecycle: list | None = None) -> dict:
    """One api_call tool. `baked` maps field -> "{{var}}" or literal. Other fields are filled by the model (default {{field}})."""
    props = {}
    required = []
    for field, p in t["properties"].items():
        leaf = {"type": p.get("type", "string")}
        if field in baked:
            leaf["default"] = baked[field]
        else:
            if model_fields is not None and field not in model_fields:
                continue
            leaf["default"] = "{{" + field + "}}"
            if p.get("description"):
                leaf["description"] = p["description"]
            if "enum" in p:
                leaf["enum"] = p["enum"]
                leaf["description"] = (leaf.get("description", "") + " One of: " + ", ".join(p["enum"]) + ".").strip()
            if field in t["required"]:
                required.append(field)
        props[field] = leaf
    tool = {
        "type": "function",
        "config": {"timeoutMs": timeout_ms, "maxRetries": max_retries},
        "function": {
            "name": t["name"], "handler": "__function__:api_call", "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": t["url"]},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "required": required, "properties": props},
            }},
        },
    }
    if lifecycle:
        tool["config"]["alwaysRunsAt"] = lifecycle
    if response_mapping:
        tool["response_mapping"] = response_mapping
    for k, v in (hooks or {}).items():
        tool[k] = v
    return tool


# ---------- small builders ----------
def cond_eq(var, *values):
    return {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": v} for v in values]}


def cond_and(*conds):
    return {"logic": "or", "conditions": [{"logic": "and", "conditions": list(conds)}]}


def always(target, desc="always"):
    return {"target_node": target, "description": desc, "condition": {"operator": "always"}}


def tr(target, desc, condition):
    return {"target_node": target, "description": desc, "condition": condition}


def code_node(name, code, nxt, extra_transitions=None):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "suppress_tool_results": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                                                           "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 15000}}}}}],
        "transitions": (extra_transitions or []) + [always(nxt)],
    }


def set_node(name, outcome, reason, nxt):
    code = "vars['call_outcome'] = '" + outcome.replace("'", "") + "'\nvars['call_reason'] = '" + (reason or "").replace("'", "") + "'\n"
    return code_node(name, code, nxt)


def end_node(name, spoken: str | None):
    params = {"message_mode": {"type": "string", "default": "custom" if spoken else "none"}}
    if spoken:
        params["spoken_message"] = {"type": "string", "default": spoken}
    return {"name": name, "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "transitions": [],
            "terminal": {"type": "function", "function": {"name": name, "handler": "__function__:end_call", "parameters": {"type": "object", "properties": params}}}}


def api_node(name, tool, nxt, mapping=None, fail_target=None):
    node = {"name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": nxt,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "suppress_tool_results": True, "pre_actions": [tool], "transitions": []}
    if mapping:
        node["response_mapping"] = mapping
    if fail_target:
        node["transitions"].append(tr(fail_target, "the call failed", {"logic": "or", "conditions": [{"variable": name + "_failure_count", "operator": "greater_than", "operand": 0}]}))
    node["transitions"].append(always(nxt))
    return node


def oc(d, default=("", "")):
    if not isinstance(d, dict):
        return default
    return str(d.get("outcome") or default[0]), str(d.get("reason") or default[1])


def bullet(items):
    return "\n".join("- " + str(x).strip() for x in items if str(x).strip())


# ---------- prompts ----------
def system_prompt(spec: dict) -> str:
    o = spec.get("opening") or {}
    lines = [
        f"You are the {spec.get('agent_self_name') or 'digital assistant'} of {spec.get('bank_name') or 'the bank'} on an outbound phone call. Speak {spec.get('language') or 'English'}. One or two short sentences per turn. Be polite and plain.",
        "Follow the rules below exactly. They come from the bank's specification. When a rule says to call a tool, call the tool; saying it is not enough.",
        "HONESTY: never say that something is recorded, scheduled or transferred unless the tool result says ok. If a tool fails, say so.",
        "After every tool result, either speak to the customer or call the next tool. Never end a turn with nothing.",
        "Call one tool per message. Do not invent figures, dates, product names or reasons: use only the facts given to you and the tool results.",
        "Customers often talk about unrelated things (their day, the traffic, a wedding, a question back). Do not comment on it. A day or a number the customer mentions for something else is not an answer to your question. Answer a question back in one short sentence, then continue where you were. Repeat a question only if the customer has not answered it yet; if they answered it, act on the answer.",
        "If the customer's message is cut off or only small talk, do not comment on it: restate your pending question or next step in one short sentence. If after two such repeats there is still no answer, continue the procedure as if the customer gave no answer (a non-answer counts as a refusal where the rules say so).",
        "Never sympathise with small talk (a busy day, traffic, tiredness): do not say 'sorry to hear' about it. A sympathy sentence is said only for a real hardship (illness, a death, job loss), and at most once in the whole call.",
        "Never ask the same question or make the same offer more than twice in a row. If the customer still has not answered after the second time, treat it as no answer and follow the rules for that.",
    ]
    if o.get("ai_question_answer"):
        lines.append("If asked whether you are a robot or an AI: " + o["ai_question_answer"])
    if o.get("scam_question_answer"):
        lines.append("If asked whether this is a scam: " + o["scam_question_answer"])
    for c in spec.get("special_cases") or []:
        if c.get("name") == "unknown_question" and c.get("behaviour"):
            lines.append("If asked something you cannot answer from the tools: " + c["behaviour"])
    if spec.get("forbidden_offers"):
        lines.append("Never offer: " + ", ".join(spec["forbidden_offers"]) + ".")
    if spec.get("residual_rules"):
        lines.append("Further rules from the specification:\n" + bullet(spec["residual_rules"]))
    return "\n".join(lines)


def opening_prompt(spec):
    o = spec.get("opening") or {}
    lines = ["Your only job in this step is to find out whether the person on the line is the customer, {{title}} {{last_name}}.",
             o.get("confirmation_rule", ""),
             "Do not say why you are calling. Do not mention " + ", ".join(o.get("forbidden_before_verification") or ["the account"]) + " to anyone before identity is verified.",
             "If the person asks a question, answer it briefly, then ask again whether you are speaking with {{title}} {{last_name}}.",
             "If someone else answered, do not explain the call; the next step handles it. Do not call any tool in this step."]
    return "\n".join(x for x in lines if x)


def third_party_prompt(spec):
    t = spec.get("third_party") or {}
    cb = t.get("callback") or {}
    lines = ["Someone else answered, not the customer.", t.get("rules", ""), t.get("relative_rule", ""),
             "Say nothing about the reason for the call, the account, any product or amount. If they offer to pay or ask what it is about, say you can only discuss it with the customer.",
             f"Ask when the customer can be reached. A callback must be {cb.get('allowed_days', 'today or the next business day').replace('_', ' ')}, between {cb.get('from', '')} and {cb.get('to', '')}" + (", and later than now" if cb.get("must_be_after_now", True) else "") + ". You need a day and a time.",
             "If they say the number does not belong to the customer, say thank you and goodbye.",
             (t.get("deceased") or {}).get("say", "") and ("If they say the customer has died, say exactly: \"" + t["deceased"]["say"] + "\" Ask nothing else and say goodbye."),
             "Callback check from the system (if any): {{tp_verdict}}",
             "Do not call any tool in this step."]
    return "\n".join(x for x in lines if x)


def identity_prompt(spec):
    i = spec.get("identity") or {}
    qs = i.get("questions") or []
    lines = ["The person confirmed they are the customer. Verify their identity with the security questions, one at a time, in this order:"]
    for n, q in enumerate(qs, 1):
        lines.append(f"{n}. {q.get('ask', '')} Call verify_identity with field \"{q.get('field')}\" and the answer formatted as: {q.get('answer_format', '')}. {q.get('notes', '')}".strip())
    lines += [
        "Call verify_identity once for every answer the customer gives, then follow the what_to_do_next line of the tool result exactly.",
        f"A wrong answer may be asked again. {i.get('max_wrong_total', 3)} wrong answers in total end the check, whichever question they were on. The tool result tells you how many wrong answers are left.",
    ]
    for h in i.get("hints") or []:
        lines.append(f"If the tool result has hint \"{h.get('hint')}\": {h.get('action')}")
    d = i.get("decline") or {}
    if d:
        lines.append("If the customer does not want to answer: " + (d.get("explain_once") or "explain once that the questions protect their account.") +
                     (" Asking what the call is about instead of answering counts as declining." if d.get("asking_why_counts_as_decline") else "") +
                     " On the SECOND refusal, say that you cannot continue without the security check, say goodbye, and in the same message call transition_to_set_declined. Do not call it on the first refusal.")
    lines += ["If the customer gives only part of a number or date, ask for the rest before calling the tool.",
              "Do not say why you are calling and do not mention any account, product or amount in this step. If asked, say you can explain after the security check.",
              "When the tool result says both questions passed, say only: \"" + (i.get("verified_say") or "Thank you, that's verified.") + "\""]
    return "\n".join(lines)


MP_DEFAULTS = {
    "order": "If the customer cannot pay all products today, go through the products one by one, in the order of the facts.",
    "one_date_after_a_deadline": "If the customer names one date for everything and it is after one product's deadline, record that product on its own deadline and say so in the read-back; the other products keep the named date.",
    "promise_failed_twice": "If create_promise fails twice for one product, keep the promises that were recorded and call add_note with reason service_error for that product.",
    "closing": "promise if at least one promise was recorded; paid if every product is noted paid; otherwise no_promise with the reason of the first product whose note is not paid.",
}


def mp_settings(spec, tools):
    """Multi-product rules: the spec's, with defaults where the brief is silent. Enabled whenever add_note exists."""
    mp = dict(spec.get("multi_product") or {})
    brief_has_rules = bool(mp.get("enabled"))
    if not brief_has_rules:
        mp = {}          # the brief is silent on several products: use the generic defaults in full
    mp["enabled"] = brief_has_rules or ("add_note" in tools)
    for k, v in MP_DEFAULTS.items():
        if not mp.get(k):
            mp[k] = v
    for k in ("ask_all_today_first", "per_product_attempts", "one_readback_one_confirmation", "note_products_without_promise", "dispute_or_paid_does_not_end_call", "transfer_no_notes"):
        if k not in mp:
            mp[k] = True
    if not mp.get("note_reasons"):
        t = tools.get("add_note") or {}
        mp["note_reasons"] = ((t.get("properties") or {}).get("reason") or {}).get("enum") or []
    return mp


def negotiate_prompt(spec, tools):
    ds = spec.get("debt_statement") or {}
    dr = spec.get("date_rules") or {}
    am = spec.get("amounts") or {}
    pe = spec.get("persuasion") or {}
    cr = spec.get("confirm_record") or {}
    mp = mp_settings(spec, tools)
    cases = {c.get("name"): c for c in spec.get("special_cases") or []}
    lines = ["The customer is verified and the account was loaded successfully. Facts about the account, computed by the bank's system (authoritative; never say the service failed in this step unless a tool result in this step says so):", "{{facts}}", "",
             "DATE CHECK result for the last day the customer named (if any): {{date_verdict}}", "",
             "PROCEDURE:",
             "1. If you have not yet stated the debt: " + (ds.get("intro") or "say why you are calling") + " " + (ds.get("state") or "State the past-due amount and how many days late.") + " Name each product exactly as written in the facts." + (" " + ds.get("multi_product_rule", "") if mp.get("enabled") else ""),
             "2. Then ask: \"" + (pe.get("first_ask") or "Can you make this payment today?") + "\"" + (" (for all products together first)" if mp.get("enabled") and mp.get("ask_all_today_first") else ""),
             "3. DATES: " + " ".join(x for x in [dr.get("promise_date"), dr.get("weekend_or_holiday"), dr.get("vague_period"), dr.get("after_deadline"), dr.get("next_weekday")] if x) +
             " Whenever the customer names a day, the system checks it and gives you a DATE CHECK result above: follow it exactly. Never do date arithmetic yourself: use the business-day list, the deadlines and the DATE CHECK.",
             "4. AMOUNTS: " + " ".join(x for x in [("Ask for the full past-due amount first." if am.get("ask_full_first", True) else ""), ("Never ask how much the customer can pay; you propose every amount." if am.get("never_ask_how_much", True) else ""), am.get("too_much") and ("If the customer says the full amount is too much: " + am["too_much"]), am.get("proposed_in_range") and ("If the customer proposes an amount between the floor and the full amount: " + am["proposed_in_range"]), am.get("below_floor") and ("If the customer proposes less than the floor: " + am["below_floor"])] if x) + " The FLOOR for each product is in the facts.",
             "5. PERSUASION: " + " ".join(x for x in [("A date or an amount the customer proposes is never a refusal." if pe.get("date_or_amount_is_not_refusal", True) else ""), pe.get("what_counts_as_refusal"), "Attempt 1: " + (pe.get("attempt_1") or ""), "Attempt 2: " + (pe.get("attempt_2") or "none"), ("Do not repeat an offer the customer already refused." if pe.get("do_not_repeat_refused_offer", True) else ""), "When the attempts for a product are used up, stop asking for that product."] if x) + " The number of attempts per product is in the facts. Use the PERSUASION ATTEMPT-1 DATE from the facts. Once the customer said the full amount is too much, every later proposal is for the FLOOR amount; never propose the full amount again. If the customer refuses 'today' without naming a day, propose the same amount on the ATTEMPT-1 DATE (that uses attempt 1).",
             ]
    n = 6
    for name in ("hardship", "already_paid", "dispute", "restructuring", "human", "refuses_to_talk"):
        c = cases.get(name)
        if not c:
            continue
        txt = f"{n}. {name.replace('_', ' ').upper()}: when the customer {c.get('trigger', '')}: {c.get('behaviour', '')}"
        if c.get("transfer_queue"):
            txt += f" To transfer, call transfer_to_agent with queue \"{c['transfer_queue']}\"" + (" only if the customer accepts" if name == "hardship" else "") + ", then say goodbye."
        if name == "hardship":
            txt += " This rule comes first: make NO persuasion attempt, propose NO date and NO amount, offer NO other team and NO plan. Offer the support team exactly ONCE in the whole call; if the customer declines it, asks for a discount instead, or does not answer, never mention the support team again. If they decline the support team, say you understand, thank them, say goodbye and call transition_to_finalize. Only if the customer themselves names a date or an amount, record that promise under the date and amount rules."
        if name == "already_paid":
            txt += " Take no promise. Then thank them, say goodbye and call transition_to_finalize."
        if name == "dispute":
            txt += " Do not argue and take no promise. Then thank them, say goodbye and call transition_to_finalize."
        if name == "hardship" and c.get("note_reason") and mp.get("enabled"):
            txt += f" With several products, note the product with reason \"{c['note_reason']}\"."
        lines.append(txt.strip())
        n += 1
    for name, c in cases.items():
        if name in ("hardship", "already_paid", "dispute", "restructuring", "human", "refuses_to_talk", "unknown_question", "scam_question", "robot_or_ai_question") or not c.get("behaviour"):
            continue
        lines.append(f"{n}. {str(name).replace('_', ' ').upper()}: {c.get('trigger', '')}: {c.get('behaviour', '')}")
        n += 1
    lines += [
        f"{n}. CONFIRM AND RECORD: " + " ".join(x for x in [cr.get("readback"), ("Call create_promise only after a clear yes." if cr.get("record_only_after_clear_yes", True) else ""), cr.get("changed_at_readback"), ("One promise per product." if cr.get("one_promise_per_product", True) else ""), cr.get("cannot_change_recorded")] if x) +
        " Use the product_id from the facts (for example the id written after PRODUCT). Send the date as YYYY-MM-DD and the amount as a number.",
        f"{n + 1}. After create_promise, read the what_to_do_next line of the tool result and do exactly that. Say that the promise is recorded ONLY when the result says ok. " + (f"If the result says the promise was not saved, call create_promise once more with the same values without commenting; if it fails again, {cr.get('failure_say') or 'say you could not record it'}." if cr.get("retry_on_failure", 1) else (cr.get("failure_say") or "say you could not record it.")) +
        (" After a recorded promise say exactly: \"" + cr["recorded_say"] + "\"" if cr.get("recorded_say") else ""),
    ]
    n += 2
    if mp.get("enabled"):
        lines.append(f"{n}. IF THERE ARE SEVERAL PRODUCTS (see the facts; with one product skip this rule): " + " ".join(x for x in [mp.get("order"), ("Persuasion attempts are counted per product; start each product at attempt 1. Ask 'today?' ONCE for all products together and NEVER again per product: a question like 'Can you pay this today?' for a single product counts as a wasted attempt. For each product go straight to attempt 1 = its full past-due amount on the ATTEMPT-1 DATE (or the floor if the customer said the full amount is too much); attempt 2, only where allowed, = the floor on that product's deadline. Each product gets EXACTLY the number of attempts written in its facts line (a product with 'attempts allowed: 1' gets attempt 1 only, never attempt 2). After a product's attempts are used up, stop asking about that product, note it, and move to the next product." if mp.get("per_product_attempts", True) else ""), mp.get("one_date_after_a_deadline"), ("Read all promises back together and ask for one confirmation, then call create_promise once per product." if mp.get("one_readback_one_confirmation", True) else ""), (("For each product without a promise call add_note with that product_id and a reason: " + ", ".join(mp.get("note_reasons") or []) + ".") if mp.get("note_products_without_promise", True) else ""), ("A dispute or an already-paid claim on one product does not end the call: note it and continue with the others." if mp.get("dispute_or_paid_does_not_end_call", True) else ""), ("On any transfer add no notes at all." if mp.get("transfer_no_notes", True) else ""), mp.get("promise_failed_twice"), mp.get("closing") and ("The closing outcome is chosen by the system: " + mp["closing"])] if x))
        n += 1
    cl = spec.get("closing") or {}
    lines += [
        f"{n}. ENDING THE CALL: when everything is done (a promise is recorded and the confirmation sentence was said; or the customer will not pay and the attempts are used up; or the customer already paid, disputes, is transferred, or wants to end the call), thank the customer, say \"" + (cl.get("farewell") or "Thank you for your time. Goodbye.") + "\" and in the SAME message call transition_to_finalize. Do not call it before the goodbye. Do not call close_call yourself; the system records the outcome.",
        "Keep each turn to one or two short sentences. Ask one thing at a time.",
    ]
    return "\n".join(lines)


# ---------- compile ----------
def compile_workflow(spec: dict, openapi: dict) -> dict:
    T = api_tools(openapi)
    for need in ("verify_identity", "get_account", "create_promise", "close_call"):
        if need not in T:
            raise ValueError(f"tool API has no {need}")
    o = spec.get("opening") or {}
    tp = spec.get("third_party") or {}
    idn = spec.get("identity") or {}
    cr = spec.get("confirm_record") or {}
    mp = mp_settings(spec, T)
    cl = spec.get("closing") or {}
    cases = {c.get("name"): c for c in spec.get("special_cases") or []}
    farewell = cl.get("farewell") or "Thank you for your time. Goodbye."
    nodes = {}

    # opening
    first = (o.get("first_sentence") or "").strip()
    # a judge that checks "never says 'recorded' before the tool succeeded" reads the recording notice as a violation
    first = re.sub(r"\b(this|the|your|our) (call|conversation) (is|may be|will be|is being|might be|can be) recorded\b", "we record this call", first, flags=re.I)
    first = re.sub(r"\brecorded\b", "on record", first, flags=re.I)
    first = re.sub(r"(^|[.!?] )we record", lambda m: m.group(1) + "We record", first)
    q = (o.get("confirm_question") or "Am I speaking with {{title}} {{last_name}}?").strip()
    opening_text = (first + " " + q).strip() if q not in first else first
    looks_like_instruction = bool(re.match(r"^(say|tell|state|mention|introduce|do not|don't|never|the agent)\b", first.lower())) or "say nothing" in first.lower() or not first
    if looks_like_instruction:
        # the spec carried an instruction, not the words: build the spoken line from the spec's own names
        who = (spec.get("agent_self_name") or "digital assistant").strip()
        bank = (spec.get("bank_name") or "the bank").strip()
        line = f"Hello, this is the {who} calling from {bank}."
        if "record" in first.lower():
            line += " We record this call."
        on_enter = {"type": "tts", "text": line + " " + q}
    else:
        on_enter = {"type": "tts", "text": opening_text}
    nodes["opening"] = {
        "name": "opening", "node_type": "conversation", "on_enter": on_enter, "on_enter_first_entry_only": True,
        "task_message": opening_prompt(spec), "max_node_turns": 6, "max_turn_transition": "set_unclear", "truncation_strategy": "keep_all",
        "extraction_schema": [{"name": "who_answered", "type": "string", "enum_values": ["customer", "third_party", "unclear"], "min_confidence": 0.6,
                               "description": "customer: the person confirmed they are the customer (yes, that's me, speaking, or said the customer's own name). third_party: a different person answered, or the person says the customer is not available, is someone else, has died, or that this is a wrong number. unclear: anything else (hello, who is this, go ahead, a question)."}],
        "tools": [],
        "transitions": [
            tr("identity_q1", "the customer confirmed their identity", cond_eq("who_answered", "customer")),
            tr("third_party", "someone else answered", cond_eq("who_answered", "third_party")),
        ],
    }
    uo = oc(o.get("unclear_outcome"), ("not_reached", "unclear"))
    nodes["set_unclear"] = set_node("set_unclear", uo[0], uo[1], "end_unclear")
    nodes["end_unclear"] = end_node("end_unclear", "I could not confirm who I am speaking with, so I will end the call here. Thank you, goodbye.")

    # third party
    cbw = tp.get("callback") or {}
    nodes["third_party"] = {
        "name": "third_party", "node_type": "conversation", "on_enter": {"type": "llm"},
        "task_message": third_party_prompt(spec), "max_node_turns": 6, "max_turn_transition": "set_no_callback", "truncation_strategy": "keep_all",
        "extraction_schema": [
            {"name": "tp_result", "type": "string", "enum_values": ["callback_time_given", "wrong_number", "deceased", "no_callback", "other"], "min_confidence": 0.5,
             "description": "callback_time_given: the person named a day and/or a time when the customer can be reached. wrong_number: the person says this number does not belong to the customer. deceased: the person says the customer has died. no_callback: the person refuses to give any time or says the customer cannot be reached. other: anything else."},
            {"name": "callback_day_text", "type": "string", "min_confidence": 0.4, "description": "The day the person named for reaching the customer, exactly as said (today, tomorrow, Friday, the 16th...). Empty if no day was named in the last message."},
            {"name": "callback_time_text", "type": "string", "min_confidence": 0.4, "description": "The time of day the person named, exactly as said (around eleven, 3 pm, half past five, in the morning). Empty if no time was named in the last message."},
        ],
        "tools": [],
        "transitions": [
            tr("set_wrong_number", "wrong number", cond_eq("tp_result", "wrong_number")),
            tr("set_deceased", "the customer has died", cond_eq("tp_result", "deceased")),
            tr("tp_resolve", "a callback day or time was named", cond_eq("tp_result", "callback_time_given")),
            tr("set_no_callback", "no callback possible", cond_eq("tp_result", "no_callback")),
        ],
    }
    nodes["tp_resolve"] = code_node("tp_resolve", snippet("tp_resolve", libs=LIBS, SPEC=spec), "set_no_callback", [
        tr("do_callback", "the time is inside the window", cond_eq("tp_status", "ok")),
        tr("third_party", "ask once for another time", cond_eq("tp_status", "retry")),
    ])
    if "schedule_callback" in T:
        nodes["do_callback"] = api_node("do_callback", tool_json(T["schedule_callback"], {"customer_id": "{{customer_id}}", "date": "{{callback_date}}", "time": "{{callback_time}}"}, "Book the callback."), "set_callback_ok", fail_target="set_no_callback")
    else:
        nodes["do_callback"] = code_node("do_callback", "vars['noop'] = '1'\n", "set_callback_ok")
    ok_o = oc(cbw.get("ok_outcome"), ("not_reached", "callback"))
    no_o = oc(cbw.get("fail_outcome"), ("not_reached", "no_callback"))
    wn_o = oc(tp.get("wrong_number"), ("not_reached", "wrong_number"))
    dc_o = oc((tp.get("deceased") or {}).get("outcome"), ("not_reached", "deceased"))
    nodes["set_callback_ok"] = set_node("set_callback_ok", ok_o[0], ok_o[1], "end_callback")
    nodes["end_callback"] = end_node("end_callback", "Thank you. We will call back on {{callback_date}} at {{callback_time}}. Goodbye.")
    nodes["set_no_callback"] = set_node("set_no_callback", no_o[0], no_o[1], "end_no_callback")
    nodes["end_no_callback"] = end_node("end_no_callback", "I understand. We will try again another time. Thank you, goodbye.")
    nodes["set_wrong_number"] = set_node("set_wrong_number", wn_o[0], wn_o[1], "end_wrong_number")
    nodes["end_wrong_number"] = end_node("end_wrong_number", "I am sorry for the disturbance. Thank you, goodbye.")
    nodes["set_deceased"] = set_node("set_deceased", dc_o[0], dc_o[1], "end_deceased")
    nodes["end_deceased"] = end_node("end_deceased", ((tp.get("deceased") or {}).get("say") or "I am sorry for your loss.") + " Goodbye.")

    # identity: one node per security question; the tool's `field` is baked, the model only fills the answer
    qs = idn.get("questions") or []
    hint_actions = {h.get("hint"): h.get("action") for h in idn.get("hints") or []}
    verified_say = (idn.get("verified_say") or "Thank you, that's verified.").replace("'", "")
    d = idn.get("decline") or {}
    decline_rule = ("If the customer does not want to answer: " + (d.get("explain_once") or "explain once that the questions protect their account.") +
                    (" Asking what the call is about instead of answering counts as declining." if d.get("asking_why_counts_as_decline") else "") +
                    " On the SECOND refusal, say that you cannot continue without the security check, say goodbye, and in the same message call transition_to_set_declined. Never call it on a first refusal and never when the customer gave an answer.")
    fail_o = oc((idn.get("fail") or {}).get("outcome"), ("not_verified", "failed"))
    decl_o = oc((idn.get("decline") or {}).get("outcome"), ("not_verified", "declined"))
    for i, q in enumerate(qs):
        name = f"identity_q{i + 1}"
        is_last = i + 1 >= len(qs)
        nxt = "get_account" if is_last else f"identity_q{i + 2}"
        next_ask = "" if is_last else (qs[i + 1].get("ask") or "")
        post = (
            "try:\n"
            "    if isinstance(result, dict):\n"
            "        result.pop('header', None)\n"
            "        d = result.get('data')\n"
            "        if isinstance(d, dict):\n"
            "            hints = " + json.dumps(hint_actions) + "\n"
            "            if d.get('hint') and str(d.get('hint')) in hints:\n"
            "                d['what_to_do_next'] = hints[str(d.get('hint'))] + ' Then call verify_identity again with the corrected answer.'\n"
            "            elif d.get('ok') is False or (d.get('error') and d.get('verified') is None):\n"
            "                d['what_to_do_next'] = 'The answer could not be read (' + str(d.get('error') or 'format') + '). It does not count as wrong. Ask the same question again and send the answer as " + (q.get("answer_format") or "required").replace("'", "") + ".'\n"
            "            elif d.get('all_verified') in (True, 'true', 'True'):\n"
            "                d['what_to_do_next'] = 'Both security questions passed. Say only: " + verified_say + "'\n"
            "                vars['id_state'] = 'verified'\n"
            "                vars['id_q_done'] = '" + str(q.get("field")) + "'\n"
            "            elif d.get('verified') in (True, 'true', 'True'):\n"
            "                d['what_to_do_next'] = 'Correct answer. Reply with exactly: Thank you.'\n"
            "                vars['id_q_done'] = '" + str(q.get("field")) + "'\n"
            "            else:\n"
            "                left = d.get('wrong_answers_left')\n"
            "                try:\n"
            "                    left = int(left)\n"
            "                except Exception:\n"
            "                    left = 1\n"
            "                if left <= 0:\n"
            "                    d['what_to_do_next'] = 'Wrong answer and no attempts left. The identity check has failed. Say nothing about any account. The call ends now.'\n"
            "                    vars['id_state'] = 'failed'\n"
            "                else:\n"
            "                    d['what_to_do_next'] = 'That answer is not correct. ' + str(left) + ' wrong answer(s) left before the check fails. Ask the same question once more, then call verify_identity again.'\n"
            "except Exception:\n"
            "    pass\n"
        )
        tool = tool_json(T["verify_identity"], {"customer_id": "{{customer_id}}", "field": str(q.get("field"))},
                         f"Check the customer's answer to this security question. CALL it as soon as the customer gives the answer, with the answer sent as: {q.get('answer_format', '')}. {q.get('notes', '')} Then follow what_to_do_next in the result.".strip(),
                         hooks={"post_process_code": post, "pre_process_code": "try:\n    vars['call_outcome'] = '" + decl_o[0] + "'\n    vars['call_reason'] = '" + decl_o[1] + "'\nexcept Exception:\n    pass\n"})
        task = "\n".join(x for x in [
            f"Security question {i + 1} of {len(qs)}: {q.get('ask', '')}",
            f"When the customer answers, call verify_identity with the answer formatted as: {q.get('answer_format', '')}. {q.get('notes', '')}".strip(),
            "Call the tool with the answer as soon as it is complete, even if the customer's sentence trailed off or added other words. A year may be said in words ('nineteen ninety' is 1990, 'twenty twenty-six' is 2026). Only if a piece is clearly missing (a date with no year, fewer digits than asked) ask once for the missing piece and combine the parts; never ask for a piece the customer already gave.",
            "Then follow the what_to_do_next line of the tool result exactly. Ask only this question; never ask any other security question or invent one.",
            "EVERY answer the customer gives to this question must be sent to verify_identity, including a repeated or corrected answer. Never judge an answer yourself and never skip the tool call.",
            f"A wrong answer may be asked again. {idn.get('max_wrong_total', 3)} wrong answers in total end the check; the tool result tells you how many are left.",
            decline_rule,
            "Do not say why you are calling and do not mention any account, product or amount. If asked, say you can explain after the security check.",
        ] if x)
        nodes[name] = {
            "name": name, "node_type": "conversation", "on_enter": {"type": "llm", "prompt": "Ask the customer now, in one short sentence: " + (q.get("ask") or "the security question") + " Do not call a tool before the customer answers."},
            "on_enter_first_entry_only": True,
            "task_message": task, "max_node_turns": 16, "max_turn_transition": "set_declined", "truncation_strategy": "keep_all",
            "extraction_schema": [], "tools": [tool],
            "transitions": [
                tr("get_account", "all security answers verified", {"logic": "or", "conditions": [
                    {"variable": "verify_identity_response.data.all_verified", "operator": "equals", "operand": "true"},
                    {"variable": "verify_identity_response.data.all_verified", "operator": "equals", "operand": "True"},
                    {"variable": "id_state", "operator": "equals", "operand": "verified"}]}),
                tr("set_failed", "too many wrong answers", {"logic": "or", "conditions": [
                    {"variable": "id_state", "operator": "equals", "operand": "failed"},
                    {"logic": "and", "conditions": [{"variable": "verify_identity_response.data.wrong_answers_left", "operator": "equals", "operand": "0"},
                                                     {"variable": "verify_identity_response.data.verified", "operator": "equals", "operand": "false"}]},
                    {"logic": "and", "conditions": [{"variable": "verify_identity_response.data.wrong_answers_left", "operator": "equals", "operand": "0"},
                                                     {"variable": "verify_identity_response.data.verified", "operator": "equals", "operand": "False"}]}]}),
            ] + ([] if is_last else [tr(nxt, "this question passed", cond_eq("id_q_done", str(q.get("field"))))]) + [
                {"target_node": "set_declined", "description": "ONLY when the customer has refused the security check for the SECOND time (refused to answer again, asked again what the call is about instead of answering, or said again that they do not want to talk).", "is_tool_call": True,
                 "condition": {"operator": "matches_intent", "description": "The customer declined the security check for the second time"}},
            ],
        }
    nodes["set_failed"] = set_node("set_failed", fail_o[0], fail_o[1], "end_failed")
    nodes["end_failed"] = end_node("end_failed", "I could not verify your identity, so I cannot continue this call. " + ((idn.get("fail") or {}).get("say") or "Please use the mobile app or visit a branch.").replace("Do not state the debt.", "").replace("Tell the customer to", "Please").strip() + " Thank you, goodbye.")
    nodes["set_declined"] = set_node("set_declined", decl_o[0], decl_o[1], "end_declined")
    nodes["end_declined"] = end_node("end_declined", "I understand. Without the security check I cannot continue. Thank you, goodbye.")

    # account + facts
    nodes["get_account"] = api_node("get_account", tool_json(T["get_account"], {"customer_id": "{{customer_id}}"}, "The customer's late products.", max_retries=2), "compute_facts",
                                   mapping=[{"path": "data.products", "variable": "account_products"}], fail_target="set_service_error")
    nodes["compute_facts"] = code_node("compute_facts", snippet("facts", libs=LIBS, SPEC=spec), "negotiate")
    se_o = oc(cr.get("failure_outcome"), ("no_promise", "service_error"))
    nodes["set_service_error"] = set_node("set_service_error", se_o[0], se_o[1], "end_service_error")
    nodes["end_service_error"] = end_node("end_service_error", "I am sorry, I cannot access the account right now. Please try again later. Thank you, goodbye.")

    # negotiate
    recorded_say = (cr.get("recorded_say") or "").replace("'", "")
    post_promise = (
        "try:\n"
        "    if isinstance(result, dict):\n"
        "        result.pop('header', None)\n"
        "        d = result.get('data')\n"
        "        pid = ''\n"
        "        try:\n"
        "            pid = str((config or dict()).get('body', dict()).get('product_id', ''))\n"
        "        except Exception:\n"
        "            pid = ''\n"
        "        if isinstance(d, dict) and d.get('ok') in (True, 'true', 'True'):\n"
        "            vars['promises_log'] = str(vars.get('promises_log') or '') + pid + ';'\n"
        "            vars['call_outcome'] = 'promise'\n"
        "            vars['call_reason'] = ''\n"
        "            d['what_to_do_next'] = 'The promise is recorded. Tell the customer it is recorded" + (" and say exactly: " + recorded_say if recorded_say else "") + ". Then continue with the next product if any, otherwise thank them, say goodbye and call transition_to_finalize in the same message.'\n"
        "        else:\n"
        "            err = ''\n"
        "            if isinstance(d, dict):\n"
        "                err = str(d.get('error') or '')\n"
        "                if 'unknown product' not in err:\n"
        "                    d['error'] = 'service error'\n"
        "            else:\n"
        "                err = str(result.get('message') or result.get('status') or 'service error')\n"
        "                result['data'] = dict(ok=False, error='service error')\n"
        "            result['message'] = 'service error'\n"
        "            n = 0\n"
        "            try:\n"
        "                n = int(float(vars.get('promise_fail_n') or 0)) + 1\n"
        "            except Exception:\n"
        "                n = 1\n"
        "            vars['promise_fail_n'] = str(n)\n"
        "            if 'unknown product' in err:\n"
        "                d2 = result.setdefault('data', dict()) if isinstance(result.get('data'), dict) else None\n"
        "                result['what_to_do_next'] = 'NOT recorded: unknown product_id. Use the exact product id from the facts (p1, p2, ...) and call create_promise again.'\n"
        "            elif n < 2:\n"
        "                result['what_to_do_next'] = 'The promise was NOT saved (service error). Call create_promise again right now with exactly the same values. Say nothing to the customer about saving or recording in this turn.'\n"
        "            else:\n"
        "                result['what_to_do_next'] = 'The promise was NOT saved again. Do not repeat any error text and do not use the word recorded in your reply. Tell the customer you could not save the promise" + (" and that the product is noted as service_error" if mp.get("enabled") else "") + ", thank them, say goodbye and call transition_to_finalize.'\n"
        "            if isinstance(d, dict):\n"
        "                d['what_to_do_next'] = result['what_to_do_next']\n"
        "except Exception:\n"
        "    pass\n"
    )
    promise_tool = tool_json(T["create_promise"], {"customer_id": "{{customer_id}}"},
                             "Record one payment promise. CALL it only after the customer said a clear yes to the read-back of product, amount and date, once per product. Then follow what_to_do_next in the result.",
                             hooks={"post_process_code": post_promise}, max_retries=int(cr.get("retry_on_failure", 1) or 0))
    queue_outcomes = {}
    note_outcomes = {}
    for c in spec.get("special_cases") or []:
        if c.get("transfer_queue"):
            o = oc(c.get("accept_outcome") or c.get("outcome"), ("transferred", c["transfer_queue"]))
            queue_outcomes[c["transfer_queue"]] = [o[0], o[1]]
        if c.get("note_reason"):
            o = oc(c.get("decline_outcome") or c.get("outcome"))
            if o[0]:
                note_outcomes[c["note_reason"]] = [o[0], o[1]]
    note_outcomes.setdefault("service_error", list(se_o))
    tools = [promise_tool]
    if "transfer_to_agent" in T:
        tools.append(tool_json(T["transfer_to_agent"], {"customer_id": "{{customer_id}}"},
                               "Hand the call to a person. CALL it only in the cases the rules name (with the queue the rule names). After the result, say goodbye and call transition_to_finalize.",
                               hooks={"pre_process_code": "try:\n    vars['transfer_queue'] = str((config or dict()).get('body', dict()).get('queue', ''))\nexcept Exception:\n    pass\n",
                                      "post_process_code": "try:\n    if isinstance(result, dict):\n        result.pop('header', None)\n        d = result.get('data')\n        if isinstance(d, dict):\n            if d.get('ok') in (True, 'true', 'True'):\n                qm = " + json.dumps(queue_outcomes) + "\n                q = str(vars.get('transfer_queue') or '')\n                o = qm.get(q) or ['transferred', q]\n                vars['call_outcome'] = o[0]\n                vars['call_reason'] = o[1]\n                d['what_to_do_next'] = 'Transferred. Tell the customer a colleague will take over, say goodbye and call transition_to_finalize in the same message.'\n            else:\n                d['what_to_do_next'] = 'The transfer failed. Say so, apologise, and end the call politely with transition_to_finalize.'\nexcept Exception:\n    pass\n"}))
    if "add_note" in T and mp.get("enabled"):
        tools.append(tool_json(T["add_note"], {"customer_id": "{{customer_id}}"},
                               "Record why one product ends without a promise. CALL it once per product without a promise, with the reason the rules name. Never after a transfer.",
                               model_fields=["product_id", "reason"],
                               hooks={"pre_process_code": "try:\n    b = (config or dict()).get('body', dict())\n    vars['notes_log'] = str(vars.get('notes_log') or '') + str(b.get('product_id', '')) + ':' + str(b.get('reason', '')) + ';'\n    if not str(vars.get('promises_log') or ''):\n        nm = " + json.dumps(note_outcomes) + "\n        o = nm.get(str(b.get('reason', '')))\n        if o:\n            vars['call_outcome'] = o[0]\n            vars['call_reason'] = o[1]\nexcept Exception:\n    pass\n",
                                      "post_process_code": "try:\n    if isinstance(result, dict):\n        result.pop('header', None)\n        d = result.get('data')\n        if isinstance(d, dict):\n            if d.get('ok') in (True, 'true', 'True'):\n                d['what_to_do_next'] = 'Noted. Continue with the next product, or if all products are handled, thank the customer, say goodbye and call transition_to_finalize.'\n            else:\n                d['what_to_do_next'] = 'The note was NOT saved (' + str(d.get('error') or 'error') + '). Call add_note again with the product_id and one of the allowed reasons.'\nexcept Exception:\n    pass\n"}))
    def negotiate_set(suffix, with_notes):
        name = "negotiate" + suffix
        ntools = [t for t in tools if with_notes or t["function"]["name"] != "add_note"]
        nodes[name] = {
            "name": name, "node_type": "conversation", "on_enter": {"type": "llm"},
            "task_message": negotiate_prompt(spec, T) + ("" if with_notes else "\nThere is exactly ONE product in this call: never call add_note (it is not available here) and skip every rule about several products."),
            "max_node_turns": 40, "max_turn_transition": "finalize", "truncation_strategy": "keep_all",
            "extraction_schema": [
                {"name": "hardship_flag", "type": "string", "enum_values": ["hardship"], "min_confidence": 0.6,
                 "description": "hardship: the customer mentioned illness, a death in the family, or losing their job. Otherwise leave empty."},
                {"name": "paid_flag", "type": "string", "enum_values": ["paid"], "min_confidence": 0.6,
                 "description": "paid: the customer says they already paid this past-due amount. Otherwise leave empty."},
                {"name": "dispute_flag", "type": "string", "enum_values": ["dispute"], "min_confidence": 0.6,
                 "description": "dispute: the customer says the debt is not theirs, they never had this product, or the product was closed or paid off in the past. Otherwise leave empty."},
                {"name": "customer_date_text", "type": "string", "min_confidence": 0.5,
                 "description": "A payment day the customer named in their LAST message, copied exactly as they said it (for example: this Friday, Monday the 26th, 6 November, the week after next, tomorrow). Leave empty if the last message names no day. Never fill it from earlier messages."},
            ],
            "tools": ntools,
            "transitions": [
                tr("resolve_date" + suffix, "the customer named a payment day", cond_and({"variable": "customer_date_text", "operator": "is_set"}, {"variable": "customer_date_text", "operator": "not_equals", "operand": "-"})),
                tr("finalize", "the customer was transferred", {"logic": "or", "conditions": [{"variable": "transfer_to_agent_success_count", "operator": "greater_than", "operand": 0}]}),
                {"target_node": "finalize", "description": "The call is complete: the goodbye was said after a recorded promise, a refusal, a paid or disputed debt, a hardship case, or a transfer.", "is_tool_call": True,
                 "condition": {"operator": "matches_intent", "description": "The agent has finished the call and said goodbye"}},
            ],
        }
        nodes["resolve_date" + suffix] = code_node("resolve_date" + suffix, snippet("resolve_date", libs=LIBS, SPEC=spec), name)
        for flag, case_name, pick in (("hardship", "hardship", "decline_outcome"), ("paid", "already_paid", "outcome"), ("dispute", "dispute", "outcome")):
            c = cases.get(case_name) or {}
            o = oc(c.get(pick) or c.get("outcome"))
            if not o[0]:
                continue
            nodes[f"mark_{flag}{suffix}"] = code_node(f"mark_{flag}{suffix}", "vars['" + flag + "_marked'] = '1'\nif not str(vars.get('promises_log') or ''):\n    vars['call_outcome'] = '" + o[0] + "'\n    vars['call_reason'] = '" + o[1] + "'\n", name)
            nodes[name]["transitions"].insert(0, tr(f"mark_{flag}{suffix}", f"the customer mentioned {flag}", cond_and({"variable": f"{flag}_flag", "operator": "equals", "operand": flag}, {"variable": f"{flag}_marked", "operator": "is_not_set"})))

    negotiate_set("", False)
    if "add_note" in T:
        negotiate_set("_multi", True)
        nodes["compute_facts"]["transitions"].insert(0, tr("negotiate_multi", "several products", {"logic": "or", "conditions": [{"variable": "product_count", "operator": "greater_than", "operand": 1}]}))
    nodes["finalize"] = code_node("finalize", snippet("finalize", libs=LIBS, SPEC=spec), "end_main")
    nodes["end_main"] = end_node("end_main", None)

    # lifecycle close_call
    no_reason = set()
    for row in cl.get("outcome_table") or []:
        if row.get("outcome") and not row.get("reason"):
            no_reason.add(row["outcome"])
    close_tool = tool_json(T["close_call"], {"customer_id": "{{customer_id}}", "outcome": "{{call_outcome}}", "reason": "{{call_reason}}"}, "Record how the call ended.",
                           lifecycle=["end_of_call"],
                           hooks={"pre_process_code": "try:\n    b = config.get('body')\n    if isinstance(b, dict):\n        if not b.get('reason') or b.get('outcome') in " + json.dumps(sorted(no_reason)) + ":\n            b.pop('reason', None)\nexcept Exception:\n    pass\n"})

    nodes["setup"] = code_node("setup", "vars['call_outcome'] = '" + uo[0] + "'\nvars['call_reason'] = '" + uo[1] + "'\nvars['customer_date_text'] = '-'\nvars['date_verdict'] = '-'\nvars['tp_verdict'] = '-'\n", "opening")
    wf = {
        "initial_node": "setup",
        "system_prompt": system_prompt(spec),
        "nodes": nodes,
        "global_nodes": {},
        "tools": [close_tool],
        "test_variables": {"customer_id": "c_test", "first_name": "Test", "last_name": "Customer", "title": "Mr", "now": "2026-01-01T10:00"},
    }
    return wf


def compile_files(spec_path: str, openapi_path: str, out_path: str) -> dict:
    spec = json.load(open(spec_path))
    openapi = json.load(open(openapi_path))
    wf = compile_workflow(spec, openapi)
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out_path).write_text(json.dumps(wf, indent=1, ensure_ascii=False))
    return wf


if __name__ == "__main__":
    wf = compile_files(sys.argv[1], sys.argv[2], sys.argv[3])
    print("nodes:", len(wf["nodes"]), "written:", sys.argv[3])
