"""
tests/test_phase3.py -- Phase 3 frontend integration tests
Run: python tests/test_phase3.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

errors = []
def check(cond, label):
    status = "PASS" if cond else "FAIL"
    print(f"  {status}  {label}")
    if not cond:
        errors.append(label)

import app as application
application.init_db()
flask_app = application.app
flask_app.config["TESTING"] = True
client = flask_app.test_client()

# ── helpers ──────────────────────────────────────────────────────────────────
def get(path): return client.get(path)
def post_json(path, data): return client.post(path, json=data, content_type="application/json")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 1: All existing routes still return 200")
print("=" * 60)

routes_200 = ["/", "/jobs", "/dashboard", "/tracker", "/health"]
for r in routes_200:
    rv = get(r)
    check(rv.status_code == 200, f"GET {r} returns 200")

# API routes
rv = post_json("/api/match", {"skills": "python,sql"})
check(rv.status_code == 200, "POST /api/match returns 200")

rv = post_json("/api/skill-gap", {"current_skills": "python", "required_skills": "python,sql,flask"})
check(rv.status_code == 200, "POST /api/skill-gap returns 200")

rv = post_json("/assistant", {"message": "resume help", "language": "English"})
check(rv.status_code == 200, "POST /assistant returns 200")

rv = post_json("/api/roadmap", {"current_skills": "python", "required_skills": "python,sql,flask,docker"})
check(rv.status_code == 200, "POST /api/roadmap returns 200")

rv = post_json("/api/pipeline", {"candidate_skills": "python,sql,git"})
check(rv.status_code == 200, "POST /api/pipeline returns 200")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 2: Page content — index.html")
print("=" * 60)

rv = get("/")
html = rv.data
check(b"Turn your skills into" in html, "index hero heading present")
check(b"resume-upload" in html,          "index resume upload section present")
check(b"uploadZone" in html,             "index upload zone element present")
check(b"uploadResumeBtn" in html,        "index upload button present")
check(b"resumeFile" in html,             "index file input present")
check(b"Career assistant" in html or b"CAREER ASSISTANT" in html, "index assistant section present")
check(b"askAssistant" in html,           "index assistant button present")
check(b"Kannada" in html,               "index Kannada language option present")
check(b"lang-btn" in html,              "index language switcher buttons present")
check(b"data-lang" in html,             "index language buttons have data-lang attr")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 3: Page content — jobs.html")
print("=" * 60)

rv = get("/jobs")
html = rv.data
check(b"Smart Job Matcher" in html or b"SMART JOB MATCHER" in html, "jobs matcher section present")
check(b"skillsInput" in html,         "jobs skills input present")
check(b"matchButton" in html,         "jobs match button present")
check(b"SKILL GAP ANALYSIS" in html,  "jobs skill gap analysis section present")
check(b"gapCurrent" in html,          "jobs gap current input present")
check(b"gapRequired" in html,         "jobs gap required input present")
check(b"gapButton" in html,           "jobs gap button present")
check(b"jobFilter" in html,           "jobs filter input present")
check(b"job-card-static" in html,     "jobs static cards have correct class")
check(b"chip-skill" in html,          "jobs skill chips present")
check(b"Analyse gap" in html,         "jobs analyse gap link present")
check(b"Python Developer" in html,    "jobs sample listing present")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 4: Page content — dashboard.html (no skills)")
print("=" * 60)

rv = get("/dashboard")
html = rv.data
check(b"CANDIDATE DASHBOARD" in html,  "dashboard heading present")
check(b"nameInput" in html or b"skillsInput" in html, "dashboard skill entry form present")
check(b"Load dashboard" in html,       "dashboard load button present")
check(b"resume-upload" in html,        "dashboard link to resume upload present")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 5: Page content — dashboard.html (with skills)")
print("=" * 60)

rv = get("/dashboard?skills=python,sql,git&name=Priya")
html = rv.data
check(b"Priya" in html,                "dashboard shows candidate name")
check(b"python" in html,               "dashboard shows extracted skill")
check(b"chip-skill" in html,           "dashboard skill chips present")
check(b"Top job matches" in html or b"TOP MATCHES" in html or b"top job" in html.lower(),
      "dashboard top matches section present")
check(b"dash-grid" in html,            "dashboard uses grid layout")
check(b"dash-card" in html,            "dashboard uses dash-card components")
check(b"pipeline" in html.lower(),     "dashboard shows pipeline explainer")
check(b"score-ring" in html,           "dashboard shows score rings")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 6: Page content — tracker.html")
print("=" * 60)

# Create a test application first
with application.get_db() as conn:
    conn.execute("INSERT INTO applications(candidate_name, job_id, status) VALUES(?,?,?)",
                 ("Phase3Test", 1, "Saved"))
    test_app_id = conn.execute(
        "SELECT id FROM applications WHERE candidate_name='Phase3Test'"
    ).fetchone()[0]

rv = get("/tracker")
html = rv.data
check(b"Application tracker" in html,     "tracker heading present")
check(b"kanban" in html,                  "tracker kanban layout present")
check(b"kanban-col" in html,              "tracker kanban columns present")
check(b"Saved" in html,                   "tracker Saved column present")
check(b"Applied" in html,                 "tracker Applied column present")
check(b"Interviewing" in html,            "tracker Interviewing column present")
check(b"Offered" in html,                 "tracker Offered column present")
check(b"Rejected" in html,                "tracker Rejected column present")
check(b"status-btn" in html,              "tracker status buttons present")
check(b"knotes" in html,                  "tracker notes textarea present")
check(b"Phase3Test" in html,              "tracker shows test application")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 7: Navigation — lang buttons in all pages")
print("=" * 60)

for path in ["/", "/jobs", "/dashboard", "/tracker"]:
    rv = get(path)
    html = rv.data
    check(b"lang-btn" in html, f"{path} has language buttons")
    check(b"data-lang" in html, f"{path} has data-lang attribute")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 8: JavaScript app.js key functions present")
print("=" * 60)

import urllib.request
# Read the JS file directly (no HTTP needed)
js_path = ROOT / "static" / "js" / "app.js"
js = js_path.read_text(encoding="utf-8")
check("escapeHTML" in js,           "app.js has escapeHTML function")
check("postJSON" in js,             "app.js has postJSON function")
check("patchJSON" in js,            "app.js has patchJSON function")
check("I18N" in js,                 "app.js has I18N translations object")
check("applyLanguage" in js,        "app.js has applyLanguage function")
check("kn" in js,                   "app.js has Kannada translations")
check("renderMatchItem" in js,      "app.js has renderMatchItem function")
check("initResumeUpload" in js,     "app.js has resume upload IIFE")
check("uploadZone" in js,           "app.js references uploadZone")
check("dragover" in js,             "app.js handles drag-over events")
check("updateStatus" in js,         "app.js has updateStatus function")
check("status-btn" in js,           "app.js wires status-btn elements")
check("spinner" in js,              "app.js uses spinner loading indicator")
check("showAlert" in js,            "app.js has showAlert function")
check("setLoading" in js,           "app.js has setLoading function")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 9: CSS design tokens and new classes present")
print("=" * 60)

css_path = ROOT / "static" / "css" / "style.css"
css = css_path.read_text(encoding="utf-8")
check("--green" in css,          "CSS has --green token")
check("--amber" in css,          "CSS has --amber token")
check("--red" in css,            "CSS has --red token")
check("kanban" in css,           "CSS has kanban styles")
check("upload-zone" in css,      "CSS has upload-zone styles")
check("score-ring" in css,       "CSS has score-ring styles")
check("dash-grid" in css,        "CSS has dash-grid layout")
check("lang-btn" in css,         "CSS has lang-btn styles")
check("spinner" in css,          "CSS has spinner animation")
check("chip-match" in css,       "CSS has chip-match style")
check("chip-miss" in css,        "CSS has chip-miss style")
check("alert-success" in css,    "CSS has alert-success style")
check("alert-error" in css,      "CSS has alert-error style")
check("stage-foundation" in css, "CSS has stage-foundation badge")
check("stage-intermediate" in css,"CSS has stage-intermediate badge")
check("stage-advanced" in css,   "CSS has stage-advanced badge")
check("coverage-bar" in css,     "CSS has coverage-bar progress")
check("roadmap-step" in css,     "CSS has roadmap-step style")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 10: Application status update (PATCH) still works")
print("=" * 60)

# Update status
rv = client.post(
    f"/application/{test_app_id}/status",
    json={"status": "Applied", "notes": "Phase3 test note"},
    content_type="application/json"
)
check(rv.status_code == 200, "PATCH /application/<id>/status returns 200")
resp = rv.get_json()
check(resp.get("ok") is True, "status update response ok=True")

# Verify in tracker
rv = get("/tracker")
check(b"Phase3Test" in rv.data, "updated application still visible in tracker")

# Clean up
with application.get_db() as conn:
    conn.execute("DELETE FROM applications WHERE candidate_name='Phase3Test'")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"FAILED -- {len(errors)} assertion(s) failed:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
print("=" * 60)
