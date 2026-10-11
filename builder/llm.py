"""One-turn model calls for the builder.

Backend: the Claude Agent SDK (works with a Claude login or ANTHROPIC_API_KEY, like the kit's example builder).
Fallback: the Claude Code CLI in print mode. Every call is recorded in the trace (model + one-line purpose).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time

MODEL = os.environ.get("BUILDER_MODEL", "claude-opus-5-5")
# when the main model is out of quota (a usage or session limit), the rest of the build runs on this one instead of stopping
FALLBACK_MODEL = os.environ.get("BUILDER_FALLBACK_MODEL", "claude-sonnet-5-5")


def strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw


def extract_json(raw: str):
    """Parse the first JSON object in a model answer."""
    text = strip_fences(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model answer: " + text[:300])
    return json.loads(text[start:end + 1])


async def _ask_sdk(system: str, user: str, model: str, max_turns: int = 1) -> str:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query
    options = ClaudeAgentOptions(model=model, system_prompt=system, allowed_tools=[], disallowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch", "Agent"],
                                 permission_mode="dontAsk", max_turns=max_turns, setting_sources=[])
    parts, result = [], None
    async for m in query(prompt=user, options=options):
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, TextBlock):
                    parts.append(b.text)
        elif isinstance(m, ResultMessage):
            result = m
    text = "\n".join(parts).strip()
    if not text and result is not None and getattr(result, "result", None):
        text = str(result.result)
    return text


def _ask_cli(system: str, user: str, model: str) -> str:
    cmd = ["claude", "-p", "--output-format", "text", "--model", model, "--max-turns", "1", "--system-prompt", system]
    out = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=900)
    if out.returncode != 0 or out.stdout[:200].startswith("Not logged in"):
        raise RuntimeError("claude cli failed: " + (out.stderr or out.stdout).strip()[:500])
    return out.stdout


class LLM:
    """`ask` returns text, `ask_json` a parsed object. `calls` is the list the trace prints."""

    def __init__(self, model: str = MODEL, trace=None):
        self.model = model
        self.trace = trace
        self.calls = []
        try:
            import claude_agent_sdk  # noqa: F401
            self.backend = "sdk"
        except ImportError:
            self.backend = "cli" if shutil.which("claude") else None
        if self.backend is None:
            raise RuntimeError("no model backend: pip install claude-agent-sdk (and log in to Claude) or set ANTHROPIC_API_KEY")

    def ask(self, purpose: str, system: str, user: str, model: str | None = None) -> str:
        model = model or self.model
        t0 = time.time()
        if self.trace:
            self.trace.model_call(model, purpose, started=True)
        text, last = "", None
        for attempt in range(3):            # a model call can fail for a moment (rate limit, network): try again before giving up
            try:
                text = asyncio.run(_ask_sdk(system, user, model)) if self.backend == "sdk" else _ask_cli(system, user, model)
                if text.strip():
                    break
            except Exception as e:
                last = e
            if self.trace:
                self.trace.log(f"MODEL CALL retry {attempt + 1}: {str(last)[:120] if last else 'empty answer'}")
            time.sleep(10 * (attempt + 1))
        if not text.strip() and last is not None and model != FALLBACK_MODEL and re.search(r"limit|quota|overloaded|rate", str(last), re.I):
            if self.trace:
                self.trace.log(f"MODEL CALL {model} unavailable ({str(last)[:80]}): switching to {FALLBACK_MODEL} for the rest of the build")
            self.model = FALLBACK_MODEL
            return self.ask(purpose, system, user, FALLBACK_MODEL)
        if not text.strip() and last is not None:
            raise last
        took = time.time() - t0
        self.calls.append({"model": model, "purpose": purpose, "seconds": round(took, 1), "chars_in": len(system) + len(user), "chars_out": len(text)})
        if self.trace:
            self.trace.model_call(model, purpose, seconds=took, chars_out=len(text))
        if not text.strip():
            raise RuntimeError(f"empty model answer for: {purpose}")
        return text

    def ask_json(self, purpose: str, system: str, user: str, retries: int = 1, model: str | None = None):
        last = None
        for attempt in range(retries + 1):
            raw = self.ask(purpose + ("" if attempt == 0 else f" (retry {attempt})"), system, user, model)
            try:
                return extract_json(raw)
            except (ValueError, json.JSONDecodeError) as e:
                last = e
                user = user + "\n\nYour previous answer was not valid JSON (" + str(e)[:200] + "). Answer with one JSON object only."
        raise RuntimeError(f"model did not return JSON for {purpose}: {last}")
