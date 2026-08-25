"""A failed CLI call has to say WHY, and what to do about it.

On 2026-08-24 the advisor stopped answering. The log said:

    [advisor] claude CLI rc=1 (model=sonnet) stderr='' stdout='{"is_error":true,
    "duration_api_ms":0,"num_turns":1,"stop_reason":"stop_sequence","session_id"...

which is 200 characters of metadata and not one word of explanation, because
the CLI puts `result` — the sentence that says why — after that prefix. The
account had simply run out of subscription quota. Nothing was broken, and
nothing in the app could say so.

The NEXT day it stopped again, and the first fix proved half right. It captured
the reason text — "Failed to authenticate: OAuth session expired" — but labelled
it "usage_limit", because the heuristic was only "errored without spending any
API time", and an expired session looks exactly like an exhausted quota by that
measure. So the dock told Bryan to wait for a reset that was never coming, when
the actual fix was thirty seconds of /login. Telling someone to wait out a dead
session is worse than saying nothing at all.

    cd backend && .venv/Scripts/python -m pytest tests/test_advisor_failures.py -q
"""
import json
import os
from types import SimpleNamespace

os.environ["DATA_MODE"] = "mock"
os.environ["ADVISOR_ENABLED"] = "0"

from app.services import advisor as a  # noqa: E402


def _proc(stdout="", stderr="", rc=1):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=rc)


# ------------------------------------------------------------------ explain
def test_a_quota_block_is_named_as_one():
    """Both blocks spend no API time, so the TEXT is what separates them."""
    out = json.dumps({
        "is_error": True, "duration_api_ms": 0, "num_turns": 1,
        "stop_reason": "stop_sequence", "session_id": "abc",
        "total_cost_usd": 0,
        "result": "Claude usage limit reached. Your limit will reset at 12:00pm.",
    })
    reason, detail = a._explain(_proc(stdout=out))
    assert reason == "usage_limit"
    assert "reset at 12:00pm" in detail


def test_the_reason_survives_the_metadata_prefix():
    """The exact bug: `result` sits past the first 200 characters."""
    out = json.dumps({
        "is_error": True, "duration_api_ms": 0, "total_cost_usd": 0,
        "session_id": "x" * 300,            # push `result` well past 200 chars
        "result": "Claude usage limit reached.",
    })
    assert out.index("result") > 200
    _, detail = a._explain(_proc(stdout=out))
    assert "usage limit" in detail.lower()


def test_an_expired_session_is_not_reported_as_a_usage_limit():
    """The 2026-08-25 incident, verbatim from the log.

    Both an expired session and an exhausted quota error out having spent no
    API time and charged nothing. Only one of them fixes itself by waiting, so
    calling this "usage_limit" actively sent Bryan the wrong way.
    """
    out = json.dumps({
        "is_error": True, "duration_api_ms": 0, "total_cost_usd": 0,
        "session_id": "abc",
        "result": "Failed to authenticate: OAuth session expired and could not "
                  "be refreshed",
    })
    reason, detail = a._explain(_proc(stdout=out))
    assert reason == "auth"
    assert "authenticate" in detail.lower()
    assert "/login" in a.FIX_HINTS["auth"]


def test_every_blocking_reason_carries_a_next_step():
    """A status with no action is how this cost an hour, twice."""
    for reason in ("auth", "usage_limit", "blocked"):
        assert a.FIX_HINTS.get(reason)


def test_an_unrecognised_block_does_not_invent_a_cause():
    """It errored before reaching the API and would not say why. That is worth
    reporting as blocked; guessing 'usage limit' is what caused the mislabel."""
    out = json.dumps({"is_error": True, "duration_api_ms": 0,
                      "total_cost_usd": 0, "result": ""})
    reason, _ = a._explain(_proc(stdout=out))
    assert reason == "blocked"


def test_an_auth_failure_in_stderr_is_still_caught():
    reason, _ = a._explain(_proc(stdout="", stderr="Invalid API key provided"))
    assert reason == "auth"


def test_a_genuine_failure_is_not_mistaken_for_quota():
    # Time was spent and money was charged, so the request DID reach the API.
    out = json.dumps({"is_error": True, "duration_api_ms": 1873,
                      "total_cost_usd": 0.02,
                      "result": "Tool execution failed: permission denied"})
    reason, detail = a._explain(_proc(stdout=out))
    assert reason == "error"
    assert "permission denied" in detail


def test_non_json_output_falls_back_to_stderr():
    reason, detail = a._explain(_proc(stdout="not json", stderr="spawn EACCES"))
    assert reason == "error" and "EACCES" in detail


def test_silence_still_produces_something_to_read():
    reason, detail = a._explain(_proc(stdout="", stderr=""))
    assert reason == "error" and detail == "no output"


# ------------------------------------------------------------- retry policy
def _stub_run(monkeypatch, stdouts, rc=1):
    """Feed _attempt a scripted sequence of CLI results; record the models."""
    seen = []

    def fake(cmd, **kw):
        model = cmd[cmd.index("--model") + 1] if "--model" in cmd else "default"
        seen.append(model)
        return _proc(stdout=stdouts[min(len(seen) - 1, len(stdouts) - 1)], rc=rc)

    monkeypatch.setattr(a.subprocess, "run", fake)
    monkeypatch.setattr(a.shutil, "which", lambda x: "claude")
    return seen


QUOTA = json.dumps({"is_error": True, "duration_api_ms": 0,
                    "total_cost_usd": 0, "result": "usage limit reached"})
BROKEN = json.dumps({"is_error": True, "duration_api_ms": 900,
                     "total_cost_usd": 0.01, "result": "something broke"})


AUTH = json.dumps({"is_error": True, "duration_api_ms": 0, "total_cost_usd": 0,
                   "result": "Failed to authenticate: OAuth session expired"})


def test_a_quota_block_does_not_burn_the_fallback_model(monkeypatch):
    """The ceiling is account-wide. Retrying Sonnet cannot succeed, and doing
    it makes a plain 'you are out of quota' look like a flaky tool."""
    seen = _stub_run(monkeypatch, [QUOTA])
    assert a._run_claude("hi") == (None, None)
    assert len(seen) == 1


def test_an_expired_session_does_not_burn_the_fallback_either(monkeypatch):
    # The session is account-wide too — the fallback hits the same wall.
    seen = _stub_run(monkeypatch, [AUTH])
    assert a._run_claude("hi") == (None, None)
    assert len(seen) == 1


def test_the_recorded_failure_carries_its_fix(monkeypatch):
    _stub_run(monkeypatch, [AUTH])
    a._run_claude("hi")
    f = a.last_failure()
    assert f["reason"] == "auth"
    assert "/login" in (f["hint"] or "")


def test_the_diagnosis_survives_a_restart(monkeypatch, tmp_path):
    """Restarting the backend is the FIRST thing anyone does when the CLI stops
    working — which is exactly when an in-memory record disappears."""
    monkeypatch.setattr(a, "_FAILURE_FILE", tmp_path / "fail.json")
    _stub_run(monkeypatch, [AUTH])
    a._run_claude("hi")

    # simulate a fresh process: wipe the in-memory record, keep the file
    a._LAST_FAILURE.update(reason=None, detail=None, ts=0.0, hint=None)
    assert a.last_failure()["reason"] == "auth"


def test_an_ordinary_failure_still_retries(monkeypatch):
    seen = _stub_run(monkeypatch, [BROKEN])
    a._run_claude("hi")
    assert len(seen) == 2          # primary, then the standard-model fallback


def test_the_failure_is_recorded_for_the_ui(monkeypatch):
    _stub_run(monkeypatch, [QUOTA])
    a._run_claude("hi")
    f = a.last_failure()
    assert f["reason"] == "usage_limit"
    assert "usage limit" in f["detail"].lower()


def test_a_success_clears_the_record(monkeypatch):
    _stub_run(monkeypatch, [QUOTA])
    a._run_claude("hi")
    assert a.last_failure()["reason"] == "usage_limit"

    ok = json.dumps({"is_error": False, "result": "fine", "session_id": "s1",
                     "duration_api_ms": 10, "total_cost_usd": 0.01})
    _stub_run(monkeypatch, [ok], rc=0)
    assert a._run_claude("hi")[0] == "fine"
    assert a.last_failure()["reason"] is None
