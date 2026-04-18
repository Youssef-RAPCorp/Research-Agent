"""
GeminiAgent — thin async wrapper around google-generativeai.

Implements the  process_message(prompt) -> {"content": str}  interface
that SelfRefiner and other thinking-pattern classes expect.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# System context injected into every request so Gemini knows its role.
_PHYSICS_SYSTEM = (
    "You are an expert physics researcher and theorist working for the "
    "Renaissance of American Physics project. You have deep knowledge of "
    "quantum field theory, electrodynamics, general relativity, particle "
    "physics, and the mathematical foundations of physics. "
    "When given research papers or evidence, extract the key physics insights, "
    "identify what they imply, and reason carefully toward conclusions. "
    "Be precise, cite the evidence you use, and flag genuine uncertainties."
)


class GeminiAgent:
    """
    Async Gemini wrapper compatible with SelfRefiner / ReflectionPattern.

    process_message(prompt_or_dict) -> {"content": str}
    generate(prompt, system=None)   -> str          (convenience)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-flash-latest",
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ):
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(
                model_name=model,
                system_instruction=_PHYSICS_SYSTEM,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            self._available = True
            logger.info(f"GeminiAgent initialised with model={model}")
        except Exception as exc:
            logger.error(f"GeminiAgent init failed: {exc}")
            self._model = None
            self._available = False

    # ── Core interface ────────────────────────────────────────────────────────

    async def process_message(self, message: Any) -> Dict[str, Any]:
        """
        SelfRefiner calls  agent.process_message(prompt_str)  and reads
        response["content"].  This method satisfies that contract.
        """
        if not self._available or self._model is None:
            return {"content": "", "error": "Gemini unavailable"}

        # Accept str or dict (dict: pull "content" or "query" key)
        if isinstance(message, dict):
            prompt = message.get("content") or message.get("query") or str(message)
        else:
            prompt = str(message)

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self._model.generate_content(prompt)
            )
            return {"content": response.text}
        except Exception as exc:
            logger.error(f"Gemini generate error: {exc}")
            return {"content": "", "error": str(exc)}

    async def generate(self, prompt: str, system_override: Optional[str] = None) -> str:
        """Convenience: returns the text string directly."""
        if system_override:
            # Prepend a role instruction when the caller wants to override context
            prompt = system_override + "\n\n" + prompt
        result = await self.process_message(prompt)
        return result.get("content", "")

    @property
    def available(self) -> bool:
        return self._available
