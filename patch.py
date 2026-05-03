#!/usr/bin/env python3
"""
Physics Discovery System v3.0 — Synthesis Quality Patch
========================================================
RAP Corp | Renaissance of American Physics

Applies targeted synthesis-coherence fixes to AI-generated modules that
the installer's desc-field prompts may not reliably reproduce verbatim.

  Patch A — thinking/self_refine.py
      Adds a 'coherence' criterion (weight 2.0) to the default rubric so
      the Generate→Critique→Refine loop explicitly scores whether cited
      papers form a logical argument chain rather than a keyword-matched
      concatenation of summaries from incompatible frameworks.

  Patch B — thinking/reflection.py  (three sub-patches)
      B1: Adds COHERENCE to ReflectionCriteria enum (weight 0.20, tied
          with ACCURACY as the highest-weighted criterion).
      B2: Adds optional agent= parameter to ReflectionPattern.__init__
          so a live LLM can be injected for real critique.
      B3: Replaces the stub heuristic in _score_criteria (length/keyword
          scoring) with a real self.agent.process_message() call that
          returns structured JSON scores; falls back to the heuristic
          only when agent is None.

  Patch C — agents/orchestrator.py  (five sub-patches)
      C1: Structured 4-criteria confidence check in _pattern_down_adaptive
          (inter_paper_coherence weighted ×2).
      C2: _pattern_reflection wired to ReflectionPattern(agent=gemini).
      C3: _build_reasoning_prompt — silent exclusion + 8 new instructions
          (mainstream/fringe, theoretical incompatibilities, quantitative
          experimental reach, strengthened conclusion).
      C4: _clean_output() helper strips file paths / viewer labels / page
          counts from output.
      C5: '## Analysis' header (removes pattern label).

Run after install.py (or any time modules are regenerated):
    python patch.py

Safe to run multiple times — each sub-patch checks for its sentinel
string before making any change.
"""

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Colour helpers ────────────────────────────────────────────────────────────

try:
    import ctypes
    ctypes.windll.kernel32.SetConsoleMode(
        ctypes.windll.kernel32.GetStdHandle(-11), 7)
except Exception:
    pass

OK   = "\033[92m[OK]\033[0m"
SKIP = "\033[93m[--]\033[0m"
FAIL = "\033[91m[!!]\033[0m"


# ── Core apply helper ─────────────────────────────────────────────────────────

def apply(path: Path, sentinel: str, old: str, new: str, label: str) -> bool:
    """
    Apply one string-replacement patch to *path*.

    * If *sentinel* is already present  → skip (idempotent).
    * If *old* is not found             → warn (AI generated differently).
    * Otherwise replace *old* with *new* exactly once and write the file.

    Returns True when a change was written.
    """
    if not path.exists():
        print(f"  {FAIL} {label}: {path} not found — run install.py first")
        return False

    src = path.read_text(encoding="utf-8", errors="replace")

    if sentinel in src:
        print(f"  {SKIP} {label}: already applied")
        return False

    if old not in src:
        print(f"  {FAIL} {label}: insertion point not found in {path}")
        print(f"         The AI may have generated a different structure.")
        print(f"         Expected to find:\n         {old[:120]!r}")
        return False

    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  {OK} {label}")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# PATCH A — thinking/self_refine.py
# ══════════════════════════════════════════════════════════════════════════════

SELF_REFINE = Path("thinking/self_refine.py")

# A1: coherence criterion in default rubric
_A1_SENTINEL = '"coherence"'
_A1_OLD = (
    '            RubricCriterion("accuracy", "Mathematical and scientific accuracy", 2.0),\n'
    '            RubricCriterion("clarity", "Clear and understandable presentation", 1.5),\n'
)
_A1_NEW = (
    '            RubricCriterion("accuracy", "Mathematical and scientific accuracy", 2.0),\n'
    '            RubricCriterion(\n'
    '                "coherence",\n'
    '                "Logical dependency chain between cited papers — do they form a connected "\n'
    '                "argument with explicit inferential steps, or are papers from incompatible "\n'
    '                "theoretical frameworks (classical GR, metric-affine, scalar-tensor, etc.) "\n'
    '                "mixed without justification?",\n'
    '                2.0,\n'
    '            ),\n'
    '            RubricCriterion("clarity", "Clear and understandable presentation", 1.5),\n'
)


def patch_a(verbose: bool = True) -> int:
    """Apply all self_refine.py patches. Returns number of changes made."""
    if verbose:
        print(f"\nPatch A — {SELF_REFINE}")
    n = 0
    n += apply(SELF_REFINE, _A1_SENTINEL, _A1_OLD, _A1_NEW,
               "A1: coherence criterion in default rubric")
    return n


# ══════════════════════════════════════════════════════════════════════════════
# PATCH B — thinking/reflection.py
# ══════════════════════════════════════════════════════════════════════════════

REFLECTION = Path("thinking/reflection.py")

# B1: COHERENCE in ReflectionCriteria enum
_B1_SENTINEL = 'COHERENCE = "coherence"'
_B1_OLD = (
    '    FEASIBILITY = "feasibility"\n'
)
_B1_NEW = (
    '    FEASIBILITY = "feasibility"\n'
    '    COHERENCE = "coherence"\n'
)

# B2: COHERENCE weight in get_weighted_score
_B2_SENTINEL = 'ReflectionCriteria.COHERENCE: 0.20'
_B2_OLD = (
    '            ReflectionCriteria.ACCURACY: 0.25,\n'
    '            ReflectionCriteria.RIGOR: 0.20,\n'
    '            ReflectionCriteria.COMPLETENESS: 0.15,\n'
    '            ReflectionCriteria.CONSISTENCY: 0.15,\n'
    '            ReflectionCriteria.CLARITY: 0.10,\n'
    '            ReflectionCriteria.RELEVANCE: 0.10,\n'
    '            ReflectionCriteria.NOVELTY: 0.03,\n'
    '            ReflectionCriteria.FEASIBILITY: 0.02\n'
)
_B2_NEW = (
    '            ReflectionCriteria.ACCURACY: 0.20,\n'
    '            ReflectionCriteria.COHERENCE: 0.20,\n'
    '            ReflectionCriteria.RIGOR: 0.18,\n'
    '            ReflectionCriteria.COMPLETENESS: 0.12,\n'
    '            ReflectionCriteria.CONSISTENCY: 0.12,\n'
    '            ReflectionCriteria.CLARITY: 0.08,\n'
    '            ReflectionCriteria.RELEVANCE: 0.08,\n'
    '            ReflectionCriteria.NOVELTY: 0.01,\n'
    '            ReflectionCriteria.FEASIBILITY: 0.01,\n'
)

# B3: agent= parameter in __init__
_B3_SENTINEL = 'self.agent = agent'
_B3_OLD = (
    '    def __init__(self,      memory: Optional[PersistentMemory] = None, **kwargs):\n'
    '        self.memory = memory or PersistentMemory()\n'
    '        self.improvement_trackers: Dict[str, ImprovementTracker] = {}\n'
    '        self.critique_model = "claude-3-5-sonnet"  # Different model for critique\n'
    '        self.generation_model = "gpt-4o"  # Model that generated original content\n'
)
_B3_NEW = (
    '    def __init__(self, memory: Optional[PersistentMemory] = None, agent=None, **kwargs):\n'
    '        self.memory = memory or PersistentMemory()\n'
    '        self.agent = agent\n'
    '        self.improvement_trackers: Dict[str, ImprovementTracker] = {}\n'
    '        self.critique_model = "claude-3-5-sonnet"\n'
    '        self.generation_model = "gpt-4o"\n'
)

# B4: replace stub _score_criteria with real LLM call
_B4_SENTINEL = 'self.agent.process_message(prompt)'
_B4_OLD = (
    '        # TODO: Integrate with actual LLM API for critique model\n'
    '        # For now, simulate scoring based on content analysis\n'
    '        await asyncio.sleep(0.1)  # Simulate API call\n'
    '        \n'
    '        # Simple heuristic scoring (replace with actual LLM call)\n'
    '        base_score = min(len(content) / 1000, 0.8)  # Length-based baseline\n'
    '        confidence = 0.7\n'
    '        \n'
    '        criteria_adjustments = {\n'
    '            ReflectionCriteria.ACCURACY: 0.1 if "physics" in content.lower() else -0.1,\n'
    '            ReflectionCriteria.COMPLETENESS: 0.1 if len(content) > 500 else -0.2,\n'
    '            ReflectionCriteria.CLARITY: 0.1 if len(content.split()) < 200 else -0.1,\n'
    '            ReflectionCriteria.CONSISTENCY: 0.0,  # Neutral\n'
    '            ReflectionCriteria.NOVELTY: 0.05 if "new" in content.lower() else -0.05,\n'
    '            ReflectionCriteria.RIGOR: 0.1 if "equation" in content.lower() else -0.1,\n'
    '            ReflectionCriteria.RELEVANCE: 0.05,  # Slight positive bias\n'
    '            ReflectionCriteria.FEASIBILITY: -0.05  # Slight skepticism\n'
    '        }\n'
    '        \n'
    '        adjusted_score = max(0.0, min(1.0, base_score + criteria_adjustments.get(criteria, 0.0)))\n'
    '        \n'
    '        return {\n'
    '            "score": adjusted_score,\n'
    '            "reasoning": f"Assessment based on {criteria.value} criteria: content demonstrates {adjusted_score:.1f} quality level",\n'
    '            "confidence": confidence\n'
    '        }\n'
)
_B4_NEW = (
    '        import re as _re\n'
    '        criteria_prompts = {\n'
    '            ReflectionCriteria.ACCURACY: (\n'
    '                "Evaluate the factual accuracy of every claim. "\n'
    '                "Flag any assertion not directly supported by the cited evidence."\n'
    '            ),\n'
    '            ReflectionCriteria.COMPLETENESS: (\n'
    '                "Assess how thoroughly the question is answered given the available evidence."\n'
    '            ),\n'
    '            ReflectionCriteria.CLARITY: (\n'
    '                "Evaluate how clearly and logically the argument is expressed."\n'
    '            ),\n'
    '            ReflectionCriteria.CONSISTENCY: (\n'
    '                "Check for internal logical consistency. "\n'
    '                "Identify contradictions or unsupported inferential leaps."\n'
    '            ),\n'
    '            ReflectionCriteria.NOVELTY: (\n'
    '                "Assess the originality and depth of insight beyond simple summarisation."\n'
    '            ),\n'
    '            ReflectionCriteria.RIGOR: (\n'
    '                "Evaluate methodological rigor: are equations used correctly, "\n'
    '                "are approximations justified, are confidence levels stated?"\n'
    '            ),\n'
    '            ReflectionCriteria.RELEVANCE: (\n'
    '                "Assess whether every cited paper is genuinely relevant to the central argument."\n'
    '            ),\n'
    '            ReflectionCriteria.FEASIBILITY: (\n'
    '                "Evaluate whether the conclusions are experimentally or theoretically testable."\n'
    '            ),\n'
    '            ReflectionCriteria.COHERENCE: (\n'
    '                "Evaluate whether the cited papers form a logically connected chain of reasoning. "\n'
    '                "Are the inferential steps between papers explicit? "\n'
    '                "Are papers from incompatible theoretical frameworks (e.g. classical GR, "\n'
    '                "metric-affine gravity, scalar-tensor theories) mixed without justification? "\n'
    '                "Does the synthesis build a unified argument or merely concatenate summaries?"\n'
    '            ),\n'
    '        }\n'
    '\n'
    '        prompt = (\n'
    '            f"As an expert physics critic, {criteria_prompts[criteria]}\\n\\n"\n'
    '            f"Content to evaluate:\\n{content}\\n\\n"\n'
    '            f"Respond in JSON format only — no preamble:\\n"\n'
    '            f\'{"score": <float 0.0-1.0>, \'\n'
    '            f\'"reasoning": "<detailed explanation>", \'\n'
    '            f\'"confidence": <float 0.0-1.0>}\'\n'
    '        )\n'
    '\n'
    '        if self.agent is not None:\n'
    '            try:\n'
    '                response = await self.agent.process_message(prompt)\n'
    '                critique_text = (\n'
    '                    response.get("content", "") if isinstance(response, dict) else str(response)\n'
    '                )\n'
    '                json_match = _re.search(r\'\\{[^{}]*\\}\', critique_text, _re.DOTALL)\n'
    '                if json_match:\n'
    '                    data = json.loads(json_match.group())\n'
    '                    return {\n'
    '                        "score": max(0.0, min(1.0, float(data.get("score", 0.5)))),\n'
    '                        "reasoning": str(data.get("reasoning", "")),\n'
    '                        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.7)))),\n'
    '                    }\n'
    '            except Exception as e:\n'
    '                logger.warning(f"LLM critique failed for {criteria.value}: {e}")\n'
    '\n'
    '        # Fallback heuristic — only reached when agent is unavailable or call fails\n'
    '        base_score = min(len(content) / 1000, 0.8)\n'
    '        criteria_adjustments = {\n'
    '            ReflectionCriteria.ACCURACY: 0.1 if "physics" in content.lower() else -0.1,\n'
    '            ReflectionCriteria.COMPLETENESS: 0.1 if len(content) > 500 else -0.2,\n'
    '            ReflectionCriteria.CLARITY: 0.1 if len(content.split()) < 200 else -0.1,\n'
    '            ReflectionCriteria.CONSISTENCY: 0.0,\n'
    '            ReflectionCriteria.NOVELTY: 0.05 if "new" in content.lower() else -0.05,\n'
    '            ReflectionCriteria.RIGOR: 0.1 if "equation" in content.lower() else -0.1,\n'
    '            ReflectionCriteria.RELEVANCE: 0.05,\n'
    '            ReflectionCriteria.FEASIBILITY: -0.05,\n'
    '            ReflectionCriteria.COHERENCE: -0.15,\n'
    '        }\n'
    '        adjusted_score = max(0.0, min(1.0, base_score + criteria_adjustments.get(criteria, 0.0)))\n'
    '        return {\n'
    '            "score": adjusted_score,\n'
    '            "reasoning": (\n'
    '                f"Heuristic fallback (agent unavailable): "\n'
    '                f"{criteria.value} scored {adjusted_score:.2f}"\n'
    '            ),\n'
    '            "confidence": 0.3,\n'
    '        }\n'
)

# B5: COHERENCE suggestion in _generate_criteria_suggestion
_B5_SENTINEL = 'ReflectionCriteria.COHERENCE: (\n'
_B5_OLD = (
    '            ReflectionCriteria.FEASIBILITY: "Address practical implementation challenges"\n'
    '        }\n'
)
_B5_NEW = (
    '            ReflectionCriteria.FEASIBILITY: "Address practical implementation challenges",\n'
    '            ReflectionCriteria.COHERENCE: (\n'
    '                "Rebuild the argument as an explicit logical chain: state the inferential step "\n'
    '                "each paper contributes, and remove papers from incompatible theoretical "\n'
    '                "frameworks that are included without justification"\n'
    '            ),\n'
    '        }\n'
)


def patch_b(verbose: bool = True) -> int:
    """Apply all reflection.py patches. Returns number of changes made."""
    if verbose:
        print(f"\nPatch B — {REFLECTION}")
    n = 0
    n += apply(REFLECTION, _B1_SENTINEL, _B1_OLD, _B1_NEW,
               "B1: COHERENCE in ReflectionCriteria enum")
    n += apply(REFLECTION, _B2_SENTINEL, _B2_OLD, _B2_NEW,
               "B2: COHERENCE weight in get_weighted_score")
    n += apply(REFLECTION, _B3_SENTINEL, _B3_OLD, _B3_NEW,
               "B3: agent= parameter in __init__")
    n += apply(REFLECTION, _B4_SENTINEL, _B4_OLD, _B4_NEW,
               "B4: real LLM call in _score_criteria (replace stub heuristic)")
    n += apply(REFLECTION, _B5_SENTINEL, _B5_OLD, _B5_NEW,
               "B5: COHERENCE suggestion in _generate_criteria_suggestion")
    return n


# ══════════════════════════════════════════════════════════════════════════════
# PATCH C — agents/orchestrator.py
# ══════════════════════════════════════════════════════════════════════════════

ORCHESTRATOR = Path("agents/orchestrator.py")

# C1: structured 4-criteria confidence check in _pattern_down_adaptive
_C1_SENTINEL = 'inter_paper_coherence'
_C1_OLD = (
    '        # Quick self-assessment\n'
    '        confidence_prompt = (\n'
    '            f"Rate your confidence in this physics answer on a scale of 0-10.\\n"\n'
    '            f"Consider: factual accuracy, completeness, reasoning rigour.\\n"\n'
    '            f"Respond with ONLY a number.\\n\\n"\n'
    '            f"Answer:\\n{initial}"\n'
    '        )\n'
    '        score_str = await gemini.generate(confidence_prompt)\n'
    '        try:\n'
    '            score = float(score_str.strip().split()[0])\n'
    '        except Exception:\n'
    '            score = 5.0\n'
    '\n'
    '        logger.info(f"DOWN adaptive — initial confidence score: {score:.1f}/10")\n'
    '\n'
    '        if score < 7.0:\n'
    '            logger.info("Confidence below threshold — running self_refine")\n'
    '            return await self._pattern_self_refine(query, papers_text, gemini)\n'
    '\n'
    '        return initial\n'
)
_C1_NEW = (
    '        import json as _json\n'
    '        import re as _re\n'
    '        confidence_prompt = (\n'
    '            f"Rate this physics analysis on four criteria. "\n'
    '            f"Respond with JSON only — no other text.\\n\\n"\n'
    '            f"Analysis:\\n{initial}\\n\\n"\n'
    '            f"Criteria (score each 0-10):\\n"\n'
    '            f"1. inter_paper_coherence: Do the cited papers form a logically connected "\n'
    '            f"argument with explicit inferential steps? Are papers from incompatible "\n'
    '            f"frameworks (classical GR vs. metric-affine vs. scalar-tensor) mixed without "\n'
    '            f"justification?\\n"\n'
    '            f"2. factual_accuracy: Are individual claims about each paper correct and "\n'
    '            f"supported by the paper\'s content?\\n"\n'
    '            f"3. framework_consistency: Does the analysis stay within a consistent "\n'
    '            f"theoretical framework, or conflate distinct models without explanation?\\n"\n'
    '            f"4. evidence_support: Do the conclusions follow from the weight of the cited "\n'
    '            f"evidence?\\n\\n"\n'
    '            f\'{{"inter_paper_coherence": N, "factual_accuracy": N, \'\n'
    '            f\'"framework_consistency": N, "evidence_support": N}}\'\n'
    '        )\n'
    '        score_text = await gemini.generate(confidence_prompt)\n'
    '        try:\n'
    '            json_match = _re.search(r\'\\{[^{}]*\\}\', score_text, _re.DOTALL)\n'
    '            if json_match:\n'
    '                scores = _json.loads(json_match.group())\n'
    '                weighted = (\n'
    '                    scores.get("inter_paper_coherence", 5) * 2\n'
    '                    + scores.get("factual_accuracy", 5)\n'
    '                    + scores.get("framework_consistency", 5)\n'
    '                    + scores.get("evidence_support", 5)\n'
    '                ) / 5.0\n'
    '            else:\n'
    '                weighted = 5.0\n'
    '        except Exception:\n'
    '            weighted = 5.0\n'
    '\n'
    '        logger.info(f"DOWN adaptive — structured confidence: {weighted:.1f}/10")\n'
    '\n'
    '        if weighted < 7.0:\n'
    '            logger.info("Confidence below threshold — running self_refine")\n'
    '            return await self._pattern_self_refine(query, papers_text, gemini)\n'
    '\n'
    '        return initial\n'
)

# C2: wire ReflectionPattern into _pattern_reflection
_C2_SENTINEL = 'from thinking.reflection import ReflectionPattern'
_C2_OLD = (
    '        logger.info("Pattern: reflection")\n'
    '        prompt = self._build_reasoning_prompt(query, papers_text)\n'
    '\n'
    '        initial = await gemini.generate(prompt)\n'
    '\n'
    '        reflect_prompt = (\n'
    '            f"Reflect critically on this physics analysis. Identify:\\n"\n'
    '            f"1. Any factual errors or unsupported claims\\n"\n'
    '            f"2. Important aspects of the question that weren\'t addressed\\n"\n'
    '            f"3. Logical gaps in the reasoning\\n"\n'
    '            f"4. Whether conclusions actually follow from the cited evidence\\n\\n"\n'
    '            f"Original question: {query}\\n\\n"\n'
    '            f"Analysis to reflect on:\\n{initial}"\n'
    '        )\n'
    '        reflection = await gemini.generate(reflect_prompt)\n'
    '\n'
    '        improve_prompt = (\n'
    '            f"Using this reflection, produce a final, improved analysis.\\n\\n"\n'
    '            f"Original question: {query}\\n\\n"\n'
    '            f"Research context:\\n{papers_text}\\n\\n"\n'
    '            f"Previous analysis:\\n{initial}\\n\\n"\n'
    '            f"Reflection / critique:\\n{reflection}\\n\\n"\n'
    '            f"Write the final improved answer now:"\n'
    '        )\n'
    '        return await gemini.generate(improve_prompt)\n'
)
_C2_NEW = (
    '        import uuid as _uuid\n'
    '        from thinking.reflection import ReflectionPattern\n'
    '        logger.info("Pattern: reflection")\n'
    '\n'
    '        prompt = self._build_reasoning_prompt(query, papers_text)\n'
    '        initial = await gemini.generate(prompt)\n'
    '\n'
    '        pattern = ReflectionPattern(agent=gemini)\n'
    '        reflection_result = await pattern.reflect(initial, str(_uuid.uuid4()))\n'
    '\n'
    '        low_criteria = [\n'
    '            f"- {s.criteria.value} (score {s.score:.2f}): {s.reasoning}"\n'
    '            for s in reflection_result.transparency_scores\n'
    '            if s.score < 0.7\n'
    '        ]\n'
    '        critique_summary = (\n'
    '            "\\n".join(low_criteria)\n'
    '            if low_criteria\n'
    '            else "All criteria passed threshold — minor refinements only."\n'
    '        )\n'
    '\n'
    '        improve_prompt = (\n'
    '            f"Using this structured critique, produce a final improved analysis.\\n\\n"\n'
    '            f"Original question: {query}\\n\\n"\n'
    '            f"Research context:\\n{papers_text}\\n\\n"\n'
    '            f"Previous analysis:\\n{initial}\\n\\n"\n'
    '            f"Structured critique (criteria scoring below 0.7):\\n{critique_summary}\\n\\n"\n'
    '            f"Pay special attention to inter-paper coherence: rebuild the argument as "\n'
    '            f"an explicit logical chain, stating the inferential step each paper "\n'
    '            f"contributes, and exclude any paper that does not advance the argument.\\n\\n"\n'
    '            f"Write the final improved answer now:"\n'
    '        )\n'
    '        return await gemini.generate(improve_prompt)\n'
)

# C3: BUILD A LOGICAL CHAIN + 8-instruction prompt (replaces old 5-instruction version)
_C3_SENTINEL = 'MAINSTREAM VS. FRINGE'
_C3_OLD = (
    '            f"1. CITE EVIDENCE EXPLICITLY — for every claim, name the specific paper "\n'
    '            f"title or authors from the evidence above. Do not make uncited assertions.\\n\\n"\n'
    '            f"2. COVER ALL RELEVANT PAPERS — go through the retrieved evidence "\n'
    '            f"systematically. Do not silently ignore papers; if a paper is tangential, "\n'
    '            f"say so and explain why.\\n\\n"\n'
    '            f"3. REASON IN DEPTH — explain the physics mechanisms involved "\n'
    '            f"(relevant equations, energy scales, symmetries, theoretical frameworks). "\n'
    '            f"Do not summarise superficially.\\n\\n"\n'
    '            f"4. ADDRESS OPEN QUESTIONS — identify what the evidence leaves unresolved, "\n'
    '            f"what experiments would settle them, and what the most promising "\n'
    '            f"theoretical directions are.\\n\\n"\n'
    '            f"5. STATE A CONCLUSION — end with a clear, direct answer to the question "\n'
    '            f"based on the weight of the evidence.\\n\\n"\n'
    '            f"Your response should be comprehensive — do not truncate or abbreviate. "\n'
    '            f"A thorough analysis is expected."\n'
)
_C3_NEW = (
    '            f"1. CITE EVIDENCE EXPLICITLY — for every claim, name the specific paper "\n'
    '            f"title or authors from the evidence above. Do not make uncited assertions.\\n\\n"\n'
    '            f"2. BUILD A LOGICAL CHAIN — only cite papers that contribute a specific "\n'
    '            f"inferential step to your argument. For each cited paper, state explicitly "\n'
    '            f"what claim it supports and how it connects to the next step. If a retrieved "\n'
    '            f"paper belongs to an incompatible theoretical framework or does not advance "\n'
    '            f"the central argument, exclude it silently — do not list, mention, or "\n'
    '            f"reference excluded papers anywhere in your response.\\n\\n"\n'
    '            f"3. MAINSTREAM VS. FRINGE — before citing any paper, classify its central "\n'
    '            f"claim as either mainstream consensus (widely accepted, peer-reviewed, "\n'
    '            f"consistent with SR/GR/QFT) or a minority/fringe position (contested, "\n'
    '            f"contradicts established physics, not in standard textbooks). Minority "\n'
    '            f"positions must be explicitly labelled as such and must not be treated on "\n'
    '            f"equal footing with mainstream results. If a fringe claim would undermine "\n'
    '            f"the logical coherence of the argument, exclude it silently.\\n\\n"\n'
    '            f"4. ADDRESS THEORETICAL INCOMPATIBILITIES — when the evidence draws on "\n'
    '            f"multiple theoretical frameworks (e.g. f(R) gravity, Lovelock gravity, "\n'
    '            f"Yang-Mills, scalar-tensor theories), explicitly state whether each pair "\n'
    '            f"is mathematically compatible, a complementary approximation in different "\n'
    '            f"regimes, or a mutually exclusive alternative. Do not present them as an "\n'
    '            f"interchangeable menu of options.\\n\\n"\n'
    '            f"5. REASON IN DEPTH — explain the physics mechanisms involved "\n'
    '            f"(relevant equations, energy scales, symmetries, theoretical frameworks). "\n'
    '            f"Do not summarise superficially.\\n\\n"\n'
    '            f"6. QUANTIFY EXPERIMENTAL REACH — for any predicted observable effect, "\n'
    '            f"include a quantitative estimate of the energy scale, detector precision, "\n'
    '            f"or instrumental sensitivity required to test it. State explicitly how "\n'
    '            f"far this is from current experimental capability (e.g. LHC reach, LIGO "\n'
    '            f"sensitivity, current CMB resolution).\\n\\n"\n'
    '            f"7. ADDRESS OPEN QUESTIONS — identify what the evidence leaves unresolved "\n'
    '            f"and what specific experiment or derivation would most advance the field.\\n\\n"\n'
    '            f"8. STATE A CONCLUSION — write a synthesis that goes beyond summarising "\n'
    '            f"the points above. It must identify: (a) what the weight of mainstream "\n'
    '            f"evidence actually establishes vs. what remains speculative, (b) which "\n'
    '            f"theoretical incompatibilities must be resolved for a unified framework, "\n'
    '            f"and (c) what the single most tractable next step is.\\n\\n"\n'
    '            f"Your response should be comprehensive — do not truncate or abbreviate. "\n'
    '            f"A thorough analysis is expected."\n'
)

# C4: _clean_output helper
_C4_SENTINEL = 'def _clean_output'
_C4_OLD = (
    '    async def _direct_gemini(\n'
    '        self, query: str, papers_text: str, gemini\n'
    '    ) -> str:\n'
    '        """Fallback: single direct Gemini call."""\n'
    '        return await gemini.generate(self._build_reasoning_prompt(query, papers_text))\n'
)
_C4_NEW = (
    '    def _clean_output(self, text: str) -> str:\n'
    '        """Strip machine-generated artifacts from output text."""\n'
    '        import re\n'
    '        text = re.sub(r\'file:///[^\\s\\)\\]]+\', \'\', text)\n'
    '        text = re.sub(r\'[A-Za-z]:\\\\\\\\(?:[^\\s\\)\\]]+)\', \'\', text)\n'
    '        text = re.sub(r\'\\bPage\\s+\\d+\\s+of\\s+\\d+\\b\', \'\', text, flags=re.IGNORECASE)\n'
    '        text = re.sub(r\'\\b\\d+/\\d+\\b(?=\\s*$)\', \'\', text, flags=re.MULTILINE)\n'
    '        text = re.sub(\n'
    '            r\'\\b(Research JSON Viewer|Analysis \\(pattern:[^)]+\\))\\b\', \'\', text\n'
    '        )\n'
    '        text = re.sub(r\'\\n{3,}\', \'\\n\\n\', text)\n'
    '        return text.strip()\n'
    '\n'
    '    async def _direct_gemini(\n'
    '        self, query: str, papers_text: str, gemini\n'
    '    ) -> str:\n'
    '        """Fallback: single direct Gemini call."""\n'
    '        return await gemini.generate(self._build_reasoning_prompt(query, papers_text))\n'
)

# C5: clean output in run() + strip "Analysis (pattern: ...)" label
_C5_SENTINEL = 'self._clean_output(papers_text)'
_C5_OLD = (
    '        return (\n'
    '            f"## Retrieved Evidence\\n\\n"\n'
    '            f"{papers_text}"\n'
    '            f"{divider}"\n'
    '            f"## Analysis  (pattern: {pattern})\\n\\n"\n'
    '            f"{answer}"\n'
    '        )\n'
)
_C5_NEW = (
    '        return (\n'
    '            f"## Retrieved Evidence\\n\\n"\n'
    '            f"{self._clean_output(papers_text)}"\n'
    '            f"{divider}"\n'
    '            f"## Analysis\\n\\n"\n'
    '            f"{self._clean_output(answer)}"\n'
    '        )\n'
)


def patch_c(verbose: bool = True) -> int:
    """Apply all orchestrator.py patches. Returns number of changes made."""
    if verbose:
        print(f"\nPatch C — {ORCHESTRATOR}")
    n = 0
    n += apply(ORCHESTRATOR, _C1_SENTINEL, _C1_OLD, _C1_NEW,
               "C1: structured 4-criteria confidence check in _pattern_down_adaptive")
    n += apply(ORCHESTRATOR, _C2_SENTINEL, _C2_OLD, _C2_NEW,
               "C2: wire ReflectionPattern into _pattern_reflection")
    n += apply(ORCHESTRATOR, _C3_SENTINEL, _C3_OLD, _C3_NEW,
               "C3: 8-instruction reasoning prompt (logical chain + fringe + incompatibilities)")
    n += apply(ORCHESTRATOR, _C4_SENTINEL, _C4_OLD, _C4_NEW,
               "C4: _clean_output() helper method")
    n += apply(ORCHESTRATOR, _C5_SENTINEL, _C5_OLD, _C5_NEW,
               "C5: clean output + strip 'Analysis (pattern:...)' label in run()")
    return n


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("\n+==========================================+")
    print("|  Physics Discovery System v3.0           |")
    print("|  Synthesis Quality Patch                 |")
    print("|  RAPCorp | Renaissance of American Physics|")
    print("+==========================================+\n")
    print("Applying patches to AI-generated modules...\n")

    total   = 0
    total  += patch_a()
    total  += patch_b()
    total  += patch_c()

    print(f"\n{'─' * 44}")
    if total == 0:
        print("All patches already applied — nothing changed.")
    else:
        print(f"{total} patch(es) applied successfully.")
    print(
        "\nNext step: python main.py \"your physics question\"\n"
    )


if __name__ == "__main__":
    main()
