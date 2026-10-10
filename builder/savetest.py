"""Publish the two development agents (Brief A, and Brief A+B) from out/compiled/. Used by the team's test queues only."""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "builder")]
import freya, resilient
resilient.install()
for slot, f in (("compiled-brief-a", "brief-a"), ("compiled-brief-ab", "brief-ab")):
    wf = json.load(open(ROOT / "out" / "compiled" / f"{f}.workflow.json"))
    print(slot, freya.save_workflow(slot, wf, state_file=str(ROOT / ".freya-compiled.json")))
