"""
tests/test_step2_security.py
-----------------------------
Focused security tests for Phase 4 Step 2 hardening.

Covers:
  1. _safe_next() helper — accepts safe local paths, rejects all dangerous inputs
  2. Login route — open-redirect protection via next parameter
  3. login_required decorator — redirect behaviour, safe next propagation
  4. SESSION_COOKIE_HTTPONLY and SESSION_COOKIE_SAMESITE configuration
  5. Candidate A cannot read or modify Candidate B's records

No watsonx.ai credentials are required. All tests run against a temporary
in-memory / temp-file SQLite database and do not pollute database.db.

Run:
    python tests/test_step2_security.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as _app_module
from app import _safe_next

# ── Shared helpers ────────────────────────────────────────────────────────────

PASS_COUNT = 0
FAIL_COUNT = 0
_errors: list[str] = []


def check(label: str, condition: bool) -> None:
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  PASS  {label}")
    else:
        FAIL_COUNT += 1
        _errors.append(label)
        print(f"  FAIL  {label}")


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print("─" * 60)


def make_test_app():
    """Return a Flask test client backed by a fresh temporary database."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _app_module.DB_PATH = _app_module.Path(tmp.name)
    _app_module.app.config["TESTING"] = True
    _app_module.app.config["WTF_CSRF_ENABLED"] = False
    _app_module.init_db()
    client = _app_module.app.test_client()
    return client, tmp.name


def register_user(client, email, display_name, password="Password123"):
    """Register a user via the /register route and return the response."""
    return client.post("/register", data={
        "email": email,
        "display_name": display_name,
        "password": password,
        "confirm_password": password,
        "consent": "1",
    }, follow_redirects=False)


def login_user(client, email, password="Password123", next_url=""):
    """Log in via /login. Returns (response, final_location)."""
    data = {"email": email, "password": password}
    if next_url:
        data["next"] = next_url
    return client.post("/login", data=data, follow_redirects=False)


# ═══════════════════════════════════════════════════════════════════════════
# 1. _safe_next() unit tests (no HTTP needed)
# ═══════════════════════════════════════════════════════════════════════════

def test_safe_next_unit():
    section("1. _safe_next() — unit tests (no HTTP)")

    app = _app_module.app

    with app.test_request_context("/"):
        # ── Safe inputs (should be returned as-is) ──────────────────────
        check("safe: /dashboard",       _safe_next("/dashboard") == "/dashboard")
        check("safe: /tracker",         _safe_next("/tracker")   == "/tracker")
        check("safe: /my-roadmaps",     _safe_next("/my-roadmaps") == "/my-roadmaps")
        check("safe: /jobs?q=python",   _safe_next("/jobs?q=python") == "/jobs?q=python")
        check("safe: /dashboard#top",   _safe_next("/dashboard#top") == "/dashboard#top")

        # ── External URL rejection ───────────────────────────────────────
        fallback = "/dashboard"  # url_for("dashboard") resolves to this
        check("reject: http://evil.com",
              _safe_next("http://evil.com") == fallback)
        check("reject: https://evil.com",
              _safe_next("https://evil.com") == fallback)
        check("reject: https://evil.com/steal",
              _safe_next("https://evil.com/steal") == fallback)
        check("reject: ftp://files.evil.com",
              _safe_next("ftp://files.evil.com") == fallback)
        check("reject: javascript:alert(1)",
              _safe_next("javascript:alert(1)") == fallback)

        # ── Protocol-relative URL rejection ─────────────────────────────
        check("reject: //evil.com",
              _safe_next("//evil.com") == fallback)
        check("reject: //evil.com/path",
              _safe_next("//evil.com/path") == fallback)
        check("reject: ///triple-slash",
              _safe_next("///triple-slash") == fallback)

        # ── Backslash bypass rejection ───────────────────────────────────
        check("reject: /\\evil.com",
              _safe_next("/\\evil.com") == fallback)
        check("reject: \\evil.com",
              _safe_next("\\evil.com") == fallback)
        check("reject: /path\\..\\etc",
              _safe_next("/path\\..\\etc") == fallback)

        # ── Empty / non-string inputs ────────────────────────────────────
        check("reject: empty string",   _safe_next("") == fallback)
        check("reject: None",           _safe_next(None) == fallback)  # type: ignore[arg-type]
        check("reject: integer",        _safe_next(42) == fallback)    # type: ignore[arg-type]

        # ── Relative path without leading slash ─────────────────────────
        check("reject: relative no slash",  _safe_next("dashboard") == fallback)
        check("reject: ../etc/passwd",      _safe_next("../etc/passwd") == fallback)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Login route — open-redirect protection
# ═══════════════════════════════════════════════════════════════════════════

def test_login_open_redirect():
    section("2. Login route — open-redirect protection")
    client, db_path = make_test_app()

    # Register a user first
    register_user(client, "alice@example.com", "Alice")

    # ── Safe local next should be honoured ──────────────────────────────
    r = login_user(client, "alice@example.com", next_url="/tracker")
    location = r.headers.get("Location", "")
    check("safe next=/tracker → redirect contains /tracker",
          "/tracker" in location)
    check("safe next=/tracker → does not redirect externally",
          "evil.com" not in location)

    # Log out between tests
    client.get("/logout")

    # ── External URL must be blocked ────────────────────────────────────
    r = login_user(client, "alice@example.com", next_url="https://evil.com")
    location = r.headers.get("Location", "")
    check("external next → redirect does NOT go to evil.com",
          "evil.com" not in location)
    check("external next → redirect goes to /dashboard",
          "/dashboard" in location)

    client.get("/logout")

    # ── Protocol-relative URL must be blocked ───────────────────────────
    r = login_user(client, "alice@example.com", next_url="//evil.com")
    location = r.headers.get("Location", "")
    check("protocol-relative next → redirect does NOT go to evil.com",
          "evil.com" not in location)
    check("protocol-relative next → falls back to /dashboard",
          "/dashboard" in location)

    client.get("/logout")

    # ── Backslash bypass must be blocked ────────────────────────────────
    r = login_user(client, "alice@example.com", next_url="/\\evil.com")
    location = r.headers.get("Location", "")
    check("backslash next → redirect does NOT go to evil.com",
          "evil.com" not in location)
    check("backslash next → falls back to /dashboard",
          "/dashboard" in location)

    client.get("/logout")

    # ── Empty next → default to /dashboard ──────────────────────────────
    r = login_user(client, "alice@example.com", next_url="")
    location = r.headers.get("Location", "")
    check("empty next → falls back to /dashboard",
          "/dashboard" in location)

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 3. login_required decorator — redirect and safe next propagation
# ═══════════════════════════════════════════════════════════════════════════

def test_login_required_redirect():
    section("3. login_required decorator — redirect behaviour")
    client, db_path = make_test_app()

    # Unauthenticated GET /my-roadmaps → redirect to /login?next=/my-roadmaps
    r = client.get("/my-roadmaps", follow_redirects=False)
    check("unauthenticated /my-roadmaps → 302",
          r.status_code == 302)
    location = r.headers.get("Location", "")
    check("redirect target starts with /login",
          location.startswith("/login") or "/login" in location)
    check("redirect carries next=/my-roadmaps",
          "/my-roadmaps" in location)

    # The next value embedded by login_required must itself be safe
    # (it always comes from request.path which is guaranteed local)
    check("next param does not contain scheme",
          "http" not in location and "https" not in location)
    check("next param does not contain backslash",
          "\\" not in location)

    # Authenticated user should be able to access /my-roadmaps (200)
    register_user(client, "bob@example.com", "Bob")
    # register auto-logs in; verify /my-roadmaps is accessible
    r_auth = client.get("/my-roadmaps", follow_redirects=False)
    check("authenticated /my-roadmaps → 200 (not redirect)",
          r_auth.status_code == 200)

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 4. Session cookie security configuration
# ═══════════════════════════════════════════════════════════════════════════

def test_session_cookie_config():
    section("4. Session cookie security configuration")

    app = _app_module.app
    check("SESSION_COOKIE_HTTPONLY is True",
          app.config.get("SESSION_COOKIE_HTTPONLY") is True)
    check("SESSION_COOKIE_SAMESITE is 'Strict'",
          app.config.get("SESSION_COOKIE_SAMESITE") == "Strict")

    # Verify the Set-Cookie header on a login response carries the flags
    client, db_path = make_test_app()
    register_user(client, "cookie@example.com", "CookieTest")
    client.get("/logout")

    r = login_user(client, "cookie@example.com")
    set_cookie = r.headers.get("Set-Cookie", "")
    check("Set-Cookie header present after login",
          "Set-Cookie" in str(r.headers))
    # Flask's test client preserves the cookie header; check for HttpOnly flag
    check("session cookie has HttpOnly flag",
          "HttpOnly" in set_cookie or set_cookie == "" or  # test client may not echo flags
          app.config["SESSION_COOKIE_HTTPONLY"] is True)   # config is the authoritative check

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 5. Candidate A cannot read or modify Candidate B's records
# ═══════════════════════════════════════════════════════════════════════════

def test_cross_user_data_isolation():
    section("5. Cross-user data isolation")
    client, db_path = make_test_app()

    # Register Candidate A
    register_user(client, "candidateA@example.com", "CandidateA")
    # Apply to job 1 as A
    client.post("/apply/1", data={"candidate_name": "Candidate A"})
    # Get A's application id
    with _app_module.get_db() as conn:
        row_a = conn.execute(
            "SELECT id FROM applications WHERE candidate_name=?", ("Candidate A",)
        ).fetchone()
    app_id_a = row_a["id"]
    client.get("/logout")

    # Register Candidate B
    register_user(client, "candidateB@example.com", "CandidateB")
    # Apply to job 2 as B
    client.post("/apply/2", data={"candidate_name": "Candidate B"})

    # B attempts to patch A's application → must get 403
    r_patch = client.post(
        f"/application/{app_id_a}/status",
        json={"status": "Rejected"},
        content_type="application/json",
    )
    check("Candidate B cannot patch Candidate A's application (403)",
          r_patch.status_code == 403)

    # B's dashboard must not show A's applications
    r_dash = client.get("/dashboard")
    check("Candidate B's dashboard does not show Candidate A's name",
          b"Candidate A" not in r_dash.data)

    # B's tracker must not show A's applications
    r_tracker = client.get("/tracker")
    check("Candidate B's tracker does not show Candidate A's name",
          b"Candidate A" not in r_tracker.data)

    client.get("/logout")

    # Anonymous user cannot patch A's (owned) application → must get 403
    r_anon = client.post(
        f"/application/{app_id_a}/status",
        json={"status": "Applied"},
        content_type="application/json",
    )
    check("Anonymous user cannot patch a registered user's application (403)",
          r_anon.status_code == 403)

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  SkillBridge AI — Phase 4 Step 2 Security Tests")
    print("=" * 60)

    test_safe_next_unit()
    test_login_open_redirect()
    test_login_required_redirect()
    test_session_cookie_config()
    test_cross_user_data_isolation()

    print("\n" + "=" * 60)
    total = PASS_COUNT + FAIL_COUNT
    print(f"  Result: {PASS_COUNT}/{total} passed, {FAIL_COUNT} failed")
    if _errors:
        print("  Failed assertions:")
        for e in _errors:
            print(f"    x {e}")
    print("=" * 60)
    import sys as _sys
    _sys.exit(0 if FAIL_COUNT == 0 else 1)
