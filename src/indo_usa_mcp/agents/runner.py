"""Worker that executes one agent and writes a full audit row to agent_runs."""

from __future__ import annotations

import functools
import json
import time
import traceback
from typing import Any

from psycopg.types.json import Jsonb

from .. import db
from .registry import get_agent

# Agents may return rows straight from the DB (datetime / Decimal / date), which the stdlib JSON
# encoder can't serialize — that would make the audit write itself raise and mask the real result
# (it's why the `discovery` agent was recorded as status='error'). Stringify any such value so the
# audit row always persists, whatever the agent returns.
_jsonb = functools.partial(Jsonb, dumps=functools.partial(json.dumps, default=str))


def run_agent(name: str, **params: Any) -> dict[str, Any]:
    """Execute an agent, persist a run record, and return that record.

    Exceptions are caught and logged as status='error' so the scheduler/Monitoring
    Agent can react; the error is also re-surfaced in the returned dict.
    """
    agent = get_agent(name)
    run = db.query_one(
        "INSERT INTO agent_runs (agent, status, params) VALUES (%s, 'running', %s) RETURNING id",
        (name, _jsonb(params) if params else None),
    )
    run_id = run["id"]
    started = time.monotonic()

    try:
        result = agent.run(**params)
        duration = int((time.monotonic() - started) * 1000)
        db.execute(
            "UPDATE agent_runs SET status='success', result=%s, finished_at=now(), "
            "duration_ms=%s WHERE id=%s",
            (_jsonb(result), duration, run_id),
        )
        return {"id": run_id, "agent": name, "status": "success",
                "duration_ms": duration, "result": result}
    except Exception as exc:
        duration = int((time.monotonic() - started) * 1000)
        err = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        db.execute(
            "UPDATE agent_runs SET status='error', error=%s, finished_at=now(), "
            "duration_ms=%s WHERE id=%s",
            (err, duration, run_id),
        )
        return {"id": run_id, "agent": name, "status": "error",
                "duration_ms": duration, "error": str(exc)}
