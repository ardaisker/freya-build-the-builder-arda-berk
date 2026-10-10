"""Freya credit guard. Simulations cost credits; a reserve is kept for the final.

    python3 builder/credits.py            # prints the balance, exit code 1 when at or below the reserve
    FREYA_CREDIT_RESERVE=100 (default)    # credits that must stay untouched until the final run
"""
import os, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RESERVE = float(os.environ.get("FREYA_CREDIT_RESERVE", "100"))
PER_CALL = 0.08          # measured on 10 Oct: 18.4 credits for about 250 simulated calls


def left():
    import freya
    ws = freya.workspace_id()
    return float(freya.api("GET", f"/api/v2/workspaces/{ws}/credits", workspaceId=ws)["creditsLeft"])


def allow(calls, what="run"):
    """True when `calls` simulated calls fit above the reserve. Prints one line either way."""
    try:
        have = left()
    except Exception as e:
        print(f"credit check failed ({str(e)[:80]}); continuing", flush=True); return True
    need = calls * PER_CALL
    ok = have - need >= RESERVE
    print(f"credits: {have:.1f} left, {what} needs about {need:.1f}, reserve {RESERVE:.0f} -> {'ok' if ok else 'STOP: this would eat into the reserve for the final'}", flush=True)
    return ok


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sys.exit(0 if allow(n, "this run") else 1)
