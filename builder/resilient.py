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


def install_watchdog(log=print, hard_limit_s=1800):
    """Replace freya.run_simulation with one that cannot hang: a simulation whose runs all have a verdict but whose
    status stays 'running' (seen on 10 Oct with an 'inconclusive' run) is marked completed through the documented
    update call, and so is one that exceeds the hard limit. Otherwise the workspace's single slot stays blocked."""
    import freya
    if getattr(freya.run_simulation, "_watchdog", False):
        return

    def run_simulation(agent_id, name, variables_by_persona, max_seconds=420, concurrency=None):
        import os
        concurrency = concurrency or int(os.environ.get("FREYA_SIM_CONCURRENCY", "5"))
        while True:
            try:
                sim = freya.api("POST", "/api/v2/simulations", {
                    "agentId": agent_id, "name": name, "mode": "chat", "selectedPersonaIds": list(variables_by_persona),
                    "customerVariablesMap": variables_by_persona, "maxConcurrentCalls": concurrency, "runsPerPersona": 1, "maxCallDurationSeconds": max_seconds,
                    "assistantLlmOverride": freya.AGENT_LLM, "routingLlmOverride": freya.AGENT_LLM, "extractionLlmOverride": freya.AGENT_LLM,
                    "personaLlmOverride": freya.SIM_LLM, "analysisLlmOverride": freya.SIM_LLM})
                break
            except RuntimeError as e:
                if "concurrent simulations" not in str(e):
                    raise
                log("another simulation is running in this workspace, waiting 30 s"); time.sleep(30)
        sim_id = (sim.get("simulation") or sim)["id"]
        t0, status, it_id = time.time(), "running", None
        while True:
            time.sleep(10)
            s = freya.api("GET", f"/api/v2/simulations/{sim_id}"); s = s.get("simulation") or s
            status = s.get("status")
            if status in ("completed", "failed", "paused"):
                break
            waited = time.time() - t0
            if waited > 240 and int(waited) % 60 < 10:        # once a minute after four minutes: are all runs done?
                try:
                    its = freya.api("GET", f"/api/v2/simulations/{sim_id}/iterations"); its = its.get("iterations") or its.get("items") or its
                    runs = freya.get_iteration(sim_id, its[0]["id"])["runs"] if its else []
                    open_runs = [r for r in runs if r.get("outcome") in (None, "queued", "running", "pending")]
                    if (runs and not open_runs and len(runs) >= len(variables_by_persona)) or waited > hard_limit_s:
                        log(f"simulation {sim_id} still 'running' after {waited:.0f} s with {len(open_runs)} open runs: marking it completed")
                        freya.api("PUT", f"/api/v2/simulations/{sim_id}", {"status": "completed"})
                        status = "completed"
                        break
                except Exception as e:
                    log("watchdog check failed: " + str(e)[:120])
        its = freya.api("GET", f"/api/v2/simulations/{sim_id}/iterations"); its = its.get("iterations") or its.get("items") or its
        return sim_id, its[0]["id"], status

    run_simulation._watchdog = True
    freya.run_simulation = run_simulation
