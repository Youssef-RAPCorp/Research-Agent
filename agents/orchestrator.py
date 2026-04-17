"""
PhysicsOrchestrator — Physics Discovery System v3.0
RAP Corp | Renaissance of American Physics

All agent imports are lazy (inside methods) to prevent circular imports.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any

from config.settings import get_settings
from config.logger import get_logger
from agents.registry import AgentRegistry, agent_registry

logger = get_logger(__name__)


class PhysicsOrchestrator:
    """Master coordinator for the physics research multi-agent system."""

    def __init__(self, **kwargs):
        self.settings = get_settings()
        self.registry = AgentRegistry()
        self._agents: dict = {}
        logger.info("PhysicsOrchestrator initialised")

    # ── Required abstract-method implementations ──────────────────────────

    async def _process_cycle(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def on_message_received(self, message: Any, *args: Any, **kwargs: Any) -> None:
        pass

    # ── Lazy agent loader ─────────────────────────────────────────────────

    def _get_agent(self, name: str, cls_path: str):
        if name not in self._agents:
            try:
                module_path, cls_name = cls_path.rsplit(".", 1)
                import importlib
                mod = importlib.import_module(module_path)
                cls = getattr(mod, cls_name)
                self._agents[name] = cls()
            except Exception as exc:
                import traceback
                logger.warning(f"Could not load agent {name}: {exc}")
                logger.warning(traceback.format_exc())
                return None
        return self._agents[name]

    # ── Main entry point ──────────────────────────────────────────────────

    async def run(
        self,
        query: str,
        mode: str = "standard",
        pattern: str = "down_adaptive",
    ) -> str:
        logger.info(f"Orchestrator.run | mode={mode} pattern={pattern}")
        logger.info(f"Query: {query}")

        results: list[str] = []

        # Research phase — lazy import
        research_agent = self._get_agent(
            "research", "agents.research_agent.ResearchAgent"
        )
        if research_agent:
            try:
                if asyncio.iscoroutinefunction(research_agent.run):
                    research_result = await research_agent.run(query, mode=mode, pattern=pattern)
                else:
                    research_result = research_agent.run(query, mode=mode, pattern=pattern)
                if research_result:
                    if isinstance(research_result, dict):
                        _syn = research_result.get("synthesis") or {}
                        _txt = (_syn.get("content", "") if isinstance(_syn, dict) else "") or ""
                        if not _txt:
                            _ins = research_result.get("insights") or {}
                            _kf = (_ins.get("key_findings") or []) if isinstance(_ins, dict) else []
                            _txt = "\n".join(f"  * {f}" for f in _kf if f)
                        results.append(_txt or str(research_result))
                    else:
                        results.append(str(research_result))
            except Exception as exc:
                logger.error(f"Research agent error: {exc}", exc_info=True)

        # Synthesis phase — lazy import
        if results:
            synthesis_agent = self._get_agent(
                "synthesis", "agents.synthesis_agent.SynthesisAgent"
            )
            if synthesis_agent:
                try:
                    combined = "\n\n".join(results)
                    if asyncio.iscoroutinefunction(synthesis_agent.run):
                        final = await synthesis_agent.run(combined, query=query)
                    else:
                        final = synthesis_agent.run(combined, query=query)
                    if final:
                        return str(final)
                except Exception as exc:
                    logger.error(f"Synthesis agent error: {exc}", exc_info=True)

        return "\n\n".join(results) if results else (
            f"Query received: {query}\n"
            "Note: Agent pipeline could not complete — check logs for details."
        )
