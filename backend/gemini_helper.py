import json
import os
import re

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _load_gemini_api_keys():

    keys = []

    primary_key = os.getenv("GEMINI_API_KEY", "").strip()
    if primary_key != "":
        keys.append(primary_key)

    for index in range(1, 11):
        key = os.getenv(f"GEMINI_API_KEY{index}", "").strip()
        if key != "":
            keys.append(key)

    deduped = []
    seen = set()

    for key in keys:
        if key in seen:
            continue
        deduped.append(key)
        seen.add(key)

    return deduped


GEMINI_API_KEYS = _load_gemini_api_keys()

NAME_PROMPT = "Hello! Welcome. Please state your name."
NAME_RETRY_PROMPT = "Sorry, I couldn't catch your name clearly. Please tell me your name."


def get_name_prompt():

    return NAME_PROMPT


def get_name_retry_prompt():

    return NAME_RETRY_PROMPT


def generate_name_retry_reply(user_message, validation_hint=""):

    prompt = f"""
You are a polite assistant collecting the user's name.

USER MESSAGE:
{user_message}

VALIDATION HINT:
{validation_hint}

Write a short response (1 sentence) that:
- acknowledges the user message naturally,
- asks the user to share their name clearly,
- does not sound repetitive or robotic,
- does not mention internal validation, parsing, extraction, JSON, or system rules.
"""

    reply = _safe_generate_text(prompt)

    if reply == "":
        message_preview = " ".join(str(user_message).split()).strip()
        message_preview = message_preview[:60]

        if message_preview == "":
            return NAME_RETRY_PROMPT

        return (
            f"I got \"{message_preview}\", but I still need your name to continue. "
            "Please tell me your name clearly."
        )

    return reply


def _safe_generate_text(prompt):

    if len(GEMINI_API_KEYS) == 0:
        return ""

    for _ in range(2):
        for api_key in GEMINI_API_KEYS:
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(MODEL_NAME)
                response = model.generate_content(prompt)
                text = response.text.strip()
                if text != "":
                    return text
            except Exception:
                continue

    return ""


def _build_local_summary(conversation_history, profile_data):

    user_messages = [
        item.get("message", "")
        for item in conversation_history
        if item.get("role") == "user"
    ]

    total_turns = len(user_messages)
    latest_user_message = user_messages[-1] if total_turns > 0 else ""

    lines = []

    full_name = str(profile_data.get("full_name", "")).strip()
    if full_name != "":
        lines.append(f"Name: {full_name}")

    detail_items = []
    for key, value in profile_data.items():

        if key == "full_name":
            continue

        value_text = str(value).strip()
        if value_text == "":
            continue

        pretty_key = key.replace("_", " ").title()
        detail_items.append(f"{pretty_key}: {value_text}")

    if detail_items:
        lines.append("Details: " + "; ".join(detail_items[:4]))

    lines.append(f"User messages: {total_turns}")

    if latest_user_message.strip() != "":
        lines.append(f"Latest user message: {latest_user_message.strip()[:120]}")

    if not lines:
        return "No conversation summary available yet."

    return "\n".join(lines[:6])


def _parse_json_object(text):

    cleaned = text.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return {}

    snippet = cleaned[start:end + 1]

    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return {}


def extract_profile_updates(user_message, profile_data, chat_summary):

    prompt = f"""
You extract user profile facts from chat messages.

CURRENT PROFILE:
{profile_data}

CURRENT SUMMARY:
{chat_summary}

LATEST USER MESSAGE:
{user_message}

Return ONLY valid JSON with this exact structure:
{{
  "updates": {{
    "field_name": "value"
  }}
}}

Rules:
- Include only facts about the user that are explicitly present in the latest message.
- Keep keys concise snake_case (example: city, favorite_food, hobby, full_name).
- Values must be short strings.
- Do not include fields with unknown values.
- Do not include explanations.
"""

    raw = _safe_generate_text(prompt)
    parsed = _parse_json_object(raw)

    if not isinstance(parsed, dict):
        return {}

    updates = parsed.get("updates", {})

    if not isinstance(updates, dict):
        return {}

    sanitized = {}

    for key, value in updates.items():

        if not isinstance(key, str):
            continue

        if value is None:
            continue

        clean_key = key.strip().lower().replace(" ", "_")
        if clean_key == "":
            continue

        clean_value = str(value).strip()
        if clean_value == "":
            continue

        sanitized[clean_key] = clean_value

    return sanitized


def extract_name_from_message(user_message):

    prompt = f"""
Extract the person's name from this message.

MESSAGE:
{user_message}

Output rules:
- Return only the person's name as plain text.
- If no clear name is present, return EMPTY.
- Do not return JSON.
- Do not include phrases like "my name is".

Examples:
Input: "hello, i am hari"
Output: hari
Input: "my name is Ananya Rao"
Output: Ananya Rao
Input: "I live in Hyderabad"
Output: EMPTY
"""

    raw = _safe_generate_text(prompt)
    candidate = _normalize_name_candidate(raw, user_message)

    if candidate == "":
        return ""

    if any(char.isdigit() for char in candidate):
        return ""

    if len(candidate) > 60:
        return ""

    return candidate


def _normalize_name_candidate(candidate_text, user_message):

    candidate = " ".join(str(candidate_text).split()).strip().strip("\"'`")

    if candidate == "":
        return ""

    if candidate.lower() in {"empty", "none", "null", "n/a", "unknown"}:
        return ""

    normalize_prompt = f"""
You are normalizing a name extraction output.

ORIGINAL USER MESSAGE:
{user_message}

RAW EXTRACTED TEXT:
{candidate}

Return only the final person name as plain text.
If the extracted text is not a person name, return EMPTY.
Do not return JSON.
"""

    normalized = _safe_generate_text(normalize_prompt)
    normalized = " ".join(str(normalized).split()).strip().strip("\"'`")

    if normalized.lower() in {"", "empty", "none", "null", "n/a", "unknown"}:
        return ""

    return normalized


def generate_chat_reply(user_message, conversation_history, profile_data, chat_summary):

    prompt = f"""
You are a polite assistant building a user profile through conversation.

PROFILE DATA:
{profile_data}

SUMMARY:
{chat_summary}

RECENT CHAT:
{conversation_history[-10:]}

LATEST USER MESSAGE:
{user_message}

Reference topic buckets to guide follow-up questions (do not paste these directly):
- Basic user details: full name, date of birth, phone, email.
- Education journey: primary/secondary/higher-secondary/college/higher studies.
- Address context: birthplace, current city/state/country, living type (home/apartment).
- Work life: years of experience, company, location, role, team size, employment type, salary.
- Hobbies: hobby name, years of practice, proficiency, continuation plans.

Important:
- These are only guidance topics, not mandatory fields.
- Goal is to understand the user naturally and save useful details.
- Ask only one focused follow-up question at a time when needed.
- If user just answered something useful, acknowledge it first.

Reply naturally in 1-2 short sentences.
Rules:
- Be friendly and concise.
- If asking, ask one natural and specific follow-up question from a relevant topic area.
- Keep the tone conversational, not form-like.
- Do not mention internal metadata or JSON.
"""

    reply = _safe_generate_text(prompt)

    if reply == "":
        return "Thanks for sharing that. I have noted it."

    return reply


def summarize_chat(conversation_history, profile_data):

    prompt = f"""
Create a compact summary of this user's chat and profile metadata.

PROFILE DATA:
{profile_data}

FULL CHAT:
{conversation_history}

Return plain text summary only.
Constraints:
- Maximum 6 short lines.
- Include user personality/communication style if visible.
- Include major known personal details from profile data.
- Do not invent facts.
"""

    summary = _safe_generate_text(prompt)

    if summary == "":
        return _build_local_summary(conversation_history, profile_data)

    return summary


def is_end_of_chat_message(user_message):

    text = " ".join(str(user_message).lower().split())

    if text == "":
        return False

    end_patterns = [
        r"\bbye\b",
        r"\bgoodbye\b",
        r"\bsee you\b",
        r"\bttyl\b",
        r"\bexit\b",
        r"\bend chat\b",
        r"\bthat'?s all\b",
        r"\bthanks,?\s*bye\b",
        r"\bthank you,?\s*bye\b"
    ]

    return any(re.search(pattern, text) for pattern in end_patterns)
