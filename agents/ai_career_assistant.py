"""
agents/ai_career_assistant.py
------------------------------
AI-enhanced career assistant that tries IBM watsonx.ai first and falls
back to the rule-based career_assistant when the AI is unavailable or
times out.

Public API (same signature as career_assistant.career_reply):
    ai_career_reply(message: str, language: str = "English") -> str

Behaviour
---------
When watsonx.ai credentials are configured (WATSONX_API_KEY etc.):
  - Sends a contextualised prompt in the requested language.
  - Returns the AI-generated response.
  - If the AI call returns None (timeout, error) → falls back to rule-based.

When watsonx.ai is NOT configured:
  - Immediately falls back to the rule-based career_assistant.
  - Logs a DEBUG message (no warning spam on every request).
"""

from __future__ import annotations

import logging

from agents.ai_client import generate_text, is_available
from agents.career_assistant import career_reply as _rule_based_reply

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_EN = (
    "You are SkillBridge AI, a friendly and practical career guidance assistant "
    "for students and fresh graduates in Bengaluru, India. "
    "Provide concise, actionable advice (under 200 words). "
    "Focus on realistic steps, Bengaluru job market context, and free learning resources. "
    "Do not mention salaries beyond what is publicly known. "
    "Never claim to be a human. Never make up company names or job listings."
)

_SYSTEM_KN = (
    "ನೀವು SkillBridge AI ಆಗಿದ್ದೀರಿ — ಬೆಂಗಳೂರಿನ ವಿದ್ಯಾರ್ಥಿಗಳು ಮತ್ತು ಹೊಸ ಪದವೀಧರರಿಗಾಗಿ "
    "ಸ್ನೇಹಪರ ವೃತ್ತಿ ಮಾರ್ಗದರ್ಶಿ. "
    "200 ಪದಗಳಿಗಿಂತ ಕಡಿಮೆ ಸಂಕ್ಷಿಪ್ತ, ಕ್ರಿಯಾಶೀಲ ಸಲಹೆ ನೀಡಿ. "
    "ಬೆಂಗಳೂರು ಉದ್ಯೋಗ ಮಾರ್ಕೆಟ್ ಸಂದರ್ಭ ಮತ್ತು ಉಚಿತ ಕಲಿಕಾ ಸಂಪನ್ಮೂಲಗಳ ಮೇಲೆ ಗಮನ ಕೇಂದ್ರೀಕರಿಸಿ. "
    "ನೀವು ಮಾನವ ಎಂದು ಹೇಳಿಕೊಳ್ಳಬೇಡಿ."
)


def _build_prompt(message: str, language: str) -> str:
    """Construct a full prompt string for the career assistant."""
    is_kannada = language.lower().startswith("kannada")
    system = _SYSTEM_KN if is_kannada else _SYSTEM_EN

    if is_kannada:
        return (
            f"{system}\n\n"
            f"ಪ್ರಶ್ನೆ: {message}\n\n"
            f"ಉತ್ತರ:"
        )
    return (
        f"{system}\n\n"
        f"Question: {message}\n\n"
        f"Answer:"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ai_career_reply(message: str, language: str = "English") -> str:
    """
    Return career guidance for *message* in the requested *language*.

    Tries watsonx.ai first; falls back to the rule-based assistant if AI
    is unavailable or fails.

    Parameters
    ----------
    message  : user's question or topic (string)
    language : "English" (default) or "Kannada"

    Returns
    -------
    str  — guidance text (never None)
    """
    if not message or not message.strip():
        return _rule_based_reply("", language)

    if not is_available():
        logger.debug(
            "ai_career_reply: watsonx.ai not configured — using rule-based fallback"
        )
        return _rule_based_reply(message, language)

    prompt = _build_prompt(message.strip(), language)
    ai_text = generate_text(prompt, max_new_tokens=350)

    if ai_text and ai_text.strip():
        logger.info("ai_career_reply: AI response returned (%d chars)", len(ai_text))
        return ai_text.strip()

    # AI returned None or empty — fall back gracefully
    logger.warning(
        "ai_career_reply: AI returned empty/None response — using rule-based fallback"
    )
    return _rule_based_reply(message, language)
