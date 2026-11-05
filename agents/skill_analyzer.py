"""
agents/skill_analyzer.py
------------------------
Analyses the gap between a candidate's current skills and a role's required
skills, then delegates roadmap generation to roadmap_agent.

Public API (unchanged signature, richer output):
    analyze_skill_gap(current_skills, required_skills) -> dict
"""

from __future__ import annotations
from agents.roadmap_agent import generate_roadmap


def _normalise(skills: list) -> set[str]:
    """Return a lower-cased set of non-empty skill strings."""
    return {str(s).strip().lower() for s in skills if str(s).strip()}


def analyze_skill_gap(
    current_skills: list[str],
    required_skills: list[str],
) -> dict:
    """
    Compare candidate skills against job requirements and produce a
    structured gap analysis with a prioritised learning roadmap.

    Parameters
    ----------
    current_skills  : list of skills the candidate already has
    required_skills : list of skills the target role requires

    Returns
    -------
    dict with keys:
        matched         – sorted list of skills candidate already has
        missing         – sorted list of skills candidate needs to acquire
        coverage        – int percentage of required skills already covered
        priority_order  – missing skills sorted high-priority first
        roadmap         – full structured roadmap from roadmap_agent
        summary         – human-readable one-liner
    """
    if not isinstance(current_skills, list):
        current_skills = list(current_skills) if current_skills else []
    if not isinstance(required_skills, list):
        required_skills = list(required_skills) if required_skills else []

    current = _normalise(current_skills)
    required = _normalise(required_skills)

    matched = sorted(current & required)
    missing = sorted(required - current)

    coverage = round(len(matched) / len(required) * 100) if required else 0

    # Build roadmap for the missing skills; this also gives us priority order
    roadmap = generate_roadmap(missing)

    # Extract priority-ordered skill names from the roadmap
    priority_order = [step["skill"] for step in roadmap["ordered_steps"]]

    # Human-readable summary
    if not required:
        summary = "No required skills specified."
    elif coverage == 100:
        summary = "You already have all the required skills for this role."
    elif coverage >= 75:
        summary = (
            f"Strong match: you have {coverage}% of required skills. "
            f"Focus on {', '.join(priority_order[:2])} to be fully ready."
        )
    elif coverage >= 40:
        summary = (
            f"Partial match ({coverage}%). Key skills to build: "
            f"{', '.join(priority_order[:3])}."
        )
    else:
        summary = (
            f"Early stage ({coverage}%). Start with foundation skills: "
            f"{', '.join(priority_order[:3])}."
        )

    return {
        "matched": matched,
        "missing": missing,
        "coverage": coverage,
        "priority_order": priority_order,
        "roadmap": roadmap,
        "summary": summary,
    }
