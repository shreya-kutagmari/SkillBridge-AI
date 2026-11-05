"""
agents/ai_roadmap_agent.py
---------------------------
AI-enhanced learning roadmap generator.

Tries IBM watsonx.ai to produce a richer, narrative roadmap enriched with
local Bengaluru context. Falls back to the structured rule-based
roadmap_agent when AI is unavailable or returns empty output.

Public API (same shape as roadmap_agent.generate_roadmap):
    ai_generate_roadmap(missing_skills: list[str]) -> dict

The returned dict always matches the structure from generate_roadmap():
    {
        "total_skills":   int,
        "total_est_days": int,
        "stages":         {"Foundation": [...], "Intermediate": [...], "Advanced": [...]},
        "ordered_steps":  [...],
        "ai_narrative":   str | None   ← NEW field; None when rule-based only
    }
"""

from __future__ import annotations

import json
import logging

from agents.ai_client import generate_text, is_available
from agents.roadmap_agent import generate_roadmap as _rule_based_roadmap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are SkillBridge AI, a career coach for Bengaluru students and fresh graduates. "
    "Given a list of skills a candidate needs to learn, write a short, encouraging "
    "learning narrative (3–5 sentences, under 120 words). "
    "Include: estimated total learning time, the most important first step, "
    "and one free local or online resource for the top skill. "
    "Be specific and practical. Do not repeat the full list of skills verbatim."
)


def _build_narrative_prompt(missing_skills: list[str], total_days: int) -> str:
    skills_str = ", ".join(missing_skills[:10])  # cap at 10 for prompt length
    return (
        f"{_SYSTEM}\n\n"
        f"Skills to learn: {skills_str}\n"
        f"Total estimated learning time: {total_days} days\n\n"
        f"Learning narrative:"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ai_generate_roadmap(missing_skills: list[str]) -> dict:
    """
    Generate a learning roadmap for *missing_skills*.

    Always produces the full structured roadmap from generate_roadmap().
    Additionally tries to attach an AI-generated narrative in `ai_narrative`.

    Parameters
    ----------
    missing_skills : list[str]

    Returns
    -------
    dict — same shape as generate_roadmap(), plus "ai_narrative": str | None
    """
    # Always run the rule-based engine first — it's the authoritative structure
    roadmap = _rule_based_roadmap(missing_skills)
    roadmap["ai_narrative"] = None  # default

    if not missing_skills or not roadmap["ordered_steps"]:
        return roadmap

    if not is_available():
        logger.debug(
            "ai_generate_roadmap: watsonx.ai not configured — rule-based roadmap only"
        )
        return roadmap

    prompt = _build_narrative_prompt(
        [s["skill"] for s in roadmap["ordered_steps"]],
        roadmap["total_est_days"],
    )
    narrative = generate_text(prompt, max_new_tokens=180)

    if narrative and narrative.strip():
        roadmap["ai_narrative"] = narrative.strip()
        logger.info(
            "ai_generate_roadmap: AI narrative attached (%d chars)", len(narrative)
        )
    else:
        logger.warning(
            "ai_generate_roadmap: AI returned empty/None — narrative omitted"
        )

    return roadmap
