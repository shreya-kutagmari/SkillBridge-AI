"""
tests/test_phase2.py -- Phase 2 verification tests
Run: python tests/test_phase2.py
"""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS_S = "PASS"
FAIL_S = "FAIL"
errors = []

def check(cond, label):
    if cond:
        print(f"  {PASS_S}  {label}")
    else:
        print(f"  {FAIL_S}  {label}")
        errors.append(label)

# Shared sample jobs (mirrors DB seed data)
SAMPLE_JOBS = [
    {"id": 1, "title": "Python Developer Intern", "company": "Bengaluru Tech Labs",
     "location": "Bengaluru", "job_type": "Internship",
     "skills": "python,sql,flask,git", "description": "Build Python web services."},
    {"id": 2, "title": "Junior Software Engineer", "company": "Civic Digital",
     "location": "Bengaluru", "job_type": "Full-time",
     "skills": "python,html,css,javascript,sql,git", "description": "Build digital services."},
    {"id": 3, "title": "Data Analyst Trainee", "company": "InsightWorks",
     "location": "Bengaluru", "job_type": "Apprenticeship",
     "skills": "python,sql,excel,pandas,communication", "description": "Clean datasets."},
    {"id": 4, "title": "IoT Support Engineer", "company": "SmartCity Systems",
     "location": "Bengaluru", "job_type": "Full-time",
     "skills": "iot,arduino,embedded c,networking,communication", "description": "Support IoT."},
    {"id": 5, "title": "AI/ML Trainee", "company": "FutureLearn AI",
     "location": "Hybrid - Bengaluru", "job_type": "Trainee",
     "skills": "python,pandas,numpy,machine learning,statistics,git", "description": "ML workflows."},
]

# ===========================================================================
print("\n" + "=" * 60)
print("TEST 1: Orchestrator — run_pipeline")
print("=" * 60)

from agents.orchestrator import run_pipeline, run_skill_pipeline

# 1a: Full pipeline with candidate skills
result = run_pipeline({"candidate_skills": ["python", "sql", "git"]}, SAMPLE_JOBS)
print(f"  candidate_skills: {result['candidate_skills']}")
print(f"  pipeline_version: {result['pipeline_version']}")
print(f"  summary: {result['summary']}")
print(f"  stages: {[s['stage'] for s in result['stages']]}")

check(result["pipeline_version"] == "1.0", "pipeline_version == '1.0'")
check(len(result["stages"]) == 4, "pipeline has 4 stages")
check(result["candidate_skills"] == ["python", "sql", "git"], "candidate_skills passed through")

stages_by_name = {s["stage"]: s for s in result["stages"]}
check("parse_resume"  in stages_by_name, "parse_resume stage present")
check("match_jobs"    in stages_by_name, "match_jobs stage present")
check("gap_analysis"  in stages_by_name, "gap_analysis stage present")
check("roadmap"       in stages_by_name, "roadmap stage present")

check(stages_by_name["parse_resume"]["status"] == "skipped", "parse_resume skipped when no resume_text")
check(stages_by_name["match_jobs"]["status"]   == "ok",      "match_jobs ran successfully")
check(stages_by_name["gap_analysis"]["status"] == "ok",      "gap_analysis ran successfully")
check(stages_by_name["roadmap"]["status"]      == "ok",      "roadmap stage ran successfully")

matches = stages_by_name["match_jobs"]["matches"]
check(len(matches) == 5, "all 5 jobs scored")
# Matches sorted high-to-low
scores = [m["score"] for m in matches]
check(scores == sorted(scores, reverse=True), "matches sorted high-to-low score")

top_match = stages_by_name["match_jobs"]["top_match"]
check(top_match is not None, "top_match is not None")
check("title" in top_match and "score" in top_match, "top_match has title and score")

gap = stages_by_name["gap_analysis"]["gap"]
check(isinstance(gap["coverage"], int), "gap coverage is int")
check(isinstance(gap["missing"], list), "gap missing is list")
check(isinstance(gap["roadmap"], dict), "gap roadmap is dict")

# 1b: Pipeline with resume text
result2 = run_pipeline(
    {"resume_text": "Experienced Python developer. Skills: python, flask, sql, git, docker."},
    SAMPLE_JOBS,
)
check(result2["stages"][0]["status"] == "ok", "parse_resume ok when resume_text provided")
check("python" in result2["candidate_skills"], "python extracted from resume_text")
check("docker" in result2["candidate_skills"], "docker extracted from resume_text")

# 1c: Pipeline with target_job_id
result3 = run_pipeline(
    {"candidate_skills": ["python", "sql"], "target_job_id": 3},
    SAMPLE_JOBS,
)
gap3 = result3["stages"][2]
check(gap3["status"] == "ok", "gap_analysis ok with target_job_id")
check(gap3.get("job_title") == "Data Analyst Trainee", "correct job targeted by id")

# 1d: Empty skills
result_empty = run_pipeline({"candidate_skills": []}, SAMPLE_JOBS)
check(result_empty["stages"][1]["status"] == "skipped", "match_jobs skipped for empty skills")

# 1e: No jobs
result_nojobs = run_pipeline({"candidate_skills": ["python"]}, [])
check(result_nojobs["stages"][1]["status"] == "skipped", "match_jobs skipped for no jobs")

# 1f: run_skill_pipeline
sp = run_skill_pipeline(["python", "sql"], ["python", "sql", "flask", "docker"])
check(sp["coverage"] == 50, "run_skill_pipeline coverage == 50%")
check(sorted(sp["missing"]) == ["docker", "flask"], "run_skill_pipeline missing correct")
check(isinstance(sp["roadmap"], dict), "run_skill_pipeline roadmap is dict")
check("explanation" in sp, "run_skill_pipeline has explanation")

# ===========================================================================
print("\n" + "=" * 60)
print("TEST 2: Career assistant — English topic routing")
print("=" * 60)

from agents.career_assistant import career_reply

# Empty input
r = career_reply("", "English")
check("Tell me" in r, "empty English message -> prompt to provide info")

# Greeting
r = career_reply("Hello, I need help", "English")
check("SkillBridge AI" in r, "greeting -> welcome message")
check("Resume" in r or "resume" in r, "greeting includes resume topic")

# Resume topic
r = career_reply("How do I improve my resume?", "English")
check("resume" in r.lower() or "skills" in r.lower(), "resume topic -> resume guidance")
check("action verbs" in r.lower() or "tailor" in r.lower() or "summary" in r.lower(),
      "resume guidance has specific advice")

# Interview topic
r = career_reply("How should I prepare for a technical interview?", "English")
check("interview" in r.lower() or "star" in r.lower() or "introduction" in r.lower(),
      "interview topic -> interview guidance")

# Skills/roadmap topic
r = career_reply("What skills should I learn for a data science role?", "English")
check("skill" in r.lower() or "learn" in r.lower() or "roadmap" in r.lower(),
      "skills topic -> skill guidance")

# Job search topic
r = career_reply("Where can I find jobs in Bengaluru?", "English")
check("linkedin" in r.lower() or "naukri" in r.lower() or "internshala" in r.lower(),
      "job search -> platform recommendations")

# Career planning
r = career_reply("How do I plan my career for the next 5 years?", "English")
check("career" in r.lower() or "plan" in r.lower() or "sprint" in r.lower(),
      "career planning -> career guidance")

# Salary
r = career_reply("How do I negotiate my salary?", "English")
check("salary" in r.lower() or "lpa" in r.lower() or "ctc" in r.lower(),
      "salary topic -> salary guidance")

# Portfolio
r = career_reply("How do I build a portfolio project?", "English")
check("portfolio" in r.lower() or "github" in r.lower() or "project" in r.lower(),
      "portfolio topic -> portfolio guidance")

# LinkedIn
r = career_reply("How should I set up my LinkedIn profile?", "English")
check("linkedin" in r.lower() or "headline" in r.lower() or "recruiter" in r.lower(),
      "linkedin topic -> LinkedIn guidance")

# Technical skills
r = career_reply("I want to learn Python and Docker", "English")
check("python" in r.lower() or "domain" in r.lower() or "foundation" in r.lower(),
      "technical topic -> technical guidance")

# Fallback
r = career_reply("something completely unrelated xyz 12345", "English")
check("resume" in r.lower() or "interview" in r.lower() or "skill" in r.lower(),
      "unknown topic -> fallback with suggestions")

# ===========================================================================
print("\n" + "=" * 60)
print("TEST 3: Career assistant — Kannada topic routing")
print("=" * 60)

# Empty Kannada
r_kn = career_reply("", "Kannada")
check(len(r_kn) > 0 and "English" not in r_kn, "empty Kannada -> Kannada prompt")

# Greeting (Kannada)
r_kn = career_reply("Hello help me", "Kannada")
check("SkillBridge AI" in r_kn, "Kannada greeting -> Kannada welcome")

# Resume (Kannada)
r_kn = career_reply("resume tips please", "Kannada")
check(len(r_kn) > 20, "Kannada resume topic -> non-empty Kannada response")

# Interview (Kannada)
r_kn = career_reply("interview preparation help", "Kannada")
check("STAR" in r_kn or "ಸಂದರ್ಶನ" in r_kn, "Kannada interview -> STAR or Kannada text")

# Skills (Kannada)
r_kn = career_reply("skills and roadmap guidance", "Kannada")
check("SkillBridge" in r_kn or "GitHub" in r_kn or "ಕೌಶಲ್ಯ" in r_kn,
      "Kannada skills topic -> relevant Kannada guidance")

# Career (Kannada)
r_kn = career_reply("career plan for future", "Kannada")
check("sprint" in r_kn.lower() or "ವೃತ್ತಿ" in r_kn or "plan" in r_kn.lower(),
      "Kannada career topic -> career guidance")

# Fallback (Kannada)
r_kn = career_reply("xyzunknown9999", "Kannada")
check(len(r_kn) > 20, "Kannada fallback -> non-empty Kannada fallback")

# ===========================================================================
print("\n" + "=" * 60)
print("TEST 4: Flask routes (/api/roadmap, /api/pipeline, /application/<id>/status, /dashboard)")
print("=" * 60)

import app as application
application.init_db()
flask_app = application.app
flask_app.config["TESTING"] = True
client = flask_app.test_client()

# 4a: POST /api/roadmap
rv = client.post(
    "/api/roadmap",
    json={"current_skills": "python,sql", "required_skills": "python,sql,flask,docker"},
    content_type="application/json",
)
check(rv.status_code == 200, "/api/roadmap returns 200")
data_rm = rv.get_json()
check(data_rm["coverage"] == 50, "/api/roadmap coverage == 50%")
check(sorted(data_rm["missing"]) == ["docker", "flask"], "/api/roadmap missing correct")
check(isinstance(data_rm["roadmap"], dict), "/api/roadmap roadmap is dict")

# 4a2: POST /api/roadmap with missing required_skills
rv_bad = client.post("/api/roadmap", json={"current_skills": "python"}, content_type="application/json")
check(rv_bad.status_code == 400, "/api/roadmap 400 when required_skills missing")
check("error" in rv_bad.get_json(), "/api/roadmap error message present")

# 4b: POST /api/pipeline
rv = client.post(
    "/api/pipeline",
    json={"candidate_skills": "python,sql,git"},
    content_type="application/json",
)
check(rv.status_code == 200, "/api/pipeline returns 200")
data_pipe = rv.get_json()
check("stages" in data_pipe, "/api/pipeline has stages")
check("candidate_skills" in data_pipe, "/api/pipeline has candidate_skills")
check(len(data_pipe["stages"]) == 4, "/api/pipeline has 4 stages")
check(data_pipe["pipeline_version"] == "1.0", "/api/pipeline version correct")

# 4c: PATCH /application/<id>/status
# First create an application to update
with application.get_db() as conn:
    conn.execute("INSERT INTO applications(candidate_name, job_id, status) VALUES(?,?,?)",
                 ("Test User Phase2", 1, "Saved"))
    app_id = conn.execute("SELECT id FROM applications WHERE candidate_name='Test User Phase2'").fetchone()[0]

rv = client.post(
    f"/application/{app_id}/status",
    json={"status": "Applied", "notes": "Applied on portal"},
    content_type="application/json",
)
check(rv.status_code == 200, "PATCH /application/<id>/status returns 200")
resp = rv.get_json()
check(resp.get("ok") is True, "status update ok==True")
check(resp.get("status") == "Applied", "status updated to Applied")

# Verify DB was updated
with application.get_db() as conn:
    row = conn.execute("SELECT status, notes FROM applications WHERE id=?", (app_id,)).fetchone()
check(row["status"] == "Applied", "DB status updated to Applied")
check(row["notes"] == "Applied on portal", "DB notes updated")

# 4c2: Invalid status
rv_bad2 = client.post(
    f"/application/{app_id}/status",
    json={"status": "NotAStatus"},
    content_type="application/json",
)
check(rv_bad2.status_code == 400, "invalid status returns 400")

# 4c3: Not-found application
rv_nf = client.post("/application/99999/status", json={"status": "Applied"}, content_type="application/json")
check(rv_nf.status_code == 404, "missing application returns 404")

# 4c4: No fields provided
rv_nf2 = client.post(f"/application/{app_id}/status", json={}, content_type="application/json")
check(rv_nf2.status_code == 400, "empty body returns 400")

# 4d: GET /dashboard (no skills)
rv = client.get("/dashboard")
check(rv.status_code == 200, "GET /dashboard returns 200 (no skills)")
check(b"CANDIDATE DASHBOARD" in rv.data, "/dashboard HTML contains expected heading")

# 4e: GET /dashboard (with skills)
rv = client.get("/dashboard?skills=python,sql,git&name=Ravi")
check(rv.status_code == 200, "GET /dashboard with skills returns 200")
check(b"Ravi" in rv.data, "/dashboard shows candidate name")
check(b"python" in rv.data, "/dashboard shows extracted skills")

# 4f: Existing routes still work
rv_home = client.get("/")
check(rv_home.status_code == 200, "GET / still returns 200 (preserved)")

rv_jobs = client.get("/jobs")
check(rv_jobs.status_code == 200, "GET /jobs still returns 200 (preserved)")

rv_tracker = client.get("/tracker")
check(rv_tracker.status_code == 200, "GET /tracker still returns 200 (preserved)")

rv_health = client.get("/health")
check(rv_health.status_code == 200, "/health still returns 200")
health_data = rv_health.get_json()
check(health_data["status"] == "ok", "/health status == ok")
check("orchestrator" in health_data.get("agents", []), "/health lists orchestrator agent")

rv_match = client.post("/api/match", json={"skills": "python,sql"}, content_type="application/json")
check(rv_match.status_code == 200, "POST /api/match still returns 200 (preserved)")

rv_gap = client.post(
    "/api/skill-gap",
    json={"current_skills": "python", "required_skills": "python,sql,flask"},
    content_type="application/json",
)
check(rv_gap.status_code == 200, "POST /api/skill-gap still returns 200 (preserved)")
gap_data = rv_gap.get_json()
check("roadmap" in gap_data, "/api/skill-gap still returns roadmap field")
check("summary" in gap_data, "/api/skill-gap returns new summary field")

rv_asst = client.post("/assistant", json={"message": "resume help", "language": "English"}, content_type="application/json")
check(rv_asst.status_code == 200, "POST /assistant still returns 200 (preserved)")
check("reply" in rv_asst.get_json(), "/assistant returns reply field")

# Clean up test application
with application.get_db() as conn:
    conn.execute("DELETE FROM applications WHERE candidate_name='Test User Phase2'")

# ===========================================================================
print("\n" + "=" * 60)
if errors:
    print(f"FAILED -- {len(errors)} assertion(s) failed:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
print("=" * 60)
