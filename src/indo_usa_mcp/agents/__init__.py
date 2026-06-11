"""Autonomous agent layer (blueprint §6): scheduler + worker over the pipeline.

Public surface:
    AGENTS         -- name -> Agent instance registry
    run_agent(name, **params) -> agent_runs row (executes + audits one agent)
"""

from .base import Agent
from .registry import AGENTS, get_agent
from .runner import run_agent

__all__ = ["Agent", "AGENTS", "get_agent", "run_agent"]
