"""
tests/test_phase1.py — Phase 1 verification tests
Run: python tests/test_phase1.py
"""
import sys
import json
import sqlite3
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
errors = []

def check(cond, label):
    if cond:
        print(f"  {PASS}  {label}")
    else:
        print(f"  {FAIL}  {label}")
        errors.append(label)

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 1: Database schema migration")
print("=" * 60)

import app as application
application.init_db()

db = sqlite3.connect(str(ROOT / "database.db"))
db.row_factory = sqlite3.Row

tables = [r[0] for r in db.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]
print(f"  Tables found: {tables}")

check("jobs" in tables, "jobs table exists")
check("applications" in tables, "applications table exists")
check("candidates" in tables, "candidates table added")
check("candidate_skills" in tables, "candidate_skills table added")
check("roadmaps" in tables, "roadmaps table added")

cols = [r[1] for r in db.execute("PRAGMA table_info(applications)").fetchall()]
print(f"  applications columns: {cols}")
check("notes" in cols, "applications.notes column added")
check("updated_at" in cols, "applications.updated_at column added")
check("status" in cols, "applications.status preserved")
check("created_at" in cols, "applications.created_at preserved")

job_count = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
print(f"  Jobs in DB: {job_count}")
check(job_count == 5, "5 sample jobs preserved")

# Re-running init_db must be idempotent (no error, no duplicate seeds)
application.init_db()
job_count2 = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
check(job_count2 == 5, "init_db is idempotent (no duplicate seeds)")

db.close()

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 2: Skill vocabulary — resume_parser")
print("=" * 60)

from utils.resume_parser import KNOWN_SKILLS, SYNONYMS, extract_skills

print(f"  Total skills in vocabulary: {len(KNOWN_SKILLS)}")
check(len(KNOWN_SKILLS) >= 80, f"vocabulary has >= 80 skills (got {len(KNOWN_SKILLS)})")

# Basic extraction
text1 = "Experienced with Python, SQL, Flask and Git. Also know Docker and AWS."
found1 = extract_skills(text1)
print(f"  Basic extraction: {found1}")
for sk in ["python", "sql", "flask", "git", "docker", "aws"]:
    check(sk in found1, f"'{sk}' detected in basic text")

# Synonym expansion
text2 = "Proficient in JS, ML and NLP techniques"
found2 = extract_skills(text2)
print(f"  Synonym expansion: {found2}")
check("javascript" in found2, "JS -> javascript synonym")
check("machine learning" in found2, "ML -> machine learning synonym")
check("natural language processing" in found2, "NLP -> natural language processing synonym")

# Multi-word before single-word
text3 = "machine learning and deep learning experience with embedded c programming"
found3 = extract_skills(text3)
print(f"  Multi-word detection: {found3}")
check("machine learning" in found3, "'machine learning' detected as phrase")
check("deep learning" in found3, "'deep learning' detected as phrase")
check("embedded c" in found3, "'embedded c' detected as phrase")

# Edge cases
check(extract_skills("") == [], "empty string returns []")
check(extract_skills("   ") == [], "whitespace-only returns []")

# Deduplication — same skill twice in text
text4 = "Python is great. I use python daily."
found4 = extract_skills(text4)
check(found4.count("python") == 1, "skill deduplication works")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 3: Roadmap agent")
print("=" * 60)

from agents.roadmap_agent import generate_roadmap

# Normal case with known + unknown skills
rm = generate_roadmap(["python", "docker", "machine learning", "unknown-skill-xyz"])
print(f"  total_skills: {rm['total_skills']}, total_est_days: {rm['total_est_days']}")
print(f"  Stages: { {k: len(v) for k, v in rm['stages'].items()} }")

check(rm["total_skills"] == 4, "total_skills == 4")
check(rm["total_est_days"] > 0, "total_est_days > 0")
check(len(rm["ordered_steps"]) == 4, "ordered_steps has 4 entries")

priorities = [s["priority"] for s in rm["ordered_steps"]]
check(priorities == sorted(priorities), "steps sorted by priority asc")

step0 = rm["ordered_steps"][0]
for field in ["skill", "stage", "priority", "resource_type", "resource_hint", "exercise", "est_days"]:
    check(field in step0, f"step has '{field}' field")

check(
    any(s["skill"] == "unknown-skill-xyz" for s in rm["ordered_steps"]),
    "unknown skill handled with generic fallback"
)

# Empty input
rm_empty = generate_roadmap([])
check(rm_empty["total_skills"] == 0, "empty input -> total_skills == 0")
check(rm_empty["ordered_steps"] == [], "empty input -> ordered_steps == []")

# Duplicate handling
rm_dedup = generate_roadmap(["python", "Python", "PYTHON"])
check(rm_dedup["total_skills"] == 1, "duplicates deduplicated (case-insensitive)")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 4: Skill analyzer (upgraded)")
print("=" * 60)

from agents.skill_analyzer import analyze_skill_gap

# Partial match
result = analyze_skill_gap(
    ["python", "sql", "git"],
    ["python", "sql", "flask", "git", "docker"]
)
print(f"  coverage: {result['coverage']}%")
print(f"  matched: {result['matched']}")
print(f"  missing: {result['missing']}")
print(f"  priority_order: {result['priority_order']}")
print(f"  summary: {result['summary']}")

check(result["coverage"] == 60, "coverage == 60%")
check(sorted(result["matched"]) == ["git", "python", "sql"], "matched skills correct")
check(sorted(result["missing"]) == ["docker", "flask"], "missing skills correct")
check(isinstance(result["roadmap"], dict), "roadmap is dict")
check("ordered_steps" in result["roadmap"], "roadmap has ordered_steps")
check(len(result["roadmap"]["ordered_steps"]) == 2, "roadmap has 2 steps")
check(len(result["priority_order"]) == 2, "priority_order has 2 entries")
check(result["summary"] != "", "summary is non-empty")

# Full match
full = analyze_skill_gap(["python", "sql"], ["python", "sql"])
check(full["coverage"] == 100, "full match -> coverage == 100")
check(full["missing"] == [], "full match -> no missing skills")
check("all the required skills" in full["summary"], "full match summary correct")

# No required skills
empty_req = analyze_skill_gap(["python"], [])
check(empty_req["coverage"] == 0, "empty required -> coverage == 0")
check(empty_req["summary"] == "No required skills specified.", "empty required summary")

# Non-list inputs handled gracefully
try:
    result2 = analyze_skill_gap([], [])
    check(isinstance(result2, dict), "empty lists handled gracefully")
except Exception as e:
    check(False, f"empty list raised exception: {e}")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"FAILED — {len(errors)} assertion(s) failed:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"ALL {sum(1 for _ in range(1)) + 0} TESTS PASSED")
    # Count pass lines
    print("ALL TESTS PASSED")
print("=" * 60)
