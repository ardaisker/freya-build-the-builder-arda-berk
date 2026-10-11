# Our builder (team arda-berk)

One command. A brief and a tool API file go in, a phone agent on Freya comes out, with a plain-text trace.

```bash
python3.12 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp env.example env.sh && $EDITOR env.sh && source env.sh        # FREYA_API_KEY, FREYA_BANK_TEAM_KEY
python3 builder/build.py briefs/brief-a.md tools/openapi.json
python3 builder/build.py briefs/brief-a.md briefs/brief-b.md tools/openapi.json --cases public-test-set.json --brief B
```

The brief may be one file, several files, or a folder (a mail, a policy extract, a memo, a code list). The tool API is
whichever file parses as an OpenAPI document. The two model steps use the Claude Agent SDK, so a Claude login or
`ANTHROPIC_API_KEY` is needed (model `claude-opus-5-5`, override with `BUILDER_MODEL`). Everything else is the standard library.

## What the builder does

| Step | File | Model? | What happens |
|---|---|---|---|
| 1 extract | `builder/extract.py`, `spec_schema.json` | yes, 1 call | The material becomes a policy spec: opening, identity questions, calendar, lateness bands, deadline and offer rules as small rule objects, floor rule, special cases, outcome table, several-product rules, and every leftover rule word for word. |
| 1b audit | `builder/extract.py` | yes, 1 call | The spec is checked against the material. Only corrections with a quote from the material are applied (for example a memo that changes a limit). |
| 1c oracle | `builder/oracle.py` | yes, 1 call + at most 2 | A second reading that never sees the spec writes 16-24 concrete situations (a product, today's date, a day the customer names) with the deadline, floor, offers and date verdict the material requires. The code steps compute them locally; disagreements go to a judge call that patches the spec only with a quote, and a patch is kept only if it reduces the disagreements and breaks none that agreed. |
| 2 compile | `builder/compile.py`, `builder/apimap.py`, `builder/codegen/` | no | A fixed call structure is filled from the spec. Dates, deadlines, floors, offers and the closing outcome are computed by Python inside the workflow, so the phone agent's model is given finished facts. |
| 2b self-check | `builder/build.py` | no | Every code step is run locally on made-up customers built from the tool API (each product type in each band). |
| 3 lint | `builder/lint.py` | no | The platform rules from `docs/`, checked offline. |
| 4 save, smoke | `freya.py` | no | Dry run, `save_workflow(slot)` in place, one chat turn. |
| 5 test, patch | `tools/run_cases.py`, `builder/patch.py` | patch: 1 call per round | Only when practice customers are given (`--cases`). Failed transcripts go back to the model, which may revise the spec, never the structure. |
| 6 export | `freya.py` | no | `submission/<slot>.workflow.json` |

The trace is `traces/<slot>-<time>.log`: start and end, each model call with its purpose, what was created on Freya,
each test with its result.

## Why it reads a brief instead of knowing one

Nothing in `builder/` names a bank, a holiday, an outcome, a queue or a field of the tool API.

- **Tool API.** `apimap.py` matches each role (the amount of a promise, the list of products, the "verified" flag, the
  close outcome...) to the property the API file declares. The model's `api` section is used where it names a real
  property; otherwise a name-pattern match; `tests/` runs a fixture in which every field and value is renamed.
- **Rules.** Deadlines and offers are rule objects (`business_days_after_today`, `calendar_days_after_today`,
  `last_business_day_of_week`, `end_of_month`, `deadline`, ...), evaluated in code against the spec's calendar.
- **Outcomes.** Every outcome the workflow can record comes from the spec and is checked against the API's values.
- **Unknown rules.** Anything the schema has no slot for is kept verbatim in the prompts (`residual_rules`); special
  cases the brief adds get their own exit that records their outcome.

Fixtures written by the team (synthetic, in `fixtures/`): raw bank material with a memo that overrides the policy;
a brief whose tool API is fully renamed; a brief with three identity questions, calendar-day deadlines, three offers,
a percentage floor and extra special cases. `fixtures/edge-cases.json` holds 42 extra customer behaviours for the 13
practice customers, run with `builder/run_custom.py` (same scorer and judge as the kit).

## Tests

```bash
pytest tests/                                   # code steps, API map, date rules, generalisation fixtures (no network)
python3 builder/build.py fixtures/variant-brief.md fixtures/variant.openapi.json --no-freya     # offline build
python3 tools/run_cases.py <agent_id> --brief A --reps 2
python3 builder/run_custom.py <agent_id> --reps 2
```

## Final run (hidden briefs)

```bash
source env.sh
python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json --slot hidden-1 2>&1 | tee traces/hidden-1.log
python3 builder/build.py briefs/hidden-2.md briefs/hidden-2.openapi.json --slot hidden-2 2>&1 | tee traces/hidden-2.log
```

Without `--cases` no practice simulation runs (a hidden brief has none): extract, audit, compile, self-check, lint,
dry run, save, one smoke turn, export. Fill `submission/FORM-TEMPLATE.json`, commit, push, send.

## The final case: a folder of client material, not a brief

The final case is a different kind of call with different services, described by a folder of documents that contradict
each other. The builder has a second road for that; the collection road above is unchanged and still used whenever the
input brings the kit's tool API.

    python3 builder/build.py <case folder> --tool-url <base address of the services> --max-test-rounds 3

What it does, every step in the trace:

1. **Read** every file of the folder (`casefolder.py`): text, mail, PDF, Word, Excel, zip. A very large data file is
   abridged so that its shapes stay exact.
2. **Case spec** (`casespec.py`, the builder's model): services (path, fields, test calls), the procedure, the exact
   sentences, the ways a call ends, and test conversations. Every contradiction between documents is decided and
   logged with its sources ("decision on a contradiction" lines in the trace).
3. **Service check** (`casetest.py`): every service is called with the client's own test data; the trace shows the
   status and what the agent would be told.
4. **Compile** (`casecompile.py`, code only): setup -> services read before the first word -> one conversation node ->
   endings. Around every service call sits code, not the phone model:
   - the request is built by code (nested fields, path/query, types); a value copied from an earlier answer is repaired;
   - `derive`: differences, comparisons, days to a date, amounts/dates/digits as they are spoken, spoken lists,
     duplicates in a list;
   - `result_rules`: code picks, or composes from parts, the exact sentence the agent says next;
   - a result that alone ends the call ends it by code with the client's sentence;
   - error answers are routed by the engine (the platform runs no hook on an HTTP error);
   - look-alike records (same name, same last digits) are told apart by code from the digits the caller said: until
     exactly one record fits, nothing is read and the agent is told which question to ask.
5. **Test conversations** are played on Freya against the published agent; the builder's model judges them, reads the
   material a second time, and edits the spec (small edits, not a rewrite); the new version is published and replayed;
   the better version stays.
6. **Export.**

Nothing in `builder/` names a service, a field, a sentence or a value of any case; `builder/leakcheck.py` compares the
lines added since the `pre-reveal` tag with the final pack (what it still lists are ordinary English words).
`tests/test_case.py` tests this road on made-up data.

The mock of the client's services lives in `mock/` (a Cloudflare Worker). It is written by hand as the task asks, serves
the pack's test answers word for word (`mock/check_mock.py` compares all of them) and is not part of the builder.
