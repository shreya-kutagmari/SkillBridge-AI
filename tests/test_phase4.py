"""
tests/test_phase4.py
---------------------
Phase 4 integration tests for SkillBridge AI.
Covers: auth routes, AI assistant (fallback), AI roadmap (fallback),
        resume upload + chunking, RAG retrieval, per-user data isolation,
        embeddings utils, and consent banner presence.

All tests run against a temporary in-memory SQLite database so they do not
pollute the real database.db.  No watsonx.ai credentials are required —
all AI calls fall back to the rule-based engines gracefully.

Run:
    python tests/test_phase4.py
"""

from __future__ import annotations

import json
import io
import os
import sys
import tempfile
import sqlite3

# Ensure repo root is on the path when running directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as _app_module
from utils.embeddings import _split_into_sentences, _make_chunks, store_resume_chunks, delete_resume_chunks
from utils.retrieval import _cosine_similarity, _keyword_score, retrieve_chunks
from agents.ai_career_assistant import ai_career_reply
from agents.ai_roadmap_agent import ai_generate_roadmap

# ── Test helpers ─────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0
_errors: list[str] = []


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        _errors.append(label)
        print(f"  FAIL  {label}")


def section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print("─" * 60)


def make_test_app():
    """Create a Flask test client with a fresh temporary DB."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _app_module.DB_PATH = _app_module.Path(tmp.name)
    _app_module.app.config["TESTING"] = True
    _app_module.app.config["WTF_CSRF_ENABLED"] = False
    _app_module.init_db()
    client = _app_module.app.test_client()
    return client, tmp.name


def make_in_memory_db() -> sqlite3.Connection:
    """Create a minimal in-memory DB for util-level tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE, password_hash TEXT, display_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        consent_given INTEGER DEFAULT 0, consent_at TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE resume_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, resume_filename TEXT NOT NULL,
        chunk_index INTEGER NOT NULL, chunk_text TEXT NOT NULL,
        embedding_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    return conn


# ═══════════════════════════════════════════════════════════════════════════
# 1. Embeddings utils
# ═══════════════════════════════════════════════════════════════════════════

def test_embeddings_utils():
    section("1. utils/embeddings.py — chunking logic")

    # Sentence splitting
    sentences = _split_into_sentences("Hello world. This is a test! And another?")
    check("split_into_sentences returns list", isinstance(sentences, list))
    check("split_into_sentences finds 3 sentences", len(sentences) == 3)

    # Empty text
    check("split empty string returns []", _split_into_sentences("") == [])

    # Chunking — small input → single chunk
    short = ["A", "B"]
    chunks = _make_chunks(short, size=5, overlap=2)
    check("short input → 1 chunk", len(chunks) == 1)
    check("short chunk contains both sentences", "A" in chunks[0] and "B" in chunks[0])

    # Chunking — longer input
    long_sentences = [f"Sentence {i}." for i in range(12)]
    chunks_long = _make_chunks(long_sentences, size=5, overlap=2)
    check("long input → multiple chunks", len(chunks_long) > 1)

    # store_resume_chunks — no embeddings (no AI available)
    conn = make_in_memory_db()
    n = store_resume_chunks(
        user_id=1,
        filename="test_resume.txt",
        text="I know Python. I have used SQL. Flask is my framework. Git is my tool. Docker is great.",
        conn=conn,
    )
    check("store_resume_chunks returns positive count", n > 0)
    rows = conn.execute("SELECT * FROM resume_chunks WHERE user_id=1").fetchall()
    check("chunks inserted into DB", len(rows) == n)
    check("chunk_text not empty", all(r["chunk_text"] for r in rows))

    # delete_resume_chunks
    delete_resume_chunks(1, conn)
    remaining = conn.execute("SELECT COUNT(*) FROM resume_chunks WHERE user_id=1").fetchone()[0]
    check("delete_resume_chunks removes all user chunks", remaining == 0)
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Retrieval utils
# ═══════════════════════════════════════════════════════════════════════════

def test_retrieval_utils():
    section("2. utils/retrieval.py — similarity and retrieval")

    # Cosine similarity
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    check("identical vectors → cosine=1.0", abs(_cosine_similarity(a, b) - 1.0) < 1e-6)

    c = [0.0, 1.0, 0.0]
    check("orthogonal vectors → cosine=0.0", abs(_cosine_similarity(a, c)) < 1e-6)

    zero = [0.0, 0.0, 0.0]
    check("zero vector → cosine=0.0 (no crash)", _cosine_similarity(a, zero) == 0.0)

    # Keyword score
    check("exact match → score 1.0", _keyword_score("python sql", "python sql") == 1.0)
    check("no overlap → score 0.0", _keyword_score("python", "banana") == 0.0)
    check("partial overlap → 0 < score < 1", 0 < _keyword_score("python sql flask", "python django") < 1.0)
    check("empty query → 0.0", _keyword_score("", "python sql") == 0.0)

    # retrieve_chunks — keyword path (no embeddings)
    conn = make_in_memory_db()
    store_resume_chunks(
        user_id=2,
        filename="cv.txt",
        text=(
            "I am a Python developer with 2 years of experience. "
            "I have worked with Flask and SQL databases. "
            "I enjoy machine learning and data science. "
            "I use Git for version control every day. "
            "Docker and CI/CD are part of my workflow. "
            "I have contributed to open source projects on GitHub."
        ),
        conn=conn,
    )
    results = retrieve_chunks("Python Flask SQL", user_id=2, conn=conn, top_k=2)
    check("retrieve_chunks returns list", isinstance(results, list))
    check("retrieve_chunks returns ≤ top_k results", len(results) <= 2)
    check("retrieve_chunks returns non-empty strings", all(isinstance(r, str) and r for r in results))

    # User with no chunks
    empty_results = retrieve_chunks("anything", user_id=999, conn=conn, top_k=3)
    check("retrieve_chunks → [] for unknown user", empty_results == [])
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. AI career assistant (fallback mode — no watsonx.ai)
# ═══════════════════════════════════════════════════════════════════════════

def test_ai_career_assistant():
    section("3. agents/ai_career_assistant.py — fallback mode")

    # Normal English query
    reply = ai_career_reply("How do I improve my resume?", "English")
    check("English reply is a string", isinstance(reply, str))
    check("English reply is non-empty", len(reply) > 10)

    # Kannada query
    reply_kn = ai_career_reply("ರೆಸ್ಯೂಮ್ ಸುಧಾರಿಸುವುದು ಹೇಗೆ?", "Kannada")
    check("Kannada reply is a string", isinstance(reply_kn, str))
    check("Kannada reply is non-empty", len(reply_kn) > 10)

    # Empty message
    reply_empty = ai_career_reply("", "English")
    check("empty message returns fallback string", isinstance(reply_empty, str))

    # Unknown language → defaults to English rule-based
    reply_unknown = ai_career_reply("tell me about jobs", "French")
    check("unknown language returns string", isinstance(reply_unknown, str))


# ═══════════════════════════════════════════════════════════════════════════
# 4. AI roadmap agent (fallback mode — no watsonx.ai)
# ═══════════════════════════════════════════════════════════════════════════

def test_ai_roadmap_agent():
    section("4. agents/ai_roadmap_agent.py — fallback mode")

    roadmap = ai_generate_roadmap(["python", "sql", "flask"])
    check("returns dict", isinstance(roadmap, dict))
    check("has total_skills", "total_skills" in roadmap)
    check("total_skills == 3", roadmap["total_skills"] == 3)
    check("has ordered_steps", "ordered_steps" in roadmap)
    check("ordered_steps len == 3", len(roadmap["ordered_steps"]) == 3)
    check("has ai_narrative key", "ai_narrative" in roadmap)
    check("ai_narrative is None (no credentials)", roadmap["ai_narrative"] is None)
    check("has stages", "stages" in roadmap)
    check("total_est_days > 0", roadmap["total_est_days"] > 0)

    # Empty input
    empty = ai_generate_roadmap([])
    check("empty input → total_skills=0", empty["total_skills"] == 0)
    check("empty input → ai_narrative=None", empty["ai_narrative"] is None)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Auth routes — register / login / logout
# ═══════════════════════════════════════════════════════════════════════════

def test_auth_routes():
    section("5. Auth routes — register / login / logout")
    client, db_path = make_test_app()

    # GET /register
    r = client.get("/register")
    check("GET /register → 200", r.status_code == 200)
    check("register page has form", b"<form" in r.data)

    # POST /register — valid
    r = client.post("/register", data={
        "email": "tester@example.com",
        "display_name": "Tester",
        "password": "password123",
        "confirm_password": "password123",
        "consent": "1",
    }, follow_redirects=True)
    check("valid register → 200", r.status_code == 200)

    # POST /register — duplicate email
    r2 = client.post("/register", data={
        "email": "tester@example.com",
        "display_name": "Tester2",
        "password": "password123",
        "confirm_password": "password123",
        "consent": "1",
    }, follow_redirects=True)
    check("duplicate register → 200 with error", r2.status_code == 200)
    check("duplicate register shows error", b"already exists" in r2.data.lower() or b"error" in r2.data.lower())

    # POST /register — passwords don't match
    r3 = client.post("/register", data={
        "email": "new@example.com",
        "display_name": "New",
        "password": "password123",
        "confirm_password": "differentpass",
        "consent": "1",
    }, follow_redirects=True)
    check("mismatched passwords → error", b"do not match" in r3.data.lower() or b"error" in r3.data.lower())

    # POST /register — short password
    r4 = client.post("/register", data={
        "email": "short@example.com",
        "display_name": "Short",
        "password": "abc",
        "confirm_password": "abc",
        "consent": "1",
    }, follow_redirects=True)
    check("short password → error", b"8 characters" in r4.data.lower() or b"error" in r4.data.lower())

    # POST /register — no consent
    r5 = client.post("/register", data={
        "email": "noconsent@example.com",
        "display_name": "NoConsent",
        "password": "password123",
        "confirm_password": "password123",
    }, follow_redirects=True)
    check("missing consent → error", b"privacy" in r5.data.lower() or b"error" in r5.data.lower())

    # GET /login
    r = client.get("/login")
    check("GET /login → 200", r.status_code == 200)

    # POST /login — correct credentials
    r_login = client.post("/login", data={
        "email": "tester@example.com",
        "password": "password123",
    }, follow_redirects=True)
    check("valid login → 200", r_login.status_code == 200)

    # POST /login — wrong password
    r_bad = client.post("/login", data={
        "email": "tester@example.com",
        "password": "wrongpass",
    }, follow_redirects=True)
    check("wrong password → error flash", b"incorrect" in r_bad.data.lower() or b"error" in r_bad.data.lower())

    # GET /logout
    r_out = client.get("/logout", follow_redirects=True)
    check("logout → 200", r_out.status_code == 200)

    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 6. /assistant route — AI-enhanced, returns ai_powered flag
# ═══════════════════════════════════════════════════════════════════════════

def test_assistant_route():
    section("6. /assistant route — AI-enhanced")
    client, db_path = make_test_app()

    r = client.post("/assistant", json={"message": "how do I improve my resume?", "language": "English"})
    check("/assistant → 200", r.status_code == 200)
    data = json.loads(r.data)
    check("response has reply", "reply" in data)
    check("reply is non-empty string", isinstance(data["reply"], str) and len(data["reply"]) > 5)
    check("response has ai_powered flag", "ai_powered" in data)
    check("ai_powered is bool", isinstance(data["ai_powered"], bool))

    # Kannada
    r_kn = client.post("/assistant", json={"message": "ರೆಸ್ಯೂಮ್ ಹೇಗೆ ಸಿದ್ಧಪಡಿಸಬೇಕು?", "language": "Kannada"})
    check("Kannada /assistant → 200", r_kn.status_code == 200)
    kn_data = json.loads(r_kn.data)
    check("Kannada reply non-empty", isinstance(kn_data.get("reply"), str) and len(kn_data["reply"]) > 5)

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 7. /api/roadmap — AI narrative key present
# ═══════════════════════════════════════════════════════════════════════════

def test_roadmap_route():
    section("7. /api/roadmap — AI narrative field")
    client, db_path = make_test_app()

    r = client.post("/api/roadmap", json={
        "current_skills": "python",
        "required_skills": "python,sql,flask,docker",
    })
    check("/api/roadmap → 200", r.status_code == 200)
    data = json.loads(r.data)
    check("stages key present", "stages" in data)
    # ai_roadmap key should be present when there are missing skills
    check("ai_roadmap key present", "ai_roadmap" in data)
    if "ai_roadmap" in data:
        ar = data["ai_roadmap"]
        check("ai_roadmap has total_skills", "total_skills" in ar)
        check("ai_roadmap has ai_narrative key", "ai_narrative" in ar)

    # Missing required_skills → 400
    r_bad = client.post("/api/roadmap", json={"current_skills": "python"})
    check("missing required_skills → 400", r_bad.status_code == 400)

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 8. /resume upload route — chunks_stored field
# ═══════════════════════════════════════════════════════════════════════════

def test_resume_route():
    section("8. /resume upload — chunk storage")
    client, db_path = make_test_app()

    # Anonymous upload — chunks_stored=0 (no user_id)
    txt_content = (
        b"I am a Python developer with experience in Flask and SQL. "
        b"I have built data pipelines with pandas and numpy. "
        b"I use Git for version control and Docker for deployment. "
        b"I enjoy machine learning and data analysis projects."
    )
    r = client.post("/resume", data={
        "resume": (io.BytesIO(txt_content), "test_resume.txt"),
    }, content_type="multipart/form-data")
    check("/resume anonymous → 200", r.status_code == 200)
    data = json.loads(r.data)
    check("response has skills", "skills" in data)
    check("response has chunks_stored", "chunks_stored" in data)
    check("anonymous → chunks_stored=0", data["chunks_stored"] == 0)
    check("response has preview", "preview" in data)

    # Invalid extension
    r_bad = client.post("/resume", data={
        "resume": (io.BytesIO(b"bad content"), "resume.exe"),
    }, content_type="multipart/form-data")
    check("invalid extension → 400", r_bad.status_code == 400)

    # No file
    r_nofile = client.post("/resume")
    check("no file → 400", r_nofile.status_code == 400)

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 9. /health — phase 4, agents list updated
# ═══════════════════════════════════════════════════════════════════════════

def test_health_route():
    section("9. /health — phase 4 metadata")
    client, db_path = make_test_app()

    r = client.get("/health")
    check("/health → 200", r.status_code == 200)
    data = json.loads(r.data)
    check("status=ok", data.get("status") == "ok")
    check("phase=4", data.get("phase") == "4")
    check("ai_available is bool", isinstance(data.get("ai_available"), bool))
    check("ai_career_assistant in agents", "ai_career_assistant" in data.get("agents", []))
    check("ai_roadmap_agent in agents", "ai_roadmap_agent" in data.get("agents", []))
    check("utils key present", "utils" in data)

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 10. /privacy route
# ═══════════════════════════════════════════════════════════════════════════

def test_privacy_route():
    section("10. /privacy route")
    client, db_path = make_test_app()

    r = client.get("/privacy")
    check("/privacy → 200", r.status_code == 200)
    check("privacy page has content", len(r.data) > 200)

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 11. Existing routes preserved (regression)
# ═══════════════════════════════════════════════════════════════════════════

def test_existing_routes_preserved():
    section("11. Existing route regression")
    client, db_path = make_test_app()

    check("GET / → 200", client.get("/").status_code == 200)
    check("GET /jobs → 200", client.get("/jobs").status_code == 200)
    check("GET /tracker → 200", client.get("/tracker").status_code == 200)
    check("GET /dashboard → 200", client.get("/dashboard").status_code == 200)

    r = client.post("/api/match", json={"skills": "python,sql"})
    check("POST /api/match → 200", r.status_code == 200)
    check("/api/match returns list", isinstance(json.loads(r.data), list))

    r = client.post("/api/skill-gap", json={
        "current_skills": "python",
        "required_skills": "python,sql,flask",
    })
    check("POST /api/skill-gap → 200", r.status_code == 200)

    r = client.post("/api/pipeline", json={"candidate_skills": "python,sql"})
    check("POST /api/pipeline → 200", r.status_code == 200)

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  SkillBridge AI — Phase 4 Test Suite")
    print("═" * 60)

    test_embeddings_utils()
    test_retrieval_utils()
    test_ai_career_assistant()
    test_ai_roadmap_agent()
    test_auth_routes()
    test_assistant_route()
    test_roadmap_route()
    test_resume_route()
    test_health_route()
    test_privacy_route()
    test_existing_routes_preserved()

    print("\n" + "═" * 60)
    total = PASS + FAIL
    print(f"  Result: {PASS}/{total} passed, {FAIL} failed")
    if _errors:
        print("  Failed assertions:")
        for e in _errors:
            print(f"    ✗ {e}")
    print("═" * 60)
    sys.exit(0 if FAIL == 0 else 1)
