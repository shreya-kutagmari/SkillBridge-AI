"""
agents/orchestrator.py
----------------------
Coordinates the complete SkillBridge AI career-assistance workflow.

Pipeline:
  1. parse_resume  – extract text and skills from a resume file (optional)
  2. match_jobs    – score candidate skills against all job listings
  3. gap_analysis  – identify missing skills for a chosen job
  4. roadmap       – generate a prioritised, structured learning roadmap

Each stage records what it did and why so the workflow is fully explainable.
No external API calls are made; all logic is local.

Public API:
    run_pipeline(request: dict, jobs: list[dict]) -> dict
    run_skill_pipeline(current_skills, required_skills) -> dict
"""

from __future__ import annotations
from typing import Any

from agents.job_matcher import recommend_jobs
from agents.skill_analyzer import analyze_skill_gap
from agents.roadmap_agent import generate_roadmap
from utils.resume_parser import extract_skills


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split_skills(value: Any) -> list[str]:
    """Accept a comma-string, a list, or None; always return a list."""
    if not value:
        return []
    if isinstance(value, list):
        return [s.strip() for s in value if str(s).strip()]
    return [s.strip() for s in str(value).split(",") if s.strip()]


def _explain_match_score(score: int) -> str:
    if score == 100:
        return "Perfect skill match — you meet every listed requirement."
    if score >= 75:
        return f"{score}% skill overlap — strong match, minor gaps remain."
    if score >= 40:
        return f"{score}% skill overlap — partial match; focused learning will close the gap."
    return f"{score}% skill overlap — early stage; prioritise foundation skills first."


# ---------------------------------------------------------------------------
# Stage 1: Resume text → skill list
# ---------------------------------------------------------------------------

def _stage_parse_resume(resume_text: str) -> dict:
    """Extract skills from raw resume text."""
    if not resume_text or not resume_text.strip():
        return {
            "stage": "parse_resume",
            "status": "skipped",
            "explanation": "No resume text provided; skipping skill extraction.",
            "skills": [],
        }
    skills = extract_skills(resume_text)
    return {
        "stage": "parse_resume",
        "status": "ok",
        "explanation": (
            f"Extracted {len(skills)} skill(s) from resume text using keyword "
            "matching against the SkillBridge vocabulary."
        ),
        "skills": skills,
    }


# ---------------------------------------------------------------------------
# Stage 2: Skill list → ranked job matches
# ---------------------------------------------------------------------------

def _stage_match_jobs(candidate_skills: list[str], jobs: list[dict]) -> dict:
    """Rank all jobs by skill overlap with the candidate."""
    if not candidate_skills:
        return {
            "stage": "match_jobs",
            "status": "skipped",
            "explanation": "No candidate skills available; skipping job matching.",
            "matches": [],
            "top_match": None,
        }
    if not jobs:
        return {
            "stage": "match_jobs",
            "status": "skipped",
            "explanation": "No job listings found in database.",
            "matches": [],
            "top_match": None,
        }

    matches = recommend_jobs(candidate_skills, jobs)
    top = matches[0] if matches else None
    return {
        "stage": "match_jobs",
        "status": "ok",
        "explanation": (
            f"Scored {len(matches)} job listing(s) using skill-overlap matching. "
            "Scores represent the percentage of a job's required skills that "
            "the candidate already has — not a hiring decision."
        ),
        "matches": matches,
        "top_match": top,
    }


# ---------------------------------------------------------------------------
# Stage 3: Gap analysis for one job
# ---------------------------------------------------------------------------

def _stage_gap_analysis(
    candidate_skills: list[str],
    job: dict,
) -> dict:
    """Run skill-gap analysis between candidate and a specific job."""
    if not job:
        return {
            "stage": "gap_analysis",
            "status": "skipped",
            "explanation": "No target job selected; skipping gap analysis.",
            "gap": None,
        }

    # The job dict may come from recommend_jobs (which omits the raw "skills"
    # string but provides "matched_skills" and "missing_skills"), or directly
    # from the DB (which has a "skills" comma-string).  Reconstruct required
    # from whichever source is available.
    if job.get("skills"):
        required = _split_skills(job["skills"])
    else:
        required = list(job.get("matched_skills", [])) + list(job.get("missing_skills", []))
    gap = analyze_skill_gap(candidate_skills, required)
    return {
        "stage": "gap_analysis",
        "status": "ok",
        "explanation": (
            f"Compared candidate skills against '{job.get('title', 'Unknown')}' "
            f"at {job.get('company', '')}. "
            f"Coverage: {gap['coverage']}%. "
            f"Missing: {len(gap['missing'])} skill(s)."
        ),
        "gap": gap,
        "job_title": job.get("title", ""),
        "job_company": job.get("company", ""),
    }


# ---------------------------------------------------------------------------
# Stage 4: Learning roadmap for missing skills
# ---------------------------------------------------------------------------

def _stage_roadmap(missing_skills: list[str]) -> dict:
    """Generate a structured, prioritised learning roadmap."""
    roadmap = generate_roadmap(missing_skills)
    if not missing_skills:
        return {
            "stage": "roadmap",
            "status": "skipped",
            "explanation": "No missing skills — no roadmap needed.",
            "roadmap": roadmap,
        }
    return {
        "stage": "roadmap",
        "status": "ok",
        "explanation": (
            f"Generated a {roadmap['total_skills']}-step learning roadmap "
            f"(estimated {roadmap['total_est_days']} days). "
            "Steps are ordered by market demand priority then learning stage."
        ),
        "roadmap": roadmap,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(
    request: dict,
    jobs: list[dict],
) -> dict:
    """
    Run the full career-assistance pipeline.

    Parameters
    ----------
    request : dict with optional keys:
        resume_text      – raw text extracted from a resume file
        candidate_skills – list or comma-string of known skills
                           (used when no resume_text is supplied)
        target_job_id    – int job id to run gap analysis against
                           (defaults to the top-matched job)
    jobs    : list of job dicts from the database

    Returns
    -------
    dict with keys:
        candidate_skills  – final resolved skill list
        stages            – ordered list of stage result dicts
        summary           – human-readable pipeline summary
        pipeline_version  – "1.0"
    """
    stages: list[dict] = []

    # ── Stage 1: resolve candidate skills ─────────────────────────────────
    resume_text = request.get("resume_text", "")
    if resume_text:
        stage1 = _stage_parse_resume(resume_text)
        candidate_skills = stage1["skills"]
    else:
        candidate_skills = _split_skills(request.get("candidate_skills", []))
        stage1 = {
            "stage": "parse_resume",
            "status": "skipped",
            "explanation": "Skills provided directly (no resume text supplied).",
            "skills": candidate_skills,
        }
    stages.append(stage1)

    # ── Stage 2: job matching ──────────────────────────────────────────────
    stage2 = _stage_match_jobs(candidate_skills, jobs)
    stages.append(stage2)

    # ── Stage 3: gap analysis for target job ──────────────────────────────
    target_id = request.get("target_job_id")
    if target_id and stage2["matches"]:
        target_job = next(
            (m for m in stage2["matches"] if m["id"] == int(target_id)),
            stage2["top_match"],
        )
    else:
        target_job = stage2.get("top_match")

    stage3 = _stage_gap_analysis(candidate_skills, target_job)
    stages.append(stage3)

    # ── Stage 4: roadmap ───────────────────────────────────────────────────
    missing = stage3["gap"]["missing"] if stage3.get("gap") else []
    stage4 = _stage_roadmap(missing)
    stages.append(stage4)

    # ── Summary ────────────────────────────────────────────────────────────
    completed = [s["stage"] for s in stages if s["status"] == "ok"]
    top = stage2.get("top_match")
    if top:
        top_line = (
            f"Top match: '{top['title']}' at {top['company']} "
            f"({_explain_match_score(top['score'])})"
        )
    else:
        top_line = "No job matches found — try adding more skills."

    summary = (
        f"Pipeline ran {len(completed)} active stage(s): {', '.join(completed)}. "
        f"{top_line}."
    )

    return {
        "candidate_skills": candidate_skills,
        "stages": stages,
        "summary": summary,
        "pipeline_version": "1.0",
    }


def run_skill_pipeline(
    current_skills: list[str],
    required_skills: list[str],
) -> dict:
    """
    Lightweight pipeline: gap analysis + roadmap only (no resume, no job DB).
    Used by the /api/roadmap endpoint.
    """
    gap = analyze_skill_gap(current_skills, required_skills)
    roadmap_stage = _stage_roadmap(gap["missing"])
    return {
        "matched": gap["matched"],
        "missing": gap["missing"],
        "coverage": gap["coverage"],
        "priority_order": gap["priority_order"],
        "summary": gap["summary"],
        "roadmap": roadmap_stage["roadmap"],
        "explanation": roadmap_stage["explanation"],
    }
