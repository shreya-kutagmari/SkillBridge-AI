"""
agents/roadmap_agent.py
-----------------------
Generates structured, prioritised learning roadmaps for missing skills.

Each roadmap step has:
  - skill       : canonical skill name
  - stage       : "Foundation" | "Intermediate" | "Advanced"
  - priority    : 1 (highest) – 3 (lower)
  - resource    : suggested learning resource type + title
  - exercise    : a concrete, small practical exercise
  - est_days    : rough days to reach working knowledge

The SKILL_CATALOG maps every known skill to its metadata. Skills not in the
catalog fall back to a sensible generic entry so the agent never crashes.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Skill catalog
# Each entry: (stage, priority, resource_type, resource_hint, exercise, est_days)
#
# priority: 1 = high demand / fundamental, 2 = important, 3 = specialised
# ---------------------------------------------------------------------------
_CATALOG: dict[str, tuple[str, int, str, str, str, int]] = {
    # fmt: off
    # ── Fundamentals ─────────────────────────────────────────────────────────
    "python":               ("Foundation",    1, "Interactive tutorial",  "Python.org official tutorial",                       "Write a script that reads a CSV file and prints the top 5 rows.",             7),
    "sql":                  ("Foundation",    1, "Practice platform",     "SQLZoo or Mode Analytics SQL tutorial",              "Query a public dataset: find top 10 results using GROUP BY and ORDER BY.",   5),
    "git":                  ("Foundation",    1, "Hands-on guide",        "Pro Git book (free at git-scm.com)",                 "Create a repo, make 3 commits, branch, merge, and push to GitHub.",          3),
    "html":                 ("Foundation",    1, "MDN Web Docs",          "MDN HTML basics guide",                              "Build a 3-page static personal portfolio site.",                              4),
    "css":                  ("Foundation",    1, "MDN Web Docs",          "MDN CSS first steps guide",                          "Style your portfolio: add responsive layout with flexbox.",                  4),
    "javascript":           ("Foundation",    1, "Interactive course",    "javascript.info",                                    "Build a to-do list app using vanilla JS with add/delete/complete.",           7),
    "communication":        ("Foundation",    1, "Practice",              "Toastmasters or peer presentations",                 "Record a 3-minute explanation of one technical topic you know.",               3),
    "linux":                ("Foundation",    2, "Interactive tutorial",  "OverTheWire Bandit wargame",                         "Navigate a file system, edit files with vim, and write a bash script.",      5),
    "statistics":           ("Foundation",    2, "Video course",          "Khan Academy Statistics and Probability",            "Calculate mean, median, standard deviation on a real dataset in Python.",     5),
    "excel":                ("Foundation",    2, "Video tutorial",        "Excel with Business (Coursera audit)",               "Create a pivot table and VLOOKUP on a sample sales dataset.",                 3),

    # ── Web & backend ─────────────────────────────────────────────────────────
    "flask":                ("Intermediate",  1, "Official docs + demo", "Flask mega-tutorial by Miguel Grinberg",             "Build a CRUD app with Flask, SQLite, and HTML forms.",                        7),
    "django":               ("Intermediate",  1, "Official tutorial",    "Django project official tutorial",                   "Build a blog app using Django ORM, views, and templates.",                   10),
    "fastapi":              ("Intermediate",  2, "Official docs",        "FastAPI official tutorial",                          "Create a REST API with two endpoints, request validation, and auto-docs.",     5),
    "react":                ("Intermediate",  1, "Official tutorial",    "React.dev official tutorial",                        "Build a filterable product list component using hooks.",                       7),
    "node.js":              ("Intermediate",  2, "Video course",         "Node.js crash course (Traversy Media)",              "Create an Express server with 3 REST endpoints and test with Postman.",        5),
    "typescript":           ("Intermediate",  2, "Official handbook",    "TypeScript Handbook (typescriptlang.org)",           "Convert a small JavaScript project to TypeScript, fix all type errors.",       5),

    # ── Data & ML ─────────────────────────────────────────────────────────────
    "pandas":               ("Foundation",    1, "Official docs",        "10 minutes to pandas (pandas.pydata.org)",           "Load a CSV, clean nulls, filter rows, and export a summary report.",          4),
    "numpy":                ("Foundation",    1, "Official docs",        "NumPy quickstart guide",                             "Create arrays, reshape, slice, and compute statistics on a random matrix.",   3),
    "machine learning":     ("Intermediate",  1, "Video course",         "Andrew Ng's ML Specialisation (Coursera audit)",     "Train a linear regression and a decision tree on a Kaggle dataset.",         14),
    "scikit-learn":         ("Intermediate",  1, "Official docs",        "scikit-learn user guide",                            "Build a classification pipeline with preprocessing and cross-validation.",    7),
    "deep learning":        ("Advanced",      2, "Video course",         "deeplearning.ai Deep Learning Specialisation",       "Build and train a small neural network on MNIST with PyTorch.",              14),
    "tensorflow":           ("Advanced",      2, "Official tutorials",   "TensorFlow Core tutorials",                          "Train a CNN for image classification on the CIFAR-10 dataset.",              10),
    "pytorch":              ("Advanced",      2, "Official tutorials",   "PyTorch 60-minute blitz",                            "Implement and train a simple MLP from scratch using autograd.",              10),
    "natural language processing": ("Advanced", 2, "Book",               "Speech and Language Processing (Jurafsky)",          "Build a text classifier using TF-IDF and logistic regression.",              10),
    "data science":         ("Intermediate",  1, "Video course",         "IBM Data Science Professional Certificate (audit)",  "Complete an end-to-end EDA project: load, clean, visualise, summarise.",     10),
    "data analysis":        ("Foundation",    1, "Practice project",     "Kaggle Learn: Pandas + Data Visualisation",          "Analyse a public CSV dataset and answer 5 business questions with code.",      7),
    "data visualization":   ("Intermediate",  2, "Practice",             "Plotly and Matplotlib documentation",                "Create 3 chart types (line, bar, scatter) for the same dataset.",             4),
    "matplotlib":           ("Foundation",    2, "Official docs",        "Matplotlib tutorials",                               "Reproduce 3 chart types from a provided dataset.",                            3),
    "seaborn":              ("Intermediate",  2, "Official docs",        "Seaborn tutorial gallery",                           "Create a correlation heatmap and a pairplot for a real dataset.",             2),
    "scipy":                ("Intermediate",  2, "Official docs",        "SciPy tutorial",                                     "Perform hypothesis testing (t-test) on a real dataset.",                     3),

    # ── Cloud & DevOps ─────────────────────────────────────────────────────────
    "aws":                  ("Intermediate",  1, "Official training",    "AWS Cloud Practitioner Essentials (free)",           "Deploy a static website on S3 with a custom domain using Route 53.",         10),
    "azure":                ("Intermediate",  2, "Official training",    "Microsoft Azure Fundamentals (AZ-900 free path)",    "Create an Azure Web App and deploy a Flask app via GitHub Actions.",         10),
    "docker":               ("Intermediate",  1, "Official docs",        "Docker getting started guide",                       "Containerise a Flask app: write a Dockerfile, build, and run it locally.",    5),
    "kubernetes":           ("Advanced",      2, "Interactive tutorial", "Kubernetes.io interactive tutorial",                 "Deploy a containerised app to a local Minikube cluster with a Service.",      7),
    "ci/cd":                ("Intermediate",  2, "Official docs",        "GitHub Actions quickstart",                          "Write a CI workflow that runs tests on every push to main.",                  5),
    "github actions":       ("Intermediate",  2, "Official docs",        "GitHub Actions quickstart",                          "Write a CI workflow that lints and tests a Python project on push.",          4),

    # ── Databases ─────────────────────────────────────────────────────────────
    "mongodb":              ("Intermediate",  2, "Official docs",        "MongoDB University M001 (free)",                     "Create a collection, insert 20 documents, and write 5 aggregation queries.", 5),
    "postgresql":           ("Intermediate",  1, "Tutorial",             "postgresqltutorial.com",                             "Design a 3-table schema with foreign keys and write complex JOIN queries.",   5),
    "redis":                ("Intermediate",  2, "Official docs",        "Redis quickstart guide",                             "Implement a simple cache layer for a Python function using redis-py.",        3),

    # ── IoT & hardware ─────────────────────────────────────────────────────────
    "iot":                  ("Foundation",    2, "Video course",         "Coursera: Introduction to the Internet of Things",   "Connect an LED to an Arduino and control it via serial commands.",            5),
    "arduino":              ("Foundation",    2, "Arduino Project Hub",  "Arduino starter kit documentation",                 "Build a temperature sensor that logs readings every 5 seconds.",              5),
    "networking":           ("Foundation",    2, "Video course",         "CompTIA Network+ study guide (free resources)",      "Configure a home router, capture packets with Wireshark, explain TCP/IP.",   7),
    "embedded c":           ("Intermediate",  2, "Book",                 "C Programming for Embedded Systems (Kirk Zurell)",   "Write a bare-metal LED blink program for an ARM Cortex-M microcontroller.",  7),

    # ── Tools ─────────────────────────────────────────────────────────────────
    "github":               ("Foundation",    1, "Interactive guide",    "GitHub Skills (skills.github.com)",                  "Fork a repo, open a pull request, and resolve a merge conflict.",             2),
    "postman":              ("Foundation",    2, "Official docs",        "Postman Learning Center",                            "Test a public REST API: write 5 requests with assertions in a collection.",   2),
    "jupyter":              ("Foundation",    2, "Official docs",        "Jupyter quickstart guide",                           "Create a notebook: load data, visualise it, write markdown explanations.",    2),
    "tableau":              ("Intermediate",  2, "Official training",    "Tableau Public training videos",                     "Connect to a CSV and build an interactive dashboard with 3 charts.",          5),
    "powerbi":              ("Intermediate",  2, "Official docs",        "Microsoft Power BI guided learning",                 "Import a dataset and build a report with 3 visuals and slicers.",             5),
    "figma":                ("Foundation",    2, "Official tutorial",    "Figma design basics",                                "Design a 3-screen mobile app wireframe and share it as a prototype.",         4),

    # ── Security ──────────────────────────────────────────────────────────────
    "cybersecurity":        ("Foundation",    2, "Video course",         "Cybersecurity for Everyone (Coursera audit)",        "Complete the OverTheWire Bandit levels 0-10.",                                7),
    "owasp":                ("Intermediate",  2, "Official docs",        "OWASP Top 10 documentation",                        "Audit a demo web app for the top 3 OWASP vulnerabilities.",                  5),

    # ── Languages / methodologies ─────────────────────────────────────────────
    "java":                 ("Foundation",    1, "Interactive tutorial", "MOOC.fi Java Programming course",                   "Build a simple OOP bank account simulator with deposit/withdraw.",            7),
    "c++":                  ("Foundation",    2, "Book",                 "Learncpp.com",                                       "Implement a linked list from scratch in C++.",                                7),
    "agile methodology":    ("Foundation",    2, "Guide",                "Atlassian Agile Coach guide",                        "Run a 2-week sprint simulation: backlog, standups, retrospective.",           3),
    "scrum methodology":    ("Foundation",    2, "Certification prep",   "Scrum Guide (scrum.org, free)",                     "Complete the Scrum Open assessment on scrum.org.",                            2),
    "object oriented programming": ("Foundation", 1, "Tutorial",        "Real Python OOP guide",                              "Model a library system with at least 3 classes and inheritance.",             4),
    "version control":      ("Foundation",    1, "Interactive guide",    "GitHub Skills (skills.github.com)",                  "Create a repo, use branches, and merge via a pull request.",                  2),
    "project management":   ("Foundation",    2, "Course",               "Google Project Management Certificate (audit)",     "Create a project plan: scope, milestones, risk register, RACI chart.",        5),
    "leadership":           ("Foundation",    2, "Reading",              "The Manager's Path (Camille Fournier)",              "Lead a group session: set an agenda, facilitate discussion, summarise.",      5),

    # ── Soft skills ────────────────────────────────────────────────────────────
    "problem solving":      ("Foundation",    1, "Practice platform",    "LeetCode easy problems",                             "Solve 10 LeetCode easy problems, write comments explaining your approach.",   7),
    "critical thinking":    ("Foundation",    2, "Reading",              "Thinking, Fast and Slow (Kahneman)",                "Analyse a recent project decision: list assumptions, evidence, alternatives.",3),
    "time management":      ("Foundation",    2, "Practice",             "Pomodoro technique guide",                           "Track your work for 3 days with a time log, identify 2 improvements.",        2),
    "team collaboration":   ("Foundation",    2, "Practice",             "Atlassian teamwork guide",                           "Contribute to an open-source issue or pair-program for 1 hour.",              3),
    # fmt: on
}

# Generic fallback for skills not in the catalog
_GENERIC: tuple[str, int, str, str, str, int] = (
    "Foundation", 2, "Documentation / tutorial",
    "Search for the official documentation or a beginner tutorial",
    "Complete one small practical exercise and publish the code to GitHub.",
    5,
)


def _build_step(skill: str) -> dict:
    """Return a single roadmap step dict for *skill*."""
    stage, priority, res_type, res_hint, exercise, est_days = _CATALOG.get(
        skill.lower(), _GENERIC
    )
    return {
        "skill": skill,
        "stage": stage,
        "priority": priority,
        "resource_type": res_type,
        "resource_hint": res_hint,
        "exercise": exercise,
        "est_days": est_days,
    }


def generate_roadmap(missing_skills: list[str]) -> dict:
    """
    Generate a full, structured learning roadmap for a list of missing skills.

    Parameters
    ----------
    missing_skills : list[str]
        Skills the candidate needs to acquire.

    Returns
    -------
    dict with keys:
        total_skills   – number of skills in the roadmap
        total_est_days – sum of estimated learning days
        stages         – dict mapping stage name → list of step dicts
        ordered_steps  – flat list sorted by priority then stage order
    """
    if not missing_skills:
        return {
            "total_skills": 0,
            "total_est_days": 0,
            "stages": {"Foundation": [], "Intermediate": [], "Advanced": []},
            "ordered_steps": [],
        }

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for s in missing_skills:
        key = s.strip().lower()
        if key and key not in seen:
            unique.append(s.strip())
            seen.add(key)

    steps = [_build_step(s) for s in unique]

    # Sort: primary by priority (1 first), secondary by stage order
    _stage_order = {"Foundation": 0, "Intermediate": 1, "Advanced": 2}
    ordered = sorted(steps, key=lambda x: (x["priority"], _stage_order.get(x["stage"], 9)))

    stages: dict[str, list] = {"Foundation": [], "Intermediate": [], "Advanced": []}
    for step in ordered:
        stages.setdefault(step["stage"], []).append(step)

    return {
        "total_skills": len(ordered),
        "total_est_days": sum(s["est_days"] for s in ordered),
        "stages": stages,
        "ordered_steps": ordered,
    }
