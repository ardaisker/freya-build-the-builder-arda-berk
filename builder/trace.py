"""Plain-text builder trace: start/end, every model call, what was created on Freya, every test and its result."""
from __future__ import annotations

import json
import pathlib
import sys
import time


class Trace:
    def __init__(self, path: str | pathlib.Path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = self.path.open("a")
        self.t0 = time.time()

    def _stamp(self):
        return time.strftime("%Y-%m-%dT%H:%M:%S%z") + f" (+{time.time() - self.t0:7.1f}s)"

    def log(self, line: str):
        text = f"{self._stamp()}  {line}"
        self.f.write(text + "\n"); self.f.flush()
        print(text, flush=True)

    def section(self, title: str):
        self.log("== " + title + " ==")

    def model_call(self, model: str, purpose: str, started: bool = False, seconds: float = 0.0, chars_out: int = 0):
        if started:
            self.log(f"MODEL CALL start  model={model}  purpose={purpose}")
        else:
            self.log(f"MODEL CALL done   model={model}  purpose={purpose}  took={seconds:.1f}s  answer={chars_out} chars")

    def created(self, what: str, **fields):
        self.log("CREATED " + what + "  " + json.dumps(fields, sort_keys=True))

    def test(self, name: str, result: str):
        self.log(f"TEST {name}: {result}")

    def end(self, status: str):
        self.log(f"END status={status} total={time.time() - self.t0:.0f}s")
        self.f.close()
