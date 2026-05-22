from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

try:
    from supabase import Client, create_client
except Exception:
    Client = None
    create_client = None

DATA_FOLDER = os.getenv("DATA_FOLDER", "data")
SESSION_STORAGE = os.getenv("SESSION_STORAGE", "auto").strip().lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.getenv("SUPABASE_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "chat_sessions").strip() or "chat_sessions"


def _is_supabase_enabled() -> bool:

    if SESSION_STORAGE == "local":
        return False

    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    return create_client is not None


def _get_supabase_client() -> Client | None:

    if not _is_supabase_enabled():
        return None

    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


def get_user_file(user_id):

    return f"{DATA_FOLDER}/{user_id}.json"


def normalize_name(name):

    if name is None:
        return None

    return " ".join(str(name).split()).strip().lower()


def _ensure_user_shape(user_data):

    if "profile_data" not in user_data or not isinstance(user_data["profile_data"], dict):
        user_data["profile_data"] = {}

    if "chat_summary" not in user_data or not isinstance(user_data["chat_summary"], str):
        user_data["chat_summary"] = ""

    if "conversation_history" not in user_data or not isinstance(user_data["conversation_history"], list):
        user_data["conversation_history"] = []

    if "kyc_data" in user_data and isinstance(user_data["kyc_data"], dict):

        for key, value in user_data["kyc_data"].items():

            if value is None:
                continue

            if key not in user_data["profile_data"] or user_data["profile_data"][key] in (None, ""):
                user_data["profile_data"][key] = value

    if "kyc_data" in user_data:
        user_data.pop("kyc_data", None)

    return user_data


def _new_user(user_id: str) -> Dict[str, Any]:

    now = str(datetime.now())
    return {
        "user_id": user_id,
        "created_at": now,
        "updated_at": now,
        "profile_data": {},
        "chat_summary": "",
        "conversation_history": [],
    }


def _load_user_data_local(user_id):

    file_path = get_user_file(user_id)

    if os.path.exists(file_path):

        with open(file_path, "r") as file:
            data = json.load(file)

        data = _ensure_user_shape(data)
        return data

    new_user = _new_user(user_id)
    _save_user_data_local(user_id, new_user)
    return new_user


def _save_user_data_local(user_id, data):

    data = _ensure_user_shape(data)
    data["updated_at"] = str(datetime.now())
    data["user_id"] = user_id

    file_path = get_user_file(user_id)
    os.makedirs(DATA_FOLDER, exist_ok=True)

    with open(file_path, "w") as file:
        json.dump(data, file, indent=4)


def _delete_user_data_local(user_id):

    file_path = get_user_file(user_id)

    if os.path.exists(file_path):
        os.remove(file_path)


def _find_user_id_by_full_name_local(full_name, exclude_user_id=None):

    target_name = normalize_name(full_name)

    if not target_name:
        return None

    if not os.path.exists(DATA_FOLDER):
        return None

    for file_name in os.listdir(DATA_FOLDER):

        if not file_name.endswith(".json"):
            continue

        user_id = file_name[:-5]

        if exclude_user_id is not None and user_id == exclude_user_id:
            continue

        file_path = get_user_file(user_id)

        try:
            with open(file_path, "r") as file:
                user_data = json.load(file)
        except (json.JSONDecodeError, OSError):
            continue

        user_data = _ensure_user_shape(user_data)

        existing_name = user_data.get("profile_data", {}).get("full_name")

        if normalize_name(existing_name) == target_name:
            return user_id

    return None


def _load_user_data_supabase(user_id, client: Client):

    response = (
        client.table(SUPABASE_TABLE)
        .select("data")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if len(rows) > 0 and isinstance(rows[0], dict):
        data = rows[0].get("data")
        if isinstance(data, dict):
            return _ensure_user_shape(data)

    new_user = _new_user(user_id)
    _save_user_data_supabase(user_id, new_user, client)
    return new_user


def _save_user_data_supabase(user_id, data, client: Client):

    data = _ensure_user_shape(data)
    data["updated_at"] = str(datetime.now())
    data["user_id"] = user_id

    (
        client.table(SUPABASE_TABLE)
        .upsert(
            {
                "user_id": user_id,
                "data": data,
            },
            on_conflict="user_id",
        )
        .execute()
    )


def _delete_user_data_supabase(user_id, client: Client):

    client.table(SUPABASE_TABLE).delete().eq("user_id", user_id).execute()


def _all_supabase_rows(client: Client) -> List[Dict[str, Any]]:

    rows: List[Dict[str, Any]] = []
    page_size = 500
    start = 0

    while True:
        end = start + page_size - 1
        response = (
            client.table(SUPABASE_TABLE)
            .select("user_id,data")
            .range(start, end)
            .execute()
        )

        chunk = response.data or []

        if not chunk:
            break

        rows.extend(chunk)

        if len(chunk) < page_size:
            break

        start += page_size

    return rows


def _find_user_id_by_full_name_supabase(full_name, exclude_user_id, client: Client):

    target_name = normalize_name(full_name)

    if not target_name:
        return None

    for row in _all_supabase_rows(client):

        if not isinstance(row, dict):
            continue

        user_id = row.get("user_id")

        if not isinstance(user_id, str):
            continue

        if exclude_user_id is not None and user_id == exclude_user_id:
            continue

        data = row.get("data")
        if not isinstance(data, dict):
            continue

        user_data = _ensure_user_shape(data)
        existing_name = user_data.get("profile_data", {}).get("full_name")

        if normalize_name(existing_name) == target_name:
            return user_id

    return None


def load_user_data(user_id):

    client = _get_supabase_client()

    if client is None:
        return _load_user_data_local(user_id)

    try:
        return _load_user_data_supabase(user_id, client)
    except Exception:
        return _load_user_data_local(user_id)


def save_user_data(user_id, data):

    client = _get_supabase_client()

    if client is None:
        _save_user_data_local(user_id, data)
        return

    try:
        _save_user_data_supabase(user_id, data, client)
    except Exception:
        _save_user_data_local(user_id, data)


def delete_user_data(user_id):

    client = _get_supabase_client()

    if client is None:
        _delete_user_data_local(user_id)
        return

    try:
        _delete_user_data_supabase(user_id, client)
    except Exception:
        _delete_user_data_local(user_id)


def find_user_id_by_full_name(full_name, exclude_user_id=None):

    client = _get_supabase_client()

    if client is None:
        return _find_user_id_by_full_name_local(full_name, exclude_user_id)

    try:
        return _find_user_id_by_full_name_supabase(full_name, exclude_user_id, client)
    except Exception:
        return _find_user_id_by_full_name_local(full_name, exclude_user_id)
