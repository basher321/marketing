"""Password strength validation (SPEC-BE-071 F11).

At least 10 characters with an uppercase letter, a lowercase letter and a
digit; not one of the most common passwords, nor a common word followed only
by digits and symbols; and not containing the account's email name. Existing
passwords keep working (only new passwords are checked).
"""
import re

MIN_LENGTH = 10

# Lower-cased; checked as exact matches (also after stripping trailing symbols).
COMMON_PASSWORDS = frozenset({
    "password", "password1", "password12", "password123", "password1234", "passw0rd", "passw0rd1", "p@ssw0rd", "p@ssword1",
    "qwerty123", "qwertyuiop", "qwerty1234", "1q2w3e4r5t", "1qaz2wsx3edc", "abc123456", "abcd1234", "admin123", "admin1234",
    "administrator1", "welcome1", "welcome123", "welcome2024", "welcome2025", "welcome2026", "letmein123", "iloveyou1",
    "monkey1234", "dragon1234", "football1", "baseball1", "sunshine1", "princess1", "trustno1", "changeme1", "changeme123",
    "secret123", "summer2024", "summer2025", "summer2026", "winter2024", "winter2025", "winter2026", "spring2026", "autumn2026",
    "company123", "marketing1", "bangladesh1", "dhaka12345", "test123456", "testtest1", "user123456",
})
# Common base words: a password that is one of these followed only by digits and symbols
# ("Passw0rd123", "Welcome2027!") is refused as well.
COMMON_BASES = frozenset({
    "password", "passw0rd", "p@ssw0rd", "p@ssword", "qwerty", "qwertyuiop", "welcome", "admin", "administrator",
    "letmein", "iloveyou", "changeme", "secret", "monkey", "dragon", "football", "baseball", "sunshine", "princess",
    "summer", "winter", "spring", "autumn", "company", "marketing", "bangladesh", "dhaka", "test", "user", "abcdef",
})


def validate_password_strength(password: str, email: str | None = None) -> list[str]:
    errors = []
    if len(password) < MIN_LENGTH:
        errors.append(f"Password must be at least {MIN_LENGTH} characters.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain an uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain a lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain a digit.")
    lowered = password.lower()
    base = re.sub(r"[\d\W_]+$", "", lowered)
    if lowered in COMMON_PASSWORDS or lowered.rstrip("!@#$%^&*.?") in COMMON_PASSWORDS or base in COMMON_BASES:
        errors.append("This password is too common; choose another.")
    local = (email or "").split("@", 1)[0].lower()
    if len(local) >= 4 and local in password.lower():
        errors.append("The password must not contain your email name.")
    return errors
