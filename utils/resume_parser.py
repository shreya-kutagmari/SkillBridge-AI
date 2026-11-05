from pathlib import Path
import re

# ---------------------------------------------------------------------------
# Skill vocabulary — ordered from longest/most specific to shortest so that
# multi-word phrases are matched before their component words.
# ---------------------------------------------------------------------------
KNOWN_SKILLS = [
    # ── Multi-word phrases first (longest match wins) ───────────────────────
    "machine learning", "deep learning", "natural language processing",
    "computer vision", "data science", "data engineering", "data analysis",
    "data visualization", "big data", "embedded c", "embedded systems",
    "cloud computing", "agile methodology", "scrum methodology",
    "object oriented programming", "test driven development",
    "continuous integration", "continuous deployment", "version control",
    "problem solving", "critical thinking", "time management",
    "team collaboration", "project management",

    # ── Programming languages ────────────────────────────────────────────────
    "python", "java", "javascript", "typescript", "c++", "c#", "c",
    "kotlin", "swift", "go", "rust", "ruby", "php", "scala", "r",
    "matlab", "bash", "shell",

    # ── Web & frontend ───────────────────────────────────────────────────────
    "html", "css", "react", "angular", "vue", "next.js", "node.js",
    "express", "bootstrap", "tailwind", "sass", "webpack",

    # ── Backend & frameworks ─────────────────────────────────────────────────
    "flask", "django", "fastapi", "spring", "rails", "laravel",

    # ── Databases ────────────────────────────────────────────────────────────
    "sql", "mysql", "postgresql", "sqlite", "mongodb", "redis",
    "elasticsearch", "firebase", "cassandra",

    # ── Data & ML libraries ──────────────────────────────────────────────────
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "matplotlib", "seaborn", "plotly", "scipy", "nltk", "spacy",
    "hugging face", "langchain",

    # ── Cloud & DevOps ───────────────────────────────────────────────────────
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
    "ansible", "jenkins", "github actions", "ci/cd", "linux", "unix",

    # ── Tools & platforms ────────────────────────────────────────────────────
    "git", "github", "gitlab", "jira", "confluence", "postman",
    "excel", "powerbi", "tableau", "jupyter", "vscode", "figma",

    # ── Hardware & IoT ───────────────────────────────────────────────────────
    "iot", "arduino", "raspberry pi", "networking", "tcp/ip",

    # ── Soft / professional skills ───────────────────────────────────────────
    "communication", "leadership", "statistics",

    # ── Security ────────────────────────────────────────────────────────────
    "cybersecurity", "cryptography", "owasp",
]

# ---------------------------------------------------------------------------
# Synonym map: normalise common abbreviations / alternate spellings
# Keys are what might appear in a resume; values are canonical skill names
# that MUST also exist in KNOWN_SKILLS above.
# ---------------------------------------------------------------------------
SYNONYMS: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "ml": "machine learning",
    "dl": "deep learning",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "oop": "object oriented programming",
    "tdd": "test driven development",
    "ci": "continuous integration",
    "cd": "continuous deployment",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "sklearn": "scikit-learn",
    "tf": "tensorflow",
    "k8s": "kubernetes",
    "gke": "kubernetes",
    "hf": "hugging face",
    "rpi": "raspberry pi",
    "pbi": "powerbi",
    "power bi": "powerbi",
}


def extract_resume_text(path: str | Path) -> str:
    """Extract plain text from a PDF, DOCX, or TXT resume file."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("Install pypdf using: pip install pypdf")
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError("Install python-docx using: pip install python-docx")
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    raise RuntimeError("Unsupported file format. Use PDF, DOCX, or TXT.")


def extract_skills(text: str) -> list[str]:
    """
    Return an ordered list of recognised skills found in *text*.

    Steps:
      1. Normalise whitespace and lower-case the text.
      2. Apply synonym substitutions so abbreviations map to canonical names.
      3. Match every skill in KNOWN_SKILLS using word-boundary regex.
         Multi-word skills are checked first (list is ordered longest → shortest).
      4. Deduplicate while preserving discovery order.
    """
    if not text or not text.strip():
        return []

    normalised = re.sub(r"\s+", " ", text.lower().strip())

    # Lookbehind / lookahead: block matches *inside* longer identifiers
    # (e.g. "mygit" or "awsome") but allow trailing sentence punctuation
    # like periods and commas.  The dot is intentionally excluded from the
    # lookahead so "git." (end of sentence) is still matched.
    _LB = r"(?<![a-z0-9+#])"   # nothing alphanumeric/special immediately before
    _LA = r"(?![a-z0-9+#])"    # nothing alphanumeric/special immediately after

    # Apply synonym substitutions (whole-word only)
    for abbrev, canonical in SYNONYMS.items():
        pattern = _LB + re.escape(abbrev) + _LA
        normalised = re.sub(pattern, canonical, normalised)

    found: list[str] = []
    seen: set[str] = set()
    for skill in KNOWN_SKILLS:
        if skill in seen:
            continue
        pattern = _LB + re.escape(skill) + _LA
        if re.search(pattern, normalised):
            found.append(skill)
            seen.add(skill)

    return found
