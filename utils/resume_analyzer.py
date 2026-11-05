"""
Rule-based resume analysis for SkillBridge AI.

This module analyses extracted resume text. It does not modify the
original resume parser or make hiring/shortlisting predictions.
"""

import re


SECTION_PATTERNS = {
    "contact": [
        r"\bcontact\b",
        r"\bemail\b",
        r"\bphone\b",
    ],
    "summary": [
        r"\bprofessional summary\b",
        r"\bcareer summary\b",
        r"\bprofile summary\b",
        r"\bobjective\b",
        r"\bprofessional profile\b",
        r"\babout me\b",
    ],
    "education": [
        r"\beducation\b",
        r"\bacademic background\b",
        r"\bqualifications\b",
    ],
    "experience": [
        r"\bwork experience\b",
        r"\bprofessional experience\b",
        r"\bemployment history\b",
        r"\binternship experience\b",
        r"\binternships\b",
    ],
    "projects": [
        r"\bprojects\b",
        r"\bacademic projects\b",
        r"\bpersonal projects\b",
        r"\bproject experience\b",
    ],
    "skills": [
        r"\btechnical skills\b",
        r"\bcore skills\b",
        r"\bskills\b",
        r"\btechnologies\b",
    ],
    "certifications": [
        r"\bcertifications\b",
        r"\bcertificates\b",
        r"\blicenses\b",
    ],
}


SCORE_WEIGHTS = {
    "contact": 10,
    "summary": 15,
    "education": 15,
    "experience": 15,
    "projects": 15,
    "skills": 20,
    "certifications": 10,
}


ACTION_VERBS = {
    "built", "developed", "designed", "created", "implemented",
    "managed", "improved", "automated", "analysed", "analyzed",
    "tested", "deployed", "integrated", "led", "configured",
    "programmed", "delivered", "optimised", "optimized",
}


METRIC_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|percent|users|projects|hours|days|"
    r"months|years|records|customers|clients)\b",
    re.IGNORECASE,
)


EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?"
    r"(?:\d[-.\s]?){9,12}(?!\d)"
)


def _normalise_text(text):
    """Return safe, normalised text for analysis."""
    if not isinstance(text, str):
        return ""
    return text.strip()


def _has_heading(text, patterns):
    """Check whether a section heading appears in the resume."""
    lines = [line.strip().lower() for line in text.splitlines() if line.strip()]

    for line in lines:
        cleaned = re.sub(r"^[\s#•\-*]+", "", line)
        cleaned = re.sub(r"[:\-]+$", "", cleaned).strip()

        for pattern in patterns:
            if re.fullmatch(pattern, cleaned, flags=re.IGNORECASE):
                return True

    return False


def _has_contact_details(text):
    """Check for an email address or a likely phone number."""
    return bool(EMAIL_PATTERN.search(text) or PHONE_PATTERN.search(text))


def _count_project_entries(text):
    """Estimate the number of non-empty lines in a Projects section."""
    lines = text.splitlines()
    in_projects = False
    count = 0

    next_sections = [
        pattern
        for name, patterns in SECTION_PATTERNS.items()
        if name != "projects"
        for pattern in patterns
    ]

    for line in lines:
        cleaned = line.strip().lower()
        heading = re.sub(r"^[\s#•\-*]+", "", cleaned)
        heading = re.sub(r"[:\-]+$", "", heading).strip()

        if any(
            re.fullmatch(pattern, heading, flags=re.IGNORECASE)
            for pattern in SECTION_PATTERNS["projects"]
        ):
            in_projects = True
            continue

        if in_projects and any(
            re.fullmatch(pattern, heading, flags=re.IGNORECASE)
            for pattern in next_sections
        ):
            break

        if in_projects and line.strip():
            count += 1

    return count


def analyze_resume(text):
    """
    Analyse resume structure and content.

    Returns a dictionary containing:
    - score: indicative score out of 100
    - score_breakdown: points earned per category
    - detected_sections: sections identified
    - missing_sections: recommended sections to add
    - suggestions: actionable improvement suggestions
    - project_entry_count: approximate non-empty project lines
    """
    text = _normalise_text(text)

    if not text:
        return {
            "score": 0,
            "score_breakdown": {
                key: {"earned": 0, "maximum": weight}
                for key, weight in SCORE_WEIGHTS.items()
            },
            "detected_sections": [],
            "missing_sections": list(SCORE_WEIGHTS.keys()),
            "skills": [],
            "project_entry_count": 0,
            "suggestions": [
                "Upload a resume containing readable text to receive an analysis."
            ],
            "disclaimer": (
                "This is a rule-based estimate, not an official ATS score."
            ),
        }

    detected = []

    for section, patterns in SECTION_PATTERNS.items():
        if section == "contact":
            if _has_contact_details(text):
                detected.append(section)
        elif _has_heading(text, patterns):
            detected.append(section)

    # Import the existing extractor instead of duplicating skill logic.
    from utils.resume_parser import extract_skills

    skills = extract_skills(text)

    project_entries = _count_project_entries(text)

    breakdown = {}
    score = 0

    for section, maximum in SCORE_WEIGHTS.items():
        earned = maximum if section in detected else 0

        # Give partial project credit when a Projects heading exists
        # but the section appears to contain very little content.
        if section == "projects" and section in detected:
            if project_entries <= 1:
                earned = maximum // 2

        breakdown[section] = {
            "earned": earned,
            "maximum": maximum,
        }
        score += earned

    suggestions = []

    if "contact" not in detected:
        suggestions.append(
            "Add a professional email address or phone number in your contact section."
        )

    if "summary" not in detected:
        suggestions.append(
            "Add a short professional summary tailored to your target role."
        )

    if "education" not in detected:
        suggestions.append(
            "Add an Education section with your degree, institution, and graduation year."
        )

    if "experience" not in detected:
        suggestions.append(
            "If you have internships, volunteering, or work experience, add an Experience section. "
            "If you are a fresher, highlight relevant academic work instead."
        )

    if "projects" not in detected:
        suggestions.append(
            "Add a Projects section describing relevant academic or personal projects."
        )
    elif project_entries <= 1:
        suggestions.append(
            "Expand your project descriptions with the problem, technologies used, "
            "your contribution, and outcome."
        )

    if "skills" not in detected:
        suggestions.append(
            "Add a clearly labelled Skills section with relevant technical skills."
        )
    elif not skills:
        suggestions.append(
            "List specific technical skills and tools rather than only broad skill descriptions."
        )

    if "certifications" not in detected:
        suggestions.append(
            "Add relevant certifications or completed technical courses, if available."
        )

    if not ACTION_VERBS.intersection(set(re.findall(
        r"\b[a-zA-Z]+\b", text.lower()
    ))):
        suggestions.append(
            "Use action verbs such as Developed, Designed, Implemented, and Tested "
            "to describe your contributions."
        )

    if not METRIC_PATTERN.search(text):
        suggestions.append(
            "Where accurate, include measurable results such as time saved, "
            "users supported, or project performance."
        )

    if len(skills) < 5:
        suggestions.append(
            "Include additional relevant technical skills that you can genuinely demonstrate."
        )

    missing = [
        section
        for section in SCORE_WEIGHTS
        if section not in detected
    ]

    return {
        "score": score,
        "score_breakdown": breakdown,
        "detected_sections": detected,
        "missing_sections": missing,
        "skills": skills,
        "project_entry_count": project_entries,
        "suggestions": suggestions,
        "disclaimer": (
            "This is a rule-based resume structure and content estimate, "
            "not an official ATS score or a prediction of hiring outcomes."
        ),
    }