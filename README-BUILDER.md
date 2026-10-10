# Our builder (team arda-berk)

One command, a brief (or two) plus the tool API file in, a phone agent on Freya out, with a plain-text trace.

```bash
cp env.example env.sh && $EDITOR env.sh        # FREYA_API_KEY, FREYA_BANK_TEAM_KEY
python3.12 -m venv .venv && . .venv/bin/activate && pip install claude-agent-sdk pytest
source env.sh
python3 builder/build.py briefs/brief-a.md tools/openapi.json --cases public-test-set.json --brief A
python3 builder/build.py briefs/brief-a.md briefs/brief-b.md tools/openapi.json --cases public-test-set.json --brief B
```

The model steps use the Claude Agent SDK: a Claude login or `ANTHROPIC_API_KEY` is needed (model `claude-opus-5-5`,
override with `BUILDER_MODEL`). Everything else is standard-library Python.

## How it works

1. **extract** (`builder/extract.py`, one model call): the brief(s) and the tool API go in, a generic policy spec comes
   out (`builder/spec_schema.json`): identity questions, calendar and holidays, lateness bands and deadlines, floor
   rule, persuasion attempts, special cases, outcome table, multi-product rules, and every leftover rule verbatim.
   Enum values (outcomes, reasons, queues, fields) are validated against the API file.
2. **compile** (`builder/compile.py`, no model): a fixed topology is filled from the spec. Date arithmetic, bands,
   deadlines, floors and the outcome decision run as Python in code nodes (`builder/codegen/`), the dialogue model gets
   finished facts. One node per security question with the tool's `field` baked in. `close_call` is a lifecycle tool
   fed by variables that code nodes set.
3. **lint** (`builder/lint.py`): the platform rules from `docs/` checked offline.
4. **validate, save, smoke**: dry run, `freya.save_workflow(slot)` (in place), one chat turn.
5. **test** (`tools/run_cases.py`, the kit's scorer) and **patch** (`builder/patch.py`, one model call per round): failed
   transcripts go back to the model, which may only revise the spec; the topology stays. Bounded by `--max-test-rounds`
   and the 30-minute budget (`--budget-min`, default 27).
6. **export** to `submission/<slot>.workflow.json`.

Trace: `traces/<slot>-<time>.log` (start/end, every model call with its purpose, what was created on Freya, every test
and its result). Unit tests for the code nodes: `pytest tests/`.

Probe a workflow quickly (crash checks only, the chat route is not the scored engine):
`python3 builder/probe.py <workflow_id> PUB-01 "Yes, speaking." "14 March 1988" "4471"`.
