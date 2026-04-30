"""
PhysicsOrchestrator — Physics Discovery System v3.0
RAP Corp | Renaissance of American Physics

Pipeline:
  1. Research phase  — ResearchAgent fetches ArXiv papers + vector results
  2. Thinking phase  — GeminiAgent reasons over the evidence using the chosen
                       thinking pattern (self_refine / tree_of_thoughts / etc.)
  3. Return          — formatted string with conclusions

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

        # ── Phase 1: Research ─────────────────────────────────────────────
        papers_text = await self._research_phase(query, mode)

        if not papers_text:
            return (
                f"Query received: {query}\n"
                "Note: No research results found — check logs for details."
            )

        # ── Phase 2: Thinking ─────────────────────────────────────────────
        gemini = self._build_gemini()
        if gemini is None or not gemini.available:
            logger.warning("Gemini unavailable — returning raw research results")
            return f"## Research Results\n\n{papers_text}"

        answer = await self._thinking_phase(query, papers_text, pattern, gemini)

        # ── Combine: paper list + reasoning ──────────────────────────────
        divider = "\n\n" + "═" * 60 + "\n"
        return (
            f"## Retrieved Evidence\n\n"
            f"{self._clean_output(papers_text)}"
            f"{divider}"
            f"## Analysis\n\n"
            f"{self._clean_output(answer)}"
        )

    # ── Research phase ────────────────────────────────────────────────────

    async def _research_phase(self, query: str, mode: str) -> str:
        """Run the research agent and extract usable text from its output."""
        research_agent = self._get_agent(
            "research", "agents.research_agent.ResearchAgent"
        )
        if research_agent is None:
            return ""

        try:
            if asyncio.iscoroutinefunction(research_agent.run):
                result = await research_agent.run(query, mode=mode)
            else:
                result = research_agent.run(query, mode=mode)
        except Exception as exc:
            logger.error(f"Research agent error: {exc}", exc_info=True)
            return ""

        if not result:
            return ""

        return self._extract_papers_text(result)

    def _extract_papers_text(self, result: Any) -> str:
        """
        Pull useful text out of whatever the research agent returns.
        Tries multiple known key structures before falling back to str().
        """
        if not isinstance(result, dict):
            return str(result)

        parts: list[str] = []

        # Injected by Phase 15 — combined_papers path
        content = result.get("content", "")
        if isinstance(content, str) and content:
            parts.append(content)

        # key_findings from _generate_insights
        insights = result.get("insights") or {}
        if isinstance(insights, dict):
            kf = insights.get("key_findings") or []
            if kf:
                parts.append("Key findings:\n" + "\n".join(f"  * {f}" for f in kf if f))

        # synthesis.content
        syn = result.get("synthesis") or {}
        if isinstance(syn, dict):
            sc = syn.get("content", "")
            if isinstance(sc, str) and sc and sc not in parts:
                parts.append(sc)

        return "\n\n".join(parts) if parts else str(result)

    # ── Gemini setup ──────────────────────────────────────────────────────

    def _build_gemini(self):
        """Instantiate GeminiAgent using the configured API key."""
        api_key = (
            self.settings.google_api_key
            or self.settings.llm.google_api_key
            or ""
        )
        if not api_key:
            logger.warning("GOOGLE_API_KEY not set — thinking phase disabled")
            return None
        try:
            from thinking.gemini_agent import GeminiAgent
            return GeminiAgent(api_key=api_key)
        except Exception as exc:
            logger.error(f"Could not build GeminiAgent: {exc}")
            return None

    # ── Thinking phase ────────────────────────────────────────────────────

    async def _thinking_phase(
        self,
        query: str,
        papers_text: str,
        pattern: str,
        gemini,
    ) -> str:
        """
        Dispatch to the appropriate thinking pattern.
        Each pattern uses Gemini differently to reason over the research.
        """
        logger.info(f"Starting thinking phase with pattern={pattern}")

        dispatch = {
            "self_refine":        self._pattern_self_refine,
            "reflection":         self._pattern_reflection,
            "down_adaptive":      self._pattern_down_adaptive,
            "tree_of_thoughts":   self._pattern_tree_of_thoughts,
            "lats_mcts":          self._pattern_lats_mcts,
            "reflexion_vrl":      self._pattern_reflexion_vrl,
            "multi_agent_debate": self._pattern_debate,
            "chat_eval":          self._pattern_chat_eval,
        }

        fn = dispatch.get(pattern, self._pattern_down_adaptive)
        try:
            result = await fn(query, papers_text, gemini)
            return result if isinstance(result, str) else str(result)
        except Exception as exc:
            logger.error(f"Thinking pattern '{pattern}' failed: {exc}", exc_info=True)
            # Fallback to a direct Gemini call
            return await self._direct_gemini(query, papers_text, gemini)

    # ── Pattern: down_adaptive (default) ─────────────────────────────────

    async def _pattern_down_adaptive(
        self, query: str, papers_text: str, gemini
    ) -> str:
        """
        Debate Only When Necessary — structured four-criteria confidence check:
        1. Generate an initial answer
        2. Score on inter_paper_coherence (weighted x2), factual_accuracy,
           framework_consistency, evidence_support
        3. If weighted score < 7.0 → run self_refine
        4. Return best answer
        """
        import json as _json
        import re as _re
        logger.info("Pattern: down_adaptive")

        initial = await self._direct_gemini(query, papers_text, gemini)

        confidence_prompt = (
            f"Rate this physics analysis on four criteria. "
            f"Respond with JSON only — no other text.\n\n"
            f"Analysis:\n{initial}\n\n"
            f"Criteria (score each 0-10):\n"
            f"1. inter_paper_coherence: Do the cited papers form a logically connected "
            f"argument with explicit inferential steps? Are papers from incompatible "
            f"frameworks (classical GR vs. metric-affine vs. scalar-tensor) mixed without "
            f"justification?\n"
            f"2. factual_accuracy: Are individual claims about each paper correct and "
            f"supported by the paper's content?\n"
            f"3. framework_consistency: Does the analysis stay within a consistent "
            f"theoretical framework, or conflate distinct models without explanation?\n"
            f"4. evidence_support: Do the conclusions follow from the weight of the cited "
            f"evidence?\n\n"
            f'{{"inter_paper_coherence": N, "factual_accuracy": N, '
            f'"framework_consistency": N, "evidence_support": N}}'
        )
        score_text = await gemini.generate(confidence_prompt)
        try:
            json_match = _re.search(r'\{[^{}]*\}', score_text, _re.DOTALL)
            if json_match:
                scores = _json.loads(json_match.group())
                # inter_paper_coherence weighted double — the specific failure mode we guard
                weighted = (
                    scores.get("inter_paper_coherence", 5) * 2
                    + scores.get("factual_accuracy", 5)
                    + scores.get("framework_consistency", 5)
                    + scores.get("evidence_support", 5)
                ) / 5.0
            else:
                weighted = 5.0
        except Exception:
            weighted = 5.0

        logger.info(f"DOWN adaptive — structured confidence: {weighted:.1f}/10")

        if weighted < 7.0:
            logger.info("Confidence below threshold — running self_refine")
            return await self._pattern_self_refine(query, papers_text, gemini)

        return initial

    # ── Pattern: self_refine ──────────────────────────────────────────────

    async def _pattern_self_refine(
        self, query: str, papers_text: str, gemini
    ) -> str:
        """
        Generate → Critique → Refine loop (up to 3 cycles).
        Uses the existing SelfRefiner class with GeminiAgent.
        """
        logger.info("Pattern: self_refine")
        try:
            from thinking.self_refine import SelfRefiner
            refiner = SelfRefiner(agent=gemini, max_cycles=3, quality_threshold=7.0)
            prompt = self._build_reasoning_prompt(query, papers_text)
            result = await refiner.refine(prompt)
            content = result.get("final_content", "")
            cycles = result.get("cycles_completed", 1)
            score = result.get("final_score", 0.0)
            logger.info(f"Self-refine complete: {cycles} cycles, score={score:.2f}")
            return content if content else await self._direct_gemini(query, papers_text, gemini)
        except Exception as exc:
            logger.error(f"self_refine failed: {exc}", exc_info=True)
            return await self._direct_gemini(query, papers_text, gemini)

    # ── Pattern: reflection ───────────────────────────────────────────────

    async def _pattern_reflection(
        self, query: str, papers_text: str, gemini
    ) -> str:
        """
        Generate an answer, run structured multi-criteria reflection via
        ReflectionPattern (including inter-paper coherence), then produce
        an improved version targeting the lowest-scoring criteria.
        """
        import uuid as _uuid
        from thinking.reflection import ReflectionPattern
        logger.info("Pattern: reflection")

        prompt = self._build_reasoning_prompt(query, papers_text)
        initial = await gemini.generate(prompt)

        pattern = ReflectionPattern(agent=gemini)
        reflection_result = await pattern.reflect(initial, str(_uuid.uuid4()))

        low_criteria = [
            f"- {s.criteria.value} (score {s.score:.2f}): {s.reasoning}"
            for s in reflection_result.transparency_scores
            if s.score < 0.7
        ]
        critique_summary = (
            "\n".join(low_criteria)
            if low_criteria
            else "All criteria passed threshold — minor refinements only."
        )

        improve_prompt = (
            f"Using this structured critique, produce a final improved analysis.\n\n"
            f"Original question: {query}\n\n"
            f"Research context:\n{papers_text}\n\n"
            f"Previous analysis:\n{initial}\n\n"
            f"Structured critique (criteria scoring below 0.7):\n{critique_summary}\n\n"
            f"Pay special attention to inter-paper coherence: rebuild the argument as "
            f"an explicit logical chain, stating the inferential step each paper "
            f"contributes, and exclude any paper that does not advance the argument.\n\n"
            f"Write the final improved answer now:"
        )
        return await gemini.generate(improve_prompt)

    # ── Pattern: tree_of_thoughts ─────────────────────────────────────────

    async def _pattern_tree_of_thoughts(
        self, query: str, papers_text: str, gemini
    ) -> str:
        """
        Explore 3 distinct reasoning branches (hypotheses), evaluate each,
        then synthesise the strongest into a final answer.
        """
        logger.info("Pattern: tree_of_thoughts")

        branch_prompt = (
            f"Generate 3 distinct, substantive hypotheses or reasoning paths "
            f"that could answer this physics question. Each should explore a "
            f"genuinely different theoretical angle.\n\n"
            f"Question: {query}\n\n"
            f"Research evidence:\n{papers_text}\n\n"
            f"Format as:\n"
            f"BRANCH 1: <hypothesis>\n"
            f"BRANCH 2: <hypothesis>\n"
            f"BRANCH 3: <hypothesis>"
        )
        branches_text = await gemini.generate(branch_prompt)

        # Parse branches
        branches = []
        for line in branches_text.splitlines():
            if line.startswith("BRANCH"):
                branches.append(line.split(":", 1)[-1].strip())
        if not branches:
            branches = [branches_text]

        # Evaluate each branch
        scored = []
        for i, branch in enumerate(branches):
            eval_prompt = (
                f"Evaluate this physics reasoning path.\n"
                f"Question: {query}\n"
                f"Reasoning path: {branch}\n\n"
                f"Rate it 1-10 for: (a) consistency with known physics, "
                f"(b) support from the research evidence, "
                f"(c) explanatory power.\n"
                f"Respond with: SCORE: <number>\nJUSTIFICATION: <text>"
            )
            eval_text = await gemini.generate(eval_prompt)
            score = 5.0
            for line in eval_text.splitlines():
                if line.startswith("SCORE:"):
                    try:
                        score = float(line.split(":")[1].strip().split()[0])
                    except Exception:
                        pass
            scored.append((score, branch))
            logger.info(f"Branch {i+1} score: {score:.1f}")

        scored.sort(key=lambda x: x[0], reverse=True)

        synth_prompt = (
            f"Synthesise the strongest reasoning paths into a final, definitive "
            f"physics analysis. Integrate the best insights and discard weak ones.\n\n"
            f"Question: {query}\n\n"
            f"Research evidence:\n{papers_text}\n\n"
            f"Top reasoning paths (ranked):\n"
            + "\n\n".join(f"[Score {s:.1f}] {b}" for s, b in scored)
            + "\n\nWrite the final synthesis now:"
        )
        return await gemini.generate(synth_prompt)

    # ── Pattern: lats_mcts ────────────────────────────────────────────────

    async def _pattern_lats_mcts(
        self, query: str, papers_text: str, gemini
    ) -> str:
        """
        Language Agent Tree Search: iteratively expand the most promising
        reasoning step, backpropagating quality scores.
        """
        logger.info("Pattern: lats_mcts")

        # Root thought
        root_prompt = (
            f"Begin reasoning about this physics question. "
            f"State the key physics principles at play and the first step of analysis.\n\n"
            f"Question: {query}\n\nEvidence:\n{papers_text}"
        )
        root = await gemini.generate(root_prompt)

        best = root
        best_score = 0.0

        # 3 expansion rounds
        for round_n in range(3):
            expand_prompt = (
                f"Expand on this physics reasoning. Go one level deeper — "
                f"apply the relevant equations, consider edge cases, "
                f"and draw a tentative conclusion from the evidence.\n\n"
                f"Question: {query}\n\nCurrent reasoning:\n{best}"
            )
            expanded = await gemini.generate(expand_prompt)

            score_prompt = (
                f"Score this physics reasoning 1-10 for correctness and depth.\n"
                f"Respond with only a number.\n\n{expanded}"
            )
            score_str = await gemini.generate(score_prompt)
            try:
                score = float(score_str.strip().split()[0])
            except Exception:
                score = 5.0

            logger.info(f"MCTS round {round_n+1}: score={score:.1f}")
            if score >= best_score:
                best_score = score
                best = expanded

        conclude_prompt = (
            f"Based on this multi-step reasoning, write the final conclusion "
            f"for the physics question. Be precise and cite the evidence.\n\n"
            f"Question: {query}\n\nReasoning:\n{best}"
        )
        return await gemini.generate(conclude_prompt)

    # ── Pattern: reflexion_vrl ────────────────────────────────────────────

    async def _pattern_reflexion_vrl(
        self, query: str, papers_text: str, gemini
    ) -> str:
        """
        Reflexion with verbal reinforcement: after each attempt, generate
        a verbal reward signal and use it to improve the next attempt.
        """
        logger.info("Pattern: reflexion_vrl")
        prompt = self._build_reasoning_prompt(query, papers_text)
        attempt = await gemini.generate(prompt)

        for trial in range(2):
            reward_prompt = (
                f"As a physics expert, give a verbal reward/penalty for this answer.\n"
                f"Explain specifically what was correct (reward) and what was wrong "
                f"or missing (penalty). Be concrete.\n\n"
                f"Question: {query}\nAnswer: {attempt}"
            )
            reward = await gemini.generate(reward_prompt)

            retry_prompt = (
                f"Using this feedback, write a better answer.\n\n"
                f"Question: {query}\n\n"
                f"Research:\n{papers_text}\n\n"
                f"Previous answer:\n{attempt}\n\n"
                f"Feedback:\n{reward}\n\n"
                f"Improved answer:"
            )
            attempt = await gemini.generate(retry_prompt)
            logger.info(f"Reflexion trial {trial+1} complete")

        return attempt

    # ── Pattern: multi_agent_debate ───────────────────────────────────────

    async def _pattern_debate(
        self, query: str, papers_text: str, gemini
    ) -> str:
        """
        Simulate two physicist perspectives debating, then synthesise.
        """
        logger.info("Pattern: multi_agent_debate")

        pro_prompt = (
            f"You are a physicist who believes standard quantum field theory "
            f"fully answers this question. Argue your position using the evidence.\n\n"
            f"Question: {query}\n\nEvidence:\n{papers_text}"
        )
        con_prompt = (
            f"You are a physicist who believes new physics beyond standard models "
            f"is needed to fully answer this question. Argue using the evidence.\n\n"
            f"Question: {query}\n\nEvidence:\n{papers_text}"
        )

        pro, con = await asyncio.gather(
            gemini.generate(pro_prompt),
            gemini.generate(con_prompt),
        )

        synth_prompt = (
            f"Two physicists have debated this question. Synthesise their arguments "
            f"into the most accurate, balanced conclusion supported by the evidence.\n\n"
            f"Question: {query}\n\n"
            f"Argument A (standard theory):\n{pro}\n\n"
            f"Argument B (beyond standard):\n{con}\n\n"
            f"Synthesis:"
        )
        return await gemini.generate(synth_prompt)

    # ── Pattern: chat_eval ────────────────────────────────────────────────

    async def _pattern_chat_eval(
        self, query: str, papers_text: str, gemini
    ) -> str:
        """
        Conversational evaluation: generate answer, then run a Q&A
        to probe weak points, then produce a final hardened answer.
        """
        logger.info("Pattern: chat_eval")
        prompt = self._build_reasoning_prompt(query, papers_text)
        answer = await gemini.generate(prompt)

        probe_prompt = (
            f"What are the 3 hardest follow-up questions a skeptical physicist "
            f"would ask about this answer? List only the questions.\n\n{answer}"
        )
        questions = await gemini.generate(probe_prompt)

        final_prompt = (
            f"Answer these critical questions and integrate the answers into "
            f"an improved, hardened final response.\n\n"
            f"Original question: {query}\n\n"
            f"Research:\n{papers_text}\n\n"
            f"Previous answer:\n{answer}\n\n"
            f"Critical questions:\n{questions}\n\n"
            f"Final hardened answer:"
        )
        return await gemini.generate(final_prompt)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _build_reasoning_prompt(self, query: str, papers_text: str) -> str:
        return (
            f"Physics research question: {query}\n\n"
            f"══════════════════════════════════════════\n"
            f"RETRIEVED RESEARCH EVIDENCE\n"
            f"══════════════════════════════════════════\n"
            f"{papers_text}\n\n"
            f"══════════════════════════════════════════\n"
            f"INSTRUCTIONS\n"
            f"══════════════════════════════════════════\n"
            f"Write a thorough, well-structured physics analysis that answers the "
            f"question above. Your response must:\n\n"
            f"1. CITE EVIDENCE EXPLICITLY — for every claim, name the specific paper "
            f"title or authors from the evidence above. Do not make uncited assertions.\n\n"
            f"2. BUILD A LOGICAL CHAIN — only cite papers that contribute a specific "
            f"inferential step to your argument. For each cited paper, state explicitly "
            f"what claim it supports and how it connects to the next step. If a retrieved "
            f"paper belongs to an incompatible theoretical framework or does not advance "
            f"the central argument, exclude it silently — do not list, mention, or "
            f"reference excluded papers anywhere in your response.\n\n"
            f"3. MAINSTREAM VS. FRINGE — before citing any paper, classify its central "
            f"claim as either mainstream consensus (widely accepted, peer-reviewed, "
            f"consistent with SR/GR/QFT) or a minority/fringe position (contested, "
            f"contradicts established physics, not in standard textbooks). Minority "
            f"positions must be explicitly labelled as such and must not be treated on "
            f"equal footing with mainstream results. If a fringe claim would undermine "
            f"the logical coherence of the argument, exclude it silently.\n\n"
            f"4. ADDRESS THEORETICAL INCOMPATIBILITIES — when the evidence draws on "
            f"multiple theoretical frameworks (e.g. f(R) gravity, Lovelock gravity, "
            f"Yang-Mills, scalar-tensor theories), explicitly state whether each pair "
            f"is mathematically compatible, a complementary approximation in different "
            f"regimes, or a mutually exclusive alternative. Do not present them as an "
            f"interchangeable menu of options.\n\n"
            f"5. REASON IN DEPTH — explain the physics mechanisms involved "
            f"(relevant equations, energy scales, symmetries, theoretical frameworks). "
            f"Do not summarise superficially.\n\n"
            f"6. QUANTIFY EXPERIMENTAL REACH — for any predicted observable effect, "
            f"include a quantitative estimate of the energy scale, detector precision, "
            f"or instrumental sensitivity required to test it. State explicitly how "
            f"far this is from current experimental capability (e.g. LHC reach, LIGO "
            f"sensitivity, current CMB resolution).\n\n"
            f"7. ADDRESS OPEN QUESTIONS — identify what the evidence leaves unresolved "
            f"and what specific experiment or derivation would most advance the field.\n\n"
            f"8. STATE A CONCLUSION — write a synthesis that goes beyond summarising "
            f"the points above. It must identify: (a) what the weight of mainstream "
            f"evidence actually establishes vs. what remains speculative, (b) which "
            f"theoretical incompatibilities must be resolved for a unified framework, "
            f"and (c) what the single most tractable next step is.\n\n"
            f"Your response should be comprehensive — do not truncate or abbreviate. "
            f"A thorough analysis is expected."
        )

    def _clean_output(self, text: str) -> str:
        """Strip machine-generated artifacts from output text."""
        import re
        # Remove local file paths (file:///... and Windows paths)
        text = re.sub(r'file:///[^\s\)\]]+', '', text)
        text = re.sub(r'[A-Za-z]:\\(?:[^\s\)\]]+)', '', text)
        # Remove page count artifacts (e.g. "73/73", "Page 12 of 73")
        text = re.sub(r'\bPage\s+\d+\s+of\s+\d+\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b\d+/\d+\b(?=\s*$)', '', text, flags=re.MULTILINE)
        # Remove viewer/tool labels
        text = re.sub(
            r'\b(Research JSON Viewer|Analysis \(pattern:[^)]+\))\b', '', text
        )
        # Collapse multiple blank lines left by removals
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    async def _direct_gemini(
        self, query: str, papers_text: str, gemini
    ) -> str:
        """Fallback: single direct Gemini call."""
        return await gemini.generate(self._build_reasoning_prompt(query, papers_text))
