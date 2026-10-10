"""Names of the tool API, read from the tool API file. Nothing here knows a field name in advance:
each role (the amount of a promise, the list of products, the 'verified' flag...) is matched to the property
the API file actually declares. The spec's `api` section (filled by the model) wins when it names a real property;
otherwise a name-pattern match is used; otherwise the conventional name."""
from __future__ import annotations

import re


def _body(openapi, tool):
    for path, item in (openapi.get("paths") or {}).items():
        if path.strip("/").split("/")[-1] == tool:
            return ((((item.get("post") or {}).get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
    return {}


def _resp(openapi, tool):
    for path, item in (openapi.get("paths") or {}).items():
        if path.strip("/").split("/")[-1] == tool:
            return (((((item.get("post") or {}).get("responses") or {}).get("200") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
    return {}


def _pick(props, patterns, exclude=()):
    for pat in patterns:
        for name in props:
            if name not in exclude and re.search(pat, name, re.I):
                return name
    return None


CUSTOMER = [r"^customer_id$", r"customer", r"client", r"debtor", r"holder", r"party"]
ROLES = {   # tool -> role -> name patterns, most specific first
    "verify_identity": {"answer": [r"^answer$", r"answer", r"reply", r"value", r"response", r"input", r"text"]},
    "create_promise": {"product_id": [r"^product_id$", r"product", r"account", r"contract", r"item", r"^id$"], "amount": [r"^amount$", r"amount", r"sum", r"value"], "date": [r"^date$", r"date", r"day", r"when", r"due"]},
    "add_note": {"product_id": [r"^product_id$", r"product", r"account", r"contract", r"item", r"^id$"], "reason": [r"^reason$", r"reason", r"code", r"type", r"category"]},
    "schedule_callback": {"date": [r"^date$", r"date", r"day"], "time": [r"^time$", r"time", r"hour", r"slot"]},
    "transfer_to_agent": {"queue": [r"^queue$", r"queue", r"team", r"dep", r"dest", r"target", r"skill"]},
    "close_call": {"outcome": [r"^outcome$", r"outcome", r"result", r"status", r"disposition"], "reason": [r"^reason$", r"reason", r"sub", r"detail", r"code"]},
}
RESP = {
    "verify_identity": {"verified": [r"^verified$", r"^correct$", r"^match", r"^valid$", r"^passed?$", r"verified", r"correct"],
                        "all_verified": [r"^all_verified$", r"all_", r"fully", r"complete", r"identity_(verified|confirmed)", r"done"],
                        "wrong_left": [r"wrong_answers_left", r"left", r"remaining"],
                        "hint": [r"^hint$", r"hint", r"suggest"]},
}
PRODUCT = {"product_id": [r"^product_id$", r"product_?id", r"^id$", r"account_?id", r"contract", r"ref"],
           "type": [r"^type$", r"product_?type", r"kind", r"category"],
           "past_due": [r"^past_due$", r"past_?due", r"overdue", r"arrears", r"amount_?due", r"outstanding", r"^due"],
           "days_late": [r"^days_late$", r"days_?(late|overdue|past|in_arrears|arrears)", r"dpd", r"days"]}


def heuristic(openapi: dict) -> dict:
    a = {"tools": {}}
    for tool in ("verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent", "close_call"):
        body = (_body(openapi, tool).get("properties") or {})
        if not body and not _resp(openapi, tool):
            continue
        t = {"customer": _pick(body, CUSTOMER) or "customer_id"}
        for role, pats in (ROLES.get(tool) or {}).items():
            t[role] = _pick(body, pats, exclude=(t["customer"],) + tuple(v for v in t.values() if isinstance(v, str))) or ""
        # roles no pattern matched: give them the body properties nobody claimed, in declaration order
        free = [n for n in body if n not in t.values()]
        for role in (ROLES.get(tool) or {}):
            if not t[role]:
                t[role] = free.pop(0) if free else role
        if tool == "verify_identity":
            enum_props = [n for n, p in body.items() if "enum" in p and n != t["customer"]]
            t["field"] = enum_props[0] if enum_props else (_pick(body, [r"^field$", r"field", r"question", r"type", r"kind"], exclude=(t["customer"], t["answer"])) or "field")
        if tool == "transfer_to_agent":
            enum_props = [n for n, p in body.items() if "enum" in p and n != t["customer"]]
            if enum_props:
                t["queue"] = enum_props[0]
        if tool == "close_call":
            enum_props = [n for n, p in body.items() if "enum" in p and n != t["customer"]]
            if enum_props and t["outcome"] not in body:
                t["outcome"] = enum_props[0]
        resp = (_resp(openapi, tool).get("properties") or {})
        for role, pats in (RESP.get(tool) or {}).items():
            ex = (t.get("all_verified"),) if role == "verified" else ()
            t[role] = _pick(resp, pats, exclude=tuple(x for x in ex if x))
        if tool == "verify_identity":      # 'verified' must not be the all-verified flag
            t["all_verified"] = _pick(resp, RESP[tool]["all_verified"])
            t["verified"] = _pick(resp, RESP[tool]["verified"], exclude=tuple(x for x in (t["all_verified"],) if x)) or "verified"
        if tool == "get_account":
            arr = [n for n, p in resp.items() if p.get("type") == "array"]
            t["products"] = arr[0] if arr else "products"
            items = ((resp.get(t["products"]) or {}).get("items") or {}).get("properties") or {}
            for role, pats in PRODUCT.items():
                t[role] = _pick(items, pats) or role
            t["product_fields"] = list(items.keys())
        a["tools"][tool] = t
    any_resp = {}
    for tool in a["tools"]:
        any_resp.update(_resp(openapi, tool).get("properties") or {})
    a["ok"] = _pick(any_resp, [r"^ok$", r"^success$", r"succeeded", r"^done$"]) or "ok"
    a["error"] = _pick(any_resp, [r"^error$", r"error", r"problem", r"message", r"detail", r"fault", r"reason"]) or "error"
    outcomes = ((_body(openapi, "close_call").get("properties") or {}).get((a["tools"].get("close_call") or {}).get("outcome", "outcome")) or {}).get("enum") or []
    a["outcomes"] = outcomes
    a["promise_outcome"] = next((o for o in outcomes if re.search(r"promis|ptp|commit|pledge", o, re.I)), "promise")
    a["transfer_outcome"] = next((o for o in outcomes if re.search(r"transfer|hand|escalat|forward|rout", o, re.I)), "transferred")
    # the call variable with the customer id is, unless the brief says otherwise, named like the tools' customer field
    a["call_vars"] = {"customer_id": (a["tools"].get("verify_identity") or {}).get("customer") or "customer_id", "now": "now"}
    return a


def resolve(spec: dict, openapi: dict) -> dict:
    """The API map used by the compiler: the model's `api` section where it names real properties, else the heuristic."""
    a = heuristic(openapi)
    m = (spec.get("api") or {})
    for tool, t in a["tools"].items():
        body = (_body(openapi, tool).get("properties") or {})
        resp = (_resp(openapi, tool).get("properties") or {})
        items = ((resp.get(t.get("products", "")) or {}).get("items") or {}).get("properties") or {}
        given = ((m.get("tools") or {}).get(tool) or {})
        for role, name in given.items():
            if not isinstance(name, str) or not name or role == "product_fields":
                continue
            if role == "products":
                if (resp.get(name) or {}).get("type") == "array":
                    t["products"] = name
                    items = (resp[name].get("items") or {}).get("properties") or {}
                    t["product_fields"] = list(items.keys())
            elif name in body or name in resp or name in items:
                t[role] = name
    for k in ("promise_outcome", "transfer_outcome"):
        v = m.get(k)
        if isinstance(v, str) and v and (not a["outcomes"] or v in a["outcomes"]):
            a[k] = v
    cv = m.get("call_vars") or {}
    for k in ("customer_id", "now"):
        if isinstance(cv.get(k), str) and re.match(r"^[A-Za-z_]\w*$", cv[k] or ""):
            a["call_vars"][k] = cv[k]
    return a
