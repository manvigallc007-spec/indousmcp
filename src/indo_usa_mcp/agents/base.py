"""Agent base class. Each agent is a small, idempotent unit of autonomous work."""

from __future__ import annotations

import abc
from typing import Any


class Agent(abc.ABC):
    #: Stable identifier (used in agent_runs.agent and the scheduler config).
    name: str
    #: One-line description for `agents list`.
    description: str = ""
    #: Default scheduler interval in seconds (advisory; scheduler may override).
    default_interval_s: int = 3600

    @abc.abstractmethod
    def run(self, **params: Any) -> dict[str, Any]:
        """Do the work and return a JSON-serialisable result summary.

        Must be safe to retry: raise on failure (the runner records the error);
        never leave the canonical layer half-written.
        """
        raise NotImplementedError
