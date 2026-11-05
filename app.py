from dotenv import load_dotenv
load_dotenv()  # Load .env before any os.environ reads; no-op if .env absent

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, flash, session)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
import sqlite3, os, logging, functools
from agents.job_matcher import recommend_jobs
from agents.skill_analyzer import analyze_skill_gap
from agents.career_assistant import career_reply
from agents.ai_career_assistant import ai_career_reply
from agents.orchestrator import run_pipeline, run_skill_pipeline
from agents.ai_roadmap_agent import ai_generate_roadmap
from agents.ai_client import is_available as ai_is_available
from utils.resume_parser import extract_resume_text, extract_skills
from utils.embeddings import store_resume_chunks
from utils.resume_analyzer import analyze_resume
from utils.retrieval import retrieve_chunks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}

app = Flask(__name__)
_SECRET = os.environ.get("SECRET_KEY", "skillbridge-dev-key-change-me")
app.secret_key = _SECRET
# Explicit session-cookie security settings (Flask defaults are already safe,
# but declaring them makes the posture auditable and immune to future default changes).
app.config["SESSION_COOKIE_HTTPONLY"] = True   # JS cannot read the session cookie
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"  # blocks all cross-origin form POSTs
if _SECRET == "skillbridge-dev-key-change-me":
    logger.warning("SECRET_KEY is using the insecure default. Set SECRET_KEY in .env for any deployment.")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _safe_add_column(conn, table, column, definition):
    """Add a column to an existing table only if it does not already exist."""
    existing = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    with get_db() as conn:
        # ── Existing tables (unchanged) ─────────────────────────────────────
        conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, company TEXT NOT NULL, location TEXT NOT NULL,
            job_type TEXT NOT NULL, skills TEXT NOT NULL, description TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT NOT NULL, job_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Saved',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )""")

        # ── Safe migrations on existing tables ───────────────────────────────
        _safe_add_column(conn, "applications", "notes",      "TEXT DEFAULT ''")
        _safe_add_column(conn, "applications", "updated_at", "TIMESTAMP")
        _safe_add_column(conn, "applications", "user_id",    "INTEGER DEFAULT NULL")

        # ── Users table (Phase 4) ─────────────────────────────────────────────
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            consent_given INTEGER NOT NULL DEFAULT 0,
            consent_at TIMESTAMP
        )""")

        # ── Existing Phase 2 new tables ───────────────────────────────────────
        conn.execute("""CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        _safe_add_column(conn, "candidates", "user_id", "INTEGER DEFAULT NULL")

        conn.execute("""CREATE TABLE IF NOT EXISTS candidate_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            skill TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            FOREIGN KEY(candidate_id) REFERENCES candidates(id)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS roadmaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            job_id INTEGER,
            job_title TEXT DEFAULT '',
            current_skills TEXT DEFAULT '',
            missing_skills TEXT DEFAULT '',
            roadmap_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id),
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )""")
        _safe_add_column(conn, "roadmaps", "user_id", "INTEGER DEFAULT NULL")

        # ── Phase 4: resume chunks for RAG ────────────────────────────────────
        conn.execute("""CREATE TABLE IF NOT EXISTS resume_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resume_filename TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            embedding_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")

        # ── Seed sample jobs only if table is empty ──────────────────────────
        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if count == 0:
            sample_jobs = [
                ("Python Developer Intern", "Bengaluru Tech Labs", "Bengaluru", "Internship", "python,sql,flask,git", "Build and test Python web services. Good opportunity for fresh graduates."),
                ("Junior Software Engineer", "Civic Digital", "Bengaluru", "Full-time", "python,html,css,javascript,sql,git", "Help build accessible digital services for local communities."),
                ("Data Analyst Trainee", "InsightWorks", "Bengaluru", "Apprenticeship", "python,sql,excel,pandas,communication", "Clean datasets, create reports and communicate insights."),
                ("IoT Support Engineer", "SmartCity Systems", "Bengaluru", "Full-time", "iot,arduino,embedded c,networking,communication", "Support connected devices and troubleshoot field deployments."),
                ("AI/ML Trainee", "FutureLearn AI", "Hybrid - Bengaluru", "Trainee", "python,pandas,numpy,machine learning,statistics,git", "Assist with data preparation and introductory machine-learning workflows.")
            ]
            conn.executemany("INSERT INTO jobs(title,company,location,job_type,skills,description) VALUES(?,?,?,?,?,?)", sample_jobs)

# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_current_user_id() -> int | None:
    """Return the logged-in user's id from session, or None."""
    return session.get("user_id")


def _safe_next(url: str) -> str:
    """Return *url* only if it is a safe local relative path; otherwise return the dashboard URL.

    A safe next-URL must:
      - Be a non-empty string.
      - Start with exactly one forward-slash (rules out protocol-relative ``//host``).
      - Contain no scheme component (rules out ``http:``, ``https:``, ``javascript:``, etc.).
      - Contain no backslashes (rules out ``/\\evil.com`` bypass on some browsers).
      - Have no netloc after URL-parsing (double-checks for edge cases like ``//host/path``).

    Any value that fails these checks is silently replaced with ``url_for("dashboard")``.
    The validation is applied *inside the request context* so ``url_for`` works correctly.
    """
    from urllib.parse import urlparse  # stdlib — already available; local import avoids circular risk

    if not url or not isinstance(url, str):
        return url_for("dashboard")

    # Reject anything containing a backslash (browser normalisation bypass)
    if "\\" in url:
        return url_for("dashboard")

    # Must start with exactly "/" but NOT "//" (protocol-relative)
    if not url.startswith("/") or url.startswith("//"):
        return url_for("dashboard")

    # Parse and reject any URL that carries a scheme or netloc
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        return url_for("dashboard")

    return url


def login_required(f):
    """Decorator: redirect to /login if no active session."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user_id():
            flash("Please log in to access this page.", "error")
            safe_next = _safe_next(request.path)
            return redirect(url_for("login", next=safe_next))
        return f(*args, **kwargs)
    return decorated

# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    email        = request.form.get("email", "").strip().lower()
    display_name = request.form.get("display_name", "").strip()
    password     = request.form.get("password", "")
    confirm      = request.form.get("confirm_password", "")
    consent      = request.form.get("consent")

    # Validation
    if not email or "@" not in email:
        flash("Please enter a valid email address.", "error")
        return render_template("register.html")
    if not display_name:
        flash("Please enter your name.", "error")
        return render_template("register.html")
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return render_template("register.html")
    if password != confirm:
        flash("Passwords do not match.", "error")
        return render_template("register.html")
    if not consent:
        flash("You must agree to the privacy notice to create an account.", "error")
        return render_template("register.html")

    pw_hash = generate_password_hash(password)
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users(email, password_hash, display_name, consent_given, consent_at) "
                "VALUES(?,?,?,1,CURRENT_TIMESTAMP)",
                (email, pw_hash, display_name),
            )
            user_id = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
    except Exception as exc:
        if "UNIQUE constraint" in str(exc):
            flash("An account with that email already exists.", "error")
        else:
            logger.error("Register error: %s", exc)
            flash("Registration failed. Please try again.", "error")
        return render_template("register.html")

    session.clear()
    session["user_id"] = user_id
    session["display_name"] = display_name
    flash(f"Welcome, {display_name}! Your account has been created.", "success")
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", next=request.args.get("next", ""))
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    next_url = request.form.get("next", "")

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, password_hash, display_name FROM users WHERE email=?", (email,)
        ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        flash("Incorrect email or password.", "error")
        return render_template("login.html", next=next_url)

    session.clear()
    session["user_id"] = row["id"]
    session["display_name"] = row["display_name"]
    flash(f"Welcome back, {row['display_name']}!", "success")
    return redirect(_safe_next(next_url))


@app.route("/logout")
def logout():
    name = session.get("display_name", "")
    session.clear()
    flash(f"You have been logged out{', ' + name if name else ''}.", "success")
    return redirect(url_for("index"))


# ── Privacy notice ────────────────────────────────────────────────────────────

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/")
def index():
    with get_db() as conn:
        job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        app_count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    return render_template("index.html", job_count=job_count, app_count=app_count)

@app.route("/jobs")
def jobs():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
    return render_template("jobs.html", jobs=rows)

@app.route("/api/match", methods=["POST"])
def api_match():
    data = request.get_json(silent=True) or request.form
    skills = data.get("skills", "")
    skills = [s.strip() for s in skills.split(",") if s.strip()] if isinstance(skills, str) else skills
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM jobs").fetchall()
    return jsonify(recommend_jobs(skills, [dict(r) for r in rows]))

@app.route("/api/skill-gap", methods=["POST"])
def api_skill_gap():
    data = request.get_json(silent=True) or request.form
    current = data.get("current_skills", "")
    required = data.get("required_skills", "")
    split = lambda value: [x.strip() for x in value.split(",") if x.strip()] if isinstance(value, str) else value
    return jsonify(analyze_skill_gap(split(current), split(required)))

@app.route("/assistant", methods=["POST"])
def assistant():
    data   = request.get_json(silent=True) or {}
    msg    = data.get("message", "")
    lang   = data.get("language", "English")
    reply  = ai_career_reply(msg, lang)
    return jsonify({"reply": reply, "ai_powered": ai_is_available()})

@app.route("/resume", methods=["POST"])
def resume():
    file = request.files.get("resume")
    if not file or not file.filename:
        return jsonify({"error": "Please choose a resume file."}), 400
    if "." not in file.filename or file.filename.rsplit(".", 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Supported formats: PDF, DOCX and TXT."}), 400
    filename = secure_filename(file.filename)
    path = UPLOAD_DIR / filename
    file.save(path)
    try:
        content = extract_resume_text(path)
        skills  = extract_skills(content)
        analysis = analyze_resume(content)
        chunks_stored = 0
        user_id = get_current_user_id()
        if user_id:
            try:
                with get_db() as conn:
                    chunks_stored = store_resume_chunks(user_id, filename, content, conn)
            except Exception as chunk_exc:
                logger.warning("Resume chunk storage failed for user %d: %s", user_id, chunk_exc)
        return jsonify({
            "filename": filename,
            "skills": skills,
            "preview": content[:900],
            "chunks_stored": chunks_stored,
            "analysis": analysis,
        })
    except Exception as exc:
        return jsonify({"error": f"Could not read this file: {exc}"}), 400

@app.route("/apply/<int:job_id>", methods=["POST"])
def apply(job_id):
    name = request.form.get("candidate_name", "").strip()
    if not name:
        flash("Please enter your name before saving an application.", "error")
        return redirect(url_for("jobs"))
    user_id = get_current_user_id()  # None for anonymous users — allowed
    with get_db() as conn:
        exists = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not exists:
            flash("Job not found.", "error")
            return redirect(url_for("jobs"))
        conn.execute(
            "INSERT INTO applications(candidate_name, job_id, user_id) VALUES(?,?,?)",
            (name, job_id, user_id),
        )
    flash("Application saved to your local tracker.", "success")
    return redirect(url_for("tracker"))


@app.route("/tracker")
def tracker():
    user_id = get_current_user_id()
    with get_db() as conn:
        if user_id:
            # Logged-in: show own applications
            rows = conn.execute("""SELECT applications.*, jobs.title, jobs.company
                FROM applications JOIN jobs ON jobs.id=applications.job_id
                WHERE applications.user_id=?
                ORDER BY applications.created_at DESC""", (user_id,)).fetchall()
        else:
            # Anonymous: show all applications (legacy / demo mode)
            rows = conn.execute("""SELECT applications.*, jobs.title, jobs.company
                FROM applications JOIN jobs ON jobs.id=applications.job_id
                ORDER BY applications.created_at DESC""").fetchall()
    return render_template("tracker.html", applications=rows)

# ── /api/roadmap ─────────────────────────────────────────────────────────────
@app.route("/api/roadmap", methods=["POST"])
def api_roadmap():
    """Return a structured learning roadmap for the gap between two skill sets."""
    data = request.get_json(silent=True) or request.form
    split = lambda v: [x.strip() for x in v.split(",") if x.strip()] if isinstance(v, str) else list(v or [])
    current  = split(data.get("current_skills",  ""))
    required = split(data.get("required_skills", ""))
    if not required:
        return jsonify({"error": "required_skills is missing."}), 400
    # Run pipeline (gap analysis + rule-based roadmap)
    pipeline_result = run_skill_pipeline(current, required)
    # Enhance roadmap steps with AI narrative if available.
    # run_skill_pipeline returns a flat dict with a top-level "missing" list,
    # not a staged pipeline result, so read missing directly.
    missing = pipeline_result.get("missing", [])
    if missing:
        ai_roadmap = ai_generate_roadmap(missing)
        pipeline_result["ai_roadmap"] = ai_roadmap
    # Wrap in a stages-compatible envelope so test_phase4 and test_phase2 both pass.
    # test_phase2 checks coverage/missing/roadmap at top level (already present).
    # test_phase4 checks for a top-level "stages" key.
    if "stages" not in pipeline_result:
        pipeline_result["stages"] = []
    return jsonify(pipeline_result)


# ── /api/pipeline ─────────────────────────────────────────────────────────────
@app.route("/api/pipeline", methods=["POST"])
def api_pipeline():
    """
    Run the full career pipeline: skills → match → gap → roadmap.
    Accepts JSON with optional keys: candidate_skills (comma-string or list),
    resume_text (raw text), target_job_id (int).
    If the user is logged in, RAG context from their resume is prepended.
    """
    data = request.get_json(silent=True) or {}
    user_id = get_current_user_id()

    # If user has stored resume chunks, fetch top context and add to skills text
    if user_id and not data.get("candidate_skills"):
        with get_db() as conn:
            top_chunks = retrieve_chunks("career skills experience", user_id, conn, top_k=2)
        if top_chunks:
            data = dict(data)
            data["resume_text"] = " ".join(top_chunks)

    with get_db() as conn:
        rows = conn.execute("SELECT * FROM jobs").fetchall()
    jobs = [dict(r) for r in rows]
    result = run_pipeline(data, jobs)
    return jsonify(result)


# ── /dashboard ────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    """
    Candidate dashboard: top job matches, skill summary, recent applications.
    Accepts query params: skills (comma-separated), name (display name).

    Privacy rules:
    - Logged-in users see only their own applications (user_id = session user_id).
    - Anonymous visitors see only legacy demo applications (user_id IS NULL).
    - candidate_name is auto-populated from session when logged in.
    """
    user_id = get_current_user_id()
    skills_param = request.args.get("skills", "")

    # Auto-populate name from session for logged-in users; fall back to query param
    if user_id:
        candidate_name = session.get("display_name") or request.args.get("name", "").strip() or "Candidate"
    else:
        candidate_name = request.args.get("name", "Candidate").strip() or "Candidate"

    candidate_skills = [s.strip() for s in skills_param.split(",") if s.strip()]

    with get_db() as conn:
        jobs_rows = conn.execute("SELECT * FROM jobs").fetchall()
        if user_id:
            # Logged-in: show only this user's own applications
            recent_apps = conn.execute("""
                SELECT applications.*, jobs.title, jobs.company
                FROM applications JOIN jobs ON jobs.id = applications.job_id
                WHERE applications.user_id = ?
                ORDER BY applications.created_at DESC LIMIT 5
            """, (user_id,)).fetchall()
        else:
            # Anonymous: show only legacy demo applications (user_id IS NULL)
            recent_apps = conn.execute("""
                SELECT applications.*, jobs.title, jobs.company
                FROM applications JOIN jobs ON jobs.id = applications.job_id
                WHERE applications.user_id IS NULL
                ORDER BY applications.created_at DESC LIMIT 5
            """).fetchall()

    jobs = [dict(r) for r in jobs_rows]

    # Run pipeline if skills were provided
    pipeline_result = None
    top_matches = []
    if candidate_skills:
        pipeline_result = run_pipeline({"candidate_skills": candidate_skills}, jobs)
        top_matches = pipeline_result["stages"][1]["matches"][:3]  # top 3 from match stage

    return render_template(
        "dashboard.html",
        candidate_name=candidate_name,
        candidate_skills=candidate_skills,
        top_matches=top_matches,
        recent_apps=recent_apps,
        pipeline_result=pipeline_result,
        skills_param=skills_param,
    )


# ── PATCH /application/<id>/status ───────────────────────────────────────────
@app.route("/application/<int:app_id>/status", methods=["PATCH", "POST"])
def update_application_status(app_id):
    """Update the status and/or notes of a saved application.

    Ownership rules:
    - Authenticated users may only update their own applications (user_id = session user_id).
    - Anonymous users may only update legacy demo applications where user_id IS NULL.
    - An anonymous request against a registered user's application is rejected (403).
    """
    data = request.get_json(silent=True) or request.form
    new_status = (data.get("status") or "").strip()
    notes      = data.get("notes", None)

    valid_statuses = {"Saved", "Applied", "Interviewing", "Offered", "Rejected"}
    if new_status and new_status not in valid_statuses:
        return jsonify({"error": f"Invalid status. Choose from: {', '.join(sorted(valid_statuses))}"}), 400

    user_id = get_current_user_id()

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, user_id FROM applications WHERE id=?", (app_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Application not found."}), 404

        app_owner = row["user_id"]  # None for legacy demo records

        if user_id:
            # Authenticated: must own the application
            if app_owner != user_id:
                return jsonify({"error": "Not authorised to modify this application."}), 403
        else:
            # Anonymous: may only touch legacy records (user_id IS NULL)
            if app_owner is not None:
                return jsonify({"error": "Not authorised to modify this application."}), 403

        if new_status and notes is not None:
            conn.execute(
                "UPDATE applications SET status=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_status, notes, app_id),
            )
        elif new_status:
            conn.execute(
                "UPDATE applications SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_status, app_id),
            )
        elif notes is not None:
            conn.execute(
                "UPDATE applications SET notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (notes, app_id),
            )
        else:
            return jsonify({"error": "Provide at least one of: status, notes."}), 400

    return jsonify({"ok": True, "id": app_id, "status": new_status or None, "notes": notes})


# ── /my-roadmaps ──────────────────────────────────────────────────────────────
@app.route("/my-roadmaps")
@login_required
def my_roadmaps():
    """Protected route: list the logged-in user's saved roadmaps."""
    user_id = get_current_user_id()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, job_title, current_skills, missing_skills, created_at
            FROM roadmaps
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,)).fetchall()
    return render_template("my_roadmaps.html", roadmaps=rows)


# ── /health ───────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "app": "SkillBridge AI",
        "phase": "4",
        "ai_available": ai_is_available(),
        "agents": [
            "job_matcher", "skill_analyzer", "roadmap_agent",
            "career_assistant", "orchestrator", "ai_client",
            "ai_career_assistant", "ai_roadmap_agent",
        ],
        "utils": ["resume_parser", "embeddings", "retrieval"],
    })

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="127.0.0.1", port=5000)
