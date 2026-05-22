import re


def validate_field(field, value):

    value = value.strip()

    if value == "":
        return False, "Input cannot be empty."

    if field == "full_name":

        cleaned = " ".join(value.split())

        if len(cleaned) < 2 or len(cleaned) > 60:
            return False, "Please enter a valid name."

        if any(char.isdigit() for char in cleaned):
            return False, "Name cannot contain numbers. Please state your name again."

        if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", cleaned):
            return False, "Please use letters only for your name."

        letters_count = sum(char.isalpha() for char in cleaned)

        if letters_count < 2:
            return False, "Please enter your full name."

        invalid_single_inputs = {
            "hi",
            "hello",
            "hey",
            "yo",
            "sup",
            "test",
            "none",
            "n/a"
        }

        if cleaned.lower() in invalid_single_inputs:
            return False, "That looks like a greeting, not a name. Please state your name."

        greeting_tokens = {"hi", "hello", "hey", "yo", "sup"}
        tokens = [token.strip(" .'-") for token in cleaned.lower().split()]
        if tokens and all(token in greeting_tokens for token in tokens):
            return False, "That looks like a greeting, not a name. Please state your name."

    if field == "email":

        pattern = r"^[^@]+@[^@]+\.[^@]+$"

        if not re.match(pattern, value):
            return False, "Please enter a valid email address."

    if field == "phone_number":

        digits = value.replace(" ", "")

        if not digits.isdigit() or len(digits) != 10:
            return False, "Please enter a valid 10-digit phone number."

    return True, None
