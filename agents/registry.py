"""
Agent Registry — Physics Discovery System v3.0
RAP Corp | Renaissance of American Physics
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Type

logger = logging.getLogger(__name__)

# ── Global agent registry ─────────────────────────────────────────────────────

_agent_registry: Dict[str, Type] = {}


def register_agent(name: str) -> Callable:
    """Decorator that registers an agent class under the given name."""
    def decorator(cls: Type) -> Type:
        _agent_registry[name] = cls
        logger.debug(f"Registered agent: {name} -> {cls.__name__}")
        return cls
    return decorator


def get_agent(name: str) -> Optional[Type]:
    """Return the agent class registered under *name*, or None."""
    return _agent_registry.get(name)


def get_all_agents() -> Dict[str, Type]:
    """Return a copy of the full agent registry."""
    return dict(_agent_registry)


# ── AgentRegistry class (lifecycle management) ───────────────────────────────

class AgentRegistry:
    """Runtime registry: tracks live agent instances and their health."""

    def __init__(self, **kwargs):
        self._instances: Dict[str, Any] = {}

    def register(self, name: str, instance: Any = None):
        """Works both as a direct call and as a class decorator.

        Direct:    agent_registry.register("name", instance)
        Decorator: @agent_registry.register("name")
        """
        if instance is None:
            def decorator(cls):
                self._instances[name] = cls
                logger.info(f"Agent registered: {name}")
                return cls
            return decorator
        self._instances[name] = instance
        logger.info(f"Agent instance registered: {name}")

    def get(self, name: str) -> Optional[Any]:
        return self._instances.get(name)

    def all_agents(self) -> Dict[str, Any]:
        return dict(self._instances)

    async def health_check(self) -> Dict[str, bool]:
        results = {}
        for name, instance in self._instances.items():
            try:
                if hasattr(instance, "health_check"):
                    ok = await instance.health_check()
                else:
                    ok = True
            except Exception as exc:
                logger.warning(f"Health check failed for {name}: {exc}")
                ok = False
            results[name] = ok
        return results

    async def shutdown_all(self) -> None:
        for name, instance in list(self._instances.items()):
            try:
                if hasattr(instance, "shutdown"):
                    await instance.shutdown()
                logger.info(f"Agent shut down: {name}")
            except Exception as exc:
                logger.error(f"Error shutting down {name}: {exc}")
        self._instances.clear()

    async def unregister(self, *args, **kwargs):
        return dict()


# ── Module-level singleton — generated agents call agent_registry.register() ─
agent_registry = AgentRegistry()
