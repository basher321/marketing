"""Content moderation prompts."""

MODERATOR_SYSTEM_PROMPT = """Review the given text for policy violations (hate speech, scams,
illegal content, PII leakage). Respond with 'SAFE' or 'UNSAFE: <reason>'."""
