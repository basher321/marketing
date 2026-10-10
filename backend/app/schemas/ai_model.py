"""AI model (LLM provider) settings schemas (SPEC-BE-053)."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ProviderName = Literal["anthropic", "openai", "gemini", "groq", "openrouter", "ollama"]


class AIModelProvider(BaseModel):
    provider: str
    label: str
    enabled: bool
    # Null until the company chooses one: there is no built-in default
    # (SPEC-BE-053 amendment 2026-10-02).
    model: str | None
    image_model: str | None
    has_images: bool
    # Video generation (SPEC-BE-077): OpenAI (Sora) and Gemini (Veo) only.
    video_model: str | None = None
    has_video: bool = False
    priority: int
    # "••••" + last 4 characters, or null when no key is saved. Never the key.
    key_masked: str | None
    last_error: str | None
    last_ok_at: datetime | None
    docs_url: str
    # False for a local provider that takes no key (Ollama, SPEC-BE-088).
    needs_key: bool = True


class EnvFallback(BaseModel):
    provider: str
    configured: bool


class AIModelList(BaseModel):
    providers: list[AIModelProvider]
    env_fallback: EnvFallback


class AIModelUpdate(BaseModel):
    """Only the fields sent are changed; an empty api_key keeps the saved key."""

    api_key: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    # Empty string clears it (OpenAI and Gemini only).
    image_model: str | None = Field(default=None, max_length=120)
    # Empty string clears it (OpenAI and Gemini only, SPEC-BE-077).
    video_model: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None


class AIModelOrder(BaseModel):
    order: list[ProviderName] = Field(min_length=1, max_length=6)


class AIModelTestResult(BaseModel):
    ok: bool
    latency_ms: int
    model: str
    error: str | None
    # On a 404 (retired model): what the key can use now, best first.
    suggested: str | None = None
    suggestions: list[str] = []


class ModelOption(BaseModel):
    id: str
    label: str


class SuggestedModels(BaseModel):
    chat: str | None
    image: str | None


class ProviderModels(BaseModel):
    """The provider's live list for the saved key (SPEC-BE-053 amendment)."""

    ok: bool
    error: str | None
    chat: list[ModelOption]
    image: list[ModelOption]
    video: list[ModelOption] = []
    suggested: SuggestedModels



# --- Creative providers (SPEC-BE-070) -----------------------------------------
CreativeKind = Literal["plan", "copy", "review", "image", "video"]
MCP_ID = r"^[a-z0-9][a-z0-9_-]{1,39}$"


class CreativeOrder(BaseModel):
    """Provider keys in try-order per kind: "llm", "openai_image",
    "gemini_image" or "mcp:<id>"."""

    order: dict[CreativeKind, list[str]] = Field(default_factory=dict)


class MCPToolRead(BaseModel):
    id: str
    name: str
    url: str
    enabled: bool
    token_masked: str | None
    tools: dict[str, str]
    arguments: dict[str, Any]
    cost_cents_per_call: int
    last_error: str | None = None
    last_ok_at: str | None = None


class CreativeSettings(BaseModel):
    order: dict[str, list[str]]
    available: dict[str, list[dict[str, Any]]]
    mcp_tools: list[MCPToolRead]


class MCPToolSave(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=9, max_length=500)
    token: str | None = Field(default=None, max_length=2000)  # empty keeps the saved token
    enabled: bool = True
    tools: dict[CreativeKind, str] = Field(default_factory=dict)
    arguments: dict[CreativeKind, dict[str, Any]] = Field(default_factory=dict)
    cost_cents_per_call: int = Field(default=0, ge=0, le=10000)

    @field_validator("url")
    @classmethod
    def https_only(cls, value: str) -> str:
        if not value.strip().startswith("https://"):
            raise ValueError("The MCP server URL must start with https://.")
        return value.strip()

    @field_validator("tools")
    @classmethod
    def tool_names(cls, value: dict[str, str]) -> dict[str, str]:
        return {k: v.strip() for k, v in value.items() if v and v.strip()}


class MCPToolTest(BaseModel):
    ok: bool
    message: str
    tools_found: list[str]


# Sound for AI slideshow videos (SPEC-BE-094). OpenAI text-to-speech voices.
TTSVoice = Literal["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"]


class VideoAudioSave(BaseModel):
    voiceover: bool = True
    voice: TTSVoice = "alloy"
    music_media_id: str | None = Field(default=None, max_length=36)
    music_volume: float = Field(default=0.25, ge=0.05, le=1.0)


class VideoAudioSettings(VideoAudioSave):
    # The chosen track (media item with a signed URL), or None.
    music: dict[str, Any] | None = None
