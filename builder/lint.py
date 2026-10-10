"""Offline checks of a workflow JSON against the platform rules in docs/. Returns a list of problems."""
from __future__ import annotations

import json
import sys

CONV_ONLY = {"tools", "extraction_schema"}
ACTION_TYPES = {"api_request", "code"}


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + "." + k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + f"[{i}]")
    else:
        yield path, obj


def lint(wf: dict) -> list[str]:
    p = []
    nodes = wf.get("nodes") or {}
    if wf.get("initial_node") not in nodes:
        p.append("initial_node missing from nodes")
    for path, v in walk(wf):
        if v is None:
            p.append(f"null value at {path}")
    for name, n in nodes.items():
        t = n.get("node_type")
        if n.get("name") != name:
            p.append(f"{name}: name field differs")
        for tr in n.get("transitions") or []:
            if tr.get("target_node") not in nodes and tr.get("target_node") != "__previous__":
                p.append(f"{name}: transition to unknown node {tr.get('target_node')}")
            c = tr.get("condition") or {}
            if "logic" in c and c["logic"] != "or":
                p.append(f"{name}: top-level condition logic must be 'or'")
        if n.get("max_turn_transition") and n["max_turn_transition"] not in nodes:
            p.append(f"{name}: max_turn_transition unknown")
        if t == "conversation":
            if n.get("pre_actions"):
                p.append(f"{name}: pre_actions on a conversation node are dropped by the platform")
            if "max_node_turns" in n and not n.get("max_turn_transition"):
                p.append(f"{name}: max_node_turns without max_turn_transition")
            for e in n.get("extraction_schema") or []:
                if "min_confidence" not in e:
                    p.append(f"{name}: extraction {e.get('name')} has no min_confidence")
            for tool in n.get("tools") or []:
                p += lint_tool(tool, name)
        elif t in ACTION_TYPES:
            if n.get("tools"):
                p.append(f"{name}: tools on a {t} node are dropped")
            if not n.get("passthrough"):
                p.append(f"{name}: {t} node should be passthrough")
            trs = n.get("transitions") or []
            if not trs or (trs[-1].get("condition") or {}).get("operator") != "always":
                p.append(f"{name}: passthrough node must end with an always transition")
            if not n.get("passthrough_default_transition"):
                p.append(f"{name}: passthrough_default_transition missing")
            for a in n.get("pre_actions") or []:
                fn = a.get("function") or {}
                if fn.get("handler") == "__function__:code_exec":
                    code = ((fn.get("parameters") or {}).get("properties") or {}).get("code", {}).get("default", "")
                    if "{" in code or "}" in code:
                        p.append(f"{name}: code snippet contains a brace")
                    if "vars" not in code:
                        p.append(f"{name}: code snippet never touches vars")
                else:
                    p += lint_tool(a, name)
            for m in n.get("response_mapping") or []:
                if not str(m.get("path", "")).startswith("data."):
                    p.append(f"{name}: response_mapping path should start with data.")
        elif t == "end_call":
            if not n.get("terminal"):
                p.append(f"{name}: end_call node without terminal")
            if n.get("transitions"):
                p.append(f"{name}: end_call node with transitions")
        else:
            p.append(f"{name}: unknown node_type {t}")
    for tool in wf.get("tools") or []:
        if not (tool.get("config") or {}).get("alwaysRunsAt"):
            p.append("workflow-level tool without alwaysRunsAt never runs")
        p += lint_tool(tool, "workflow")
    # reachability
    seen, stack = set(), [wf.get("initial_node")]
    while stack:
        x = stack.pop()
        if x in seen or x not in nodes:
            continue
        seen.add(x)
        n = nodes[x]
        for tr in n.get("transitions") or []:
            stack.append(tr.get("target_node"))
        if n.get("max_turn_transition"):
            stack.append(n["max_turn_transition"])
        if n.get("passthrough_default_transition"):
            stack.append(n["passthrough_default_transition"])
    for name in nodes:
        if name not in seen:
            p.append(f"{name}: unreachable")
    if "agent_config" in wf:
        p.append("agent_config should be left out")
    return p


def lint_tool(tool, where):
    p = []
    fn = tool.get("function") or {}
    props = (fn.get("parameters") or {}).get("properties") or {}
    for path, v in walk(props):
        if path.endswith(".const"):
            p.append(f"{where}/{fn.get('name')}: const does not bake, use default")
    if fn.get("handler") == "__function__:api_call":
        if "default" not in props.get("url", {}):
            p.append(f"{where}/{fn.get('name')}: url needs a default")
        body = props.get("body") or {}
        if body and "default" in body and "properties" not in body:
            p.append(f"{where}/{fn.get('name')}: body.default without body.properties")
        for f, leaf in (body.get("properties") or {}).items():
            if "default" not in leaf:
                p.append(f"{where}/{fn.get('name')}: body field {f} has no default")
    for m in tool.get("response_mapping") or []:
        if not str(m.get("path", "")).startswith("data."):
            p.append(f"{where}/{fn.get('name')}: response_mapping path should start with data.")
    return p


if __name__ == "__main__":
    wf = json.load(open(sys.argv[1]))
    probs = lint(wf)
    print("\n".join(probs) if probs else "lint: clean")
    sys.exit(1 if probs else 0)
