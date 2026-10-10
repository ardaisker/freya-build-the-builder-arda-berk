"""Retries for the Freya API client. The platform sometimes answers 502/503/504 for a moment; a builder run must not
die of that. Reads are retried on any of the three; writes only on 503 (the request was not processed), so nothing is
ever created twice."""
import sys, time


def install(log=print, tries=6):
    import freya
    if getattr(freya.api, "_resilient", False):
        return
    plain = freya.api

    def api(method, path, body=None, **params):
        for attempt in range(tries):
            try:
                return plain(method, path, body, **params)
            except RuntimeError as e:
                msg = str(e)
                code = next((c for c in ("502", "503", "504") if f"-> {c}:" in msg), None)
                retry = code is not None and (method == "GET" or code == "503")
                if not retry or attempt == tries - 1:
                    raise
                wait = min(60, 5 * (attempt + 1) ** 2)
                log(f"Freya {method} {path.split('?')[0]} answered {code}; retry {attempt + 1} in {wait} s")
                time.sleep(wait)

    api._resilient = True
    freya.api = api
