from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from gemini_helper import (
    extract_name_from_message,
    extract_profile_updates,
    generate_name_retry_reply,
    generate_chat_reply,
    get_name_prompt,
    is_end_of_chat_message,
    summarize_chat
)
from validation import validate_field
from storage import (
    delete_user_data,
    find_user_id_by_full_name,
    load_user_data,
    save_user_data
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    user_id: str
    message: str


@app.get("/health")
def health():
    return {"status": "Backend Running"}


def ensure_first_prompt(user_data):

    profile_data = user_data["profile_data"]

    if profile_data.get("full_name") is not None:
        return False

    name_prompt = get_name_prompt()
    history = user_data["conversation_history"]

    if len(history) == 0:
        history.append({
            "role": "assistant",
            "message": name_prompt
        })
        return True

    first_message = history[0]
    if first_message["role"] != "assistant" or first_message["message"].strip() != name_prompt:
        user_data["conversation_history"] = [{
            "role": "assistant",
            "message": name_prompt
        }]
        return True

    return False


def normalize_stored_name(user_data):

    stored_name = user_data["profile_data"].get("full_name")

    if stored_name is None:
        return False

    is_valid, _ = validate_field("full_name", str(stored_name))

    if is_valid:
        return False

    user_data["profile_data"]["full_name"] = None
    user_data["conversation_history"] = []
    return True


def count_user_messages(conversation_history):

    return sum(1 for item in conversation_history if item.get("role") == "user")


@app.get("/chat/start/{user_id}")
def chat_start(user_id: str):

    user_data = load_user_data(user_id)

    should_save = normalize_stored_name(user_data)

    if ensure_first_prompt(user_data):
        should_save = True

    if should_save:
        save_user_data(user_id, user_data)

    return {
        "user_id": user_id,
        "conversation_history": user_data["conversation_history"],
        "chat_summary": user_data["chat_summary"]
    }


@app.post("/chat")
def chat(request: ChatRequest):

    active_user_id = request.user_id
    user_data = load_user_data(active_user_id)
    normalize_stored_name(user_data)

    if ensure_first_prompt(user_data):

        first_prompt = get_name_prompt()
        save_user_data(active_user_id, user_data)

        return {
            "response": first_prompt,
            "user_id": active_user_id,
            "chat_summary": user_data["chat_summary"]
        }

    profile_data = user_data["profile_data"]
    incoming_message = request.message.strip()
    name_was_missing = profile_data.get("full_name") is None

    if name_was_missing:

        extracted_name = extract_name_from_message(incoming_message)

        if extracted_name == "":
            return {
                "response": generate_name_retry_reply(
                    incoming_message,
                    validation_hint="No clear name found in user message."
                ),
                "user_id": active_user_id,
                "chat_summary": user_data["chat_summary"]
            }

        is_valid, validation_message = validate_field("full_name", extracted_name)

        if not is_valid:
            return {
                "response": generate_name_retry_reply(
                    incoming_message,
                    validation_hint=validation_message or "Invalid name format."
                ),
                "user_id": active_user_id,
                "chat_summary": user_data["chat_summary"]
            }

        normalized_name = " ".join(extracted_name.split())

        existing_user_id = find_user_id_by_full_name(
            normalized_name,
            exclude_user_id=active_user_id
        )

        if existing_user_id is not None:

            old_user_id = active_user_id
            active_user_id = existing_user_id
            user_data = load_user_data(active_user_id)
            normalize_stored_name(user_data)
            profile_data = user_data["profile_data"]

            if old_user_id != active_user_id:
                delete_user_data(old_user_id)

        profile_data["full_name"] = normalized_name

    user_data["conversation_history"].append({
        "role": "user",
        "message": incoming_message
    })

    updates = extract_profile_updates(
        incoming_message,
        profile_data,
        user_data["chat_summary"]
    )

    for key, value in updates.items():
        profile_data[key] = value

    bot_response = generate_chat_reply(
        incoming_message,
        user_data["conversation_history"],
        profile_data,
        user_data["chat_summary"]
    )

    user_data["conversation_history"].append({
        "role": "assistant",
        "message": bot_response
    })

    user_message_count = count_user_messages(user_data["conversation_history"])
    should_refresh_summary = (
        user_message_count % 4 == 0 or
        is_end_of_chat_message(incoming_message)
    )

    if should_refresh_summary:
        user_data["chat_summary"] = summarize_chat(
            user_data["conversation_history"],
            profile_data
        )

    save_user_data(active_user_id, user_data)

    return {
        "response": bot_response,
        "user_id": active_user_id,
        "chat_summary": user_data["chat_summary"]
    }
