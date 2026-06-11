"""Agent registry: name -> Agent instance."""

from __future__ import annotations

from .base import Agent
from .definitions import ALL_AGENTS

AGENTS: dict[str, Agent] = {a.name: a for a in ALL_AGENTS}


def get_agent(name: str) -> Agent:
    try:
        return AGENTS[name]
    except KeyError:
        raise ValueError(
            f"Unknown agent '{name}'. Known: {', '.join(sorted(AGENTS))}"
        ) from None
