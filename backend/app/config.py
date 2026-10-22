"""Application configuration — typed, validated environment settings (SPEC-BE-003).

Every setting the app needs comes from this module, never from `os.environ`
directly elsewhere in the codebase. See backend/.env.example (SPEC-BE-002)
for the authoritative list of variables and what each one means.

Secret-bearing fields are typed `SecretStr` so the raw value never appears in
a repr/str of the Settings object by accident (SecretStr masks itself as
"**********"). Downstream code that needs the underlying value — e.g.
building a SQLAlchemy engine URL or an SMTP client — must call
`.get_secret_value()` explicitly at the point of use. Never call
`settings.model_dump()` for logging; log individual non-secret fields only.
"""
import json
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_APP_ENVS = {"development", "staging", "production"}
_JWT_ALGORITHMS = {"HS256", "RS256"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="forbid",
    )

    # --- App ---
    APP_NAME: str = Field(default="AI Orchestrator", description="Display name used in logs/docs/emails.")
    APP_ENV: str = Field(
        default="development", description="Deployment environment: development, staging, or production."
    )
    # SPEC-BE-071 F2: off unless asked for. In debug mode Starlette shows a
    # Python traceback instead of the JSON 500 handler.
    APP_DEBUG: bool = Field(
        default=False, description="Enables verbose errors/reload; must be false in staging/production."
    )
    APP_HOST: str = Field(default="0.0.0.0", description="Interface uvicorn binds to.")
    APP_PORT: int = Field(default=8000, description="Port uvicorn binds to.")

    # --- Security/JWT ---
    SECRET_KEY: SecretStr = Field(
        description="JWT signing key. No default — must be supplied per environment, never reused."
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="python-jose signing algorithm: HS256 or RS256.")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, description="Access token lifetime in minutes.")
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Refresh token lifetime in days.")
    BCRYPT_ROUNDS: int = Field(default=12, description="passlib/bcrypt cost factor (work factor); must be >= 10.")
    ENCRYPTION_KEY: SecretStr = Field(
        description="Symmetric key for credentials-at-rest. No default — must be supplied per environment."
    )
    TWO_FACTOR_ISSUER_NAME: str = Field(
        default="AI Orchestrator", description="Issuer label shown in TOTP authenticator apps."
    )

    # --- Database ---
    DATABASE_URL: SecretStr = Field(
        description="Async (asyncpg) database URL. No default — must be supplied per environment."
    )
    DATABASE_URL_SYNC: SecretStr = Field(
        description="Sync (psycopg2) database URL used by Alembic. No default — must be supplied per environment."
    )
    DATABASE_POOL_SIZE: int = Field(default=5, description="SQLAlchemy connection pool size.")
    DATABASE_MAX_OVERFLOW: int = Field(default=10, description="SQLAlchemy pool overflow above pool size.")

    # --- CORS ---
    # NoDecode stops pydantic-settings from trying to JSON-decode this env var
    # before our validator runs (its default behavior for list-typed fields);
    # the plain comma-separated string is parsed by parse_cors_origins below.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        description="Allowed browser origins; comma-separated in the environment, parsed into a list.",
    )

    # --- Rate Limiting ---
    RATE_LIMIT_LOGIN_ATTEMPTS: int = Field(
        default=20,
        description="FAILED logins per client IP within the window before that IP is paused "
        "(successful logins never count; SPEC-BE-039).",
    )
    RATE_LIMIT_LOGIN_WINDOW_MINUTES: int = Field(
        default=5, description="Sliding window for the per-IP failed-login count, in minutes."
    )
    LOGIN_MAX_FAILED_ATTEMPTS: int = Field(
        default=5,
        description="Consecutive wrong passwords on one account before it is briefly locked.",
    )
    LOGIN_LOCKOUT_MAX_MINUTES: int = Field(
        default=15,
        description="Cap for the escalating per-account lock (1, 2, 4, 8, ... minutes).",
    )

    # --- Multi-Tenant ---
    DEFAULT_TENANT_MAX_USERS: int = Field(
        default=10, description="Default seat cap applied to a newly provisioned tenant."
    )
    DEFAULT_TENANT_MAX_PRODUCTS: int = Field(
        default=500, description="Default catalog size cap applied to a newly provisioned tenant."
    )

    # --- Scheduler ---
    SCHEDULER_ENABLED: bool = Field(
        default=True, description="Whether the in-process APScheduler job scheduler starts with the app."
    )
    SCHEDULER_TIMEZONE: str = Field(
        default="UTC", description="Timezone the APScheduler instance evaluates job triggers in."
    )
    CRON_SECRET: SecretStr = Field(
        default=SecretStr(""),
        description="Bearer secret for GET /cron/{job_id} (Vercel Cron, where no in-process scheduler runs). "
        "Empty = the cron endpoint is off (404).",
    )

    # --- LLM/AI ---
    LLM_PROVIDER: str = Field(default="mock", description="LLM provider selector: anthropic, openai, or mock.")
    LLM_API_KEY: SecretStr = Field(
        default=SecretStr("changeme"),
        description="LLM provider API key; leave as placeholder to fall back to the mock provider.",
    )
    LLM_MODEL: str = Field(default="claude-sonnet-5", description="Model identifier passed to the provider SDK.")
    LLM_DAILY_COST_CAP_CENTS: int = Field(
        default=2000, description="Hard daily spend ceiling for LLM calls, in cents."
    )

    # Local Ollama for AI Models (SPEC-BE-088): its OpenAI-compatible base URL.
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434/v1", description="Ollama's OpenAI-compatible API on this server (no key needed)."
    )

    # --- Embeddings for AI reply retrieval (SPEC-BE-087) ---
    # One platform key for every company. "auto" recognises the provider from
    # the key (and tries LLM_API_KEY when this key is empty); "none", an empty
    # key, or a Claude/Groq key (no embeddings API) keep the full-text search
    # only. The app always boots without it.
    EMBEDDINGS_PROVIDER: Literal["auto", "none", "openai", "gemini", "voyage", "mistral", "cohere", "openai_compatible"] = Field(
        default="auto",
        description="Embedding provider: auto, none, openai, gemini, voyage, mistral, cohere or openai_compatible.",
    )
    EMBEDDINGS_API_KEY: SecretStr = Field(
        default=SecretStr(""), description="API key of the embedding provider (platform-wide)."
    )
    EMBEDDINGS_MODEL: str = Field(
        default="", description="Embedding model; empty = the provider's default (see ai/embeddings.PROVIDERS)."
    )
    EMBEDDINGS_MIN_SIMILARITY: float = Field(
        default=0.70, ge=0.0, le=1.0,
        description="Cosine a meaning-based match needs. Model-specific: 0.70 was measured for gemini-embedding-001 "
                    "(SPEC-BE-087); re-measure with evals/run_reply_eval.py --similarities for another model.",
    )
    EMBEDDINGS_BASE_URL: str = Field(
        default="", description="openai_compatible only: base URL ending before /embeddings, e.g. http://localhost:11434/v1."
    )
    EMBEDDINGS_DIMENSIONS: int = Field(
        default=768, ge=64, le=3072, description="Vector size requested from the embedding model."
    )

    # --- Meta (SPEC-BE-054) ---
    # Empty = "Connect with Facebook" is unavailable (503); the app still boots.
    META_APP_ID: str = Field(default="", description="Meta developer app ID (Facebook Login for Business).")
    META_APP_SECRET: SecretStr = Field(
        default=SecretStr(""), description="Meta app secret; used for the code exchange and appsecret_proof."
    )
    META_LOGIN_CONFIG_ID: str = Field(
        default="", description="Facebook Login for Business configuration ID (config_id)."
    )
    META_GRAPH_VERSION: str = Field(
        default="v25.0",
        description="Graph/Marketing API version; v26 breaking changes reportedly apply to all versions from 2026-10-27.",
    )

    # --- Social sign-in (SPEC-BE-080) ---
    # Empty = that platform's "Connect with ..." is unavailable (503); pasted
    # tokens still work and the app still boots.
    META_SOCIAL_LOGIN_CONFIG_ID: str = Field(
        default="",
        description="Optional Facebook Login for Business configuration (user token) for Page/Instagram sign-in; empty = scope-based dialog.",
    )
    TIKTOK_CLIENT_KEY: str = Field(default="", description="TikTok Login Kit client key (organic posting sign-in).")
    TIKTOK_CLIENT_SECRET: SecretStr = Field(default=SecretStr(""), description="TikTok Login Kit client secret.")
    LINKEDIN_CLIENT_ID: str = Field(default="", description="LinkedIn app client ID (company page sign-in).")
    LINKEDIN_CLIENT_SECRET: SecretStr = Field(default=SecretStr(""), description="LinkedIn app client secret.")

    # --- Ad platforms (SPEC-BE-064/065) ---
    GOOGLE_ADS_API_VERSION: str = Field(
        default="v25", description="Google Ads REST API version (also YouTube ads); each version sunsets about 12 months after release."
    )
    LINKEDIN_API_VERSION: str = Field(
        default="202609", description="LinkedIn Marketing API version (Linkedin-Version header, YYYYMM); versions retire after about a year."
    )

    # --- Zernio paid ads (SPEC-BE-084): one server key for every company ---
    ZERNIO_API_KEY: SecretStr = Field(
        default=SecretStr(""), description="Zernio API key (server-wide); empty = Zernio routes answer 503."
    )
    ZERNIO_BASE_URL: str = Field(default="https://zernio.com/api/v1", description="Zernio REST API base URL.")

    # --- Shopify (SPEC-BE-058) ---
    SHOPIFY_API_VERSION: str = Field(
        default="2026-07", description="Shopify Admin API version used for shipping sync."
    )

    # --- Dev-only fakes for end-to-end testing (approved 2026-10-01) ---
    # Both are refused when APP_ENV=production (validator below).
    META_FAKE_TRANSPORT: bool = Field(
        default=False,
        description="Dev only: answer Meta/Shopify/WooCommerce calls from in-process fixtures (integrations/dev_fakes.py).",
    )
    META_FAKE_CURRENCY: str = Field(default="BDT", description="Currency of the fake ad account / stores.")
    LLM_FIXTURE_FILE: str = Field(
        default="",
        description='Dev only, with LLM_PROVIDER=fixture: JSON list of {"match": "<text in the command>", "response": {...}}.',
    )

    # --- Frontend ---
    FRONTEND_BASE_URL: str = Field(
        default="http://localhost:3000",
        description="Public URL of the web app; used to build links in emails (password reset).",
    )

    # --- Email/SMTP ---
    SMTP_HOST: str = Field(default="localhost", description="SMTP server hostname.")
    SMTP_PORT: int = Field(default=587, description="SMTP server port (STARTTLS).")
    SMTP_USER: str = Field(default="changeme", description="SMTP auth username.")
    SMTP_PASSWORD: SecretStr = Field(default=SecretStr("changeme"), description="SMTP auth password.")
    SMTP_FROM_EMAIL: str = Field(
        default="no-reply@ai-orchestrator.local", description="From: address for transactional email."
    )

    # --- File Storage (media library, SPEC-BE-074) ---
    # "local" is the default: "s3" with the placeholder keys can't work.
    STORAGE_PROVIDER: str = Field(default="local", description="Object storage backend selector: local or s3.")
    STORAGE_ENDPOINT: str = Field(
        default="", description="S3-compatible endpoint, e.g. https://s3.eu-west-1.amazonaws.com or an R2/MinIO URL."
    )
    STORAGE_REGION: str = Field(default="us-east-1", description="S3 signing region.")
    MEDIA_ROOT: str = Field(default="media", description="Local storage folder (relative to backend/ or absolute).")
    MEDIA_URL_TTL_HOURS: int = Field(default=24, description="Lifetime of signed media URLs.")
    PUBLIC_BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Public address of this backend; signed media URLs use it. Instagram needs a public https address.",
    )
    STORAGE_BUCKET: str = Field(
        default="ai-orchestrator-assets", description="Bucket/container name for uploaded assets."
    )
    STORAGE_ACCESS_KEY: str = Field(default="changeme", description="Storage provider access key.")
    STORAGE_SECRET_KEY: SecretStr = Field(
        default=SecretStr("changeme"), description="Storage provider secret key."
    )

    # --- Ad/Marketing Caps ---
    AD_DAILY_SPEND_CAP_CENTS: int = Field(
        default=10000, description="Hard daily spend ceiling across ad platforms, in cents."
    )

    # --- Logging ---
    LOG_LEVEL: str = Field(default="INFO", description="Python logging level: DEBUG, INFO, WARNING, or ERROR.")
    LOG_FORMAT: str = Field(default="json", description="structlog renderer: json or console.")

    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        if v not in _APP_ENVS:
            raise ValueError(f"APP_ENV must be one of {sorted(_APP_ENVS)}, got {v!r}")
        return v

    @model_validator(mode="after")
    def no_fakes_in_production(self) -> "Settings":
        if self.APP_ENV == "production" and (self.META_FAKE_TRANSPORT or self.LLM_PROVIDER == "fixture"):
            raise ValueError("META_FAKE_TRANSPORT and LLM_PROVIDER=fixture are dev-only; refused when APP_ENV=production.")
        return self

    @model_validator(mode="after")
    def safe_production_settings(self) -> "Settings":
        """SPEC-BE-071 F4: a production server refuses to start with unsafe
        settings, naming each one (the database login is checked at startup)."""
        if self.APP_ENV != "production":
            return self
        problems = []
        if self.APP_DEBUG:
            problems.append("APP_DEBUG must be false")
        secret = self.SECRET_KEY.get_secret_value()
        if len(secret) < 32 or any(w in secret.lower() for w in ("changeme", "secret", "dev", "test", "example")):
            problems.append("SECRET_KEY must be a random value of at least 32 characters")
        bad_origins = [o for o in self.CORS_ORIGINS if not o.startswith("https://") or "localhost" in o or "127.0.0.1" in o]
        if bad_origins:
            problems.append(f"CORS_ORIGINS must be https and not localhost (got {', '.join(bad_origins)})")
        # SPEC-BE-101: the AI keys come from the Super admin screen (platform_settings),
        # so the .env LLM_PROVIDER may stay "mock"; the dev-only fixture is refused above.
        if problems:
            raise ValueError("Unsafe production settings: " + "; ".join(problems) + ".")
        return self

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def validate_jwt_algorithm(cls, v: str) -> str:
        if v not in _JWT_ALGORITHMS:
            raise ValueError(f"JWT_ALGORITHM must be one of {sorted(_JWT_ALGORITHMS)}, got {v!r}")
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v.strip().startswith("["):
                # SPEC-BE-071: a JSON list is accepted too, instead of being split into
                # broken origins like '["https://app.example.com"]'.
                return [str(origin).strip() for origin in json.loads(v) if str(origin).strip()]
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("BCRYPT_ROUNDS")
    @classmethod
    def validate_bcrypt_rounds(cls, v: int) -> int:
        if v < 10:
            raise ValueError(f"BCRYPT_ROUNDS must be >= 10, got {v}")
        return v


@lru_cache()
def get_settings() -> Settings:
    # SECRET_KEY/ENCRYPTION_KEY/DATABASE_URL/DATABASE_URL_SYNC have no default
    # (NFR-SEC-003) and are supplied by the env/.env source at runtime, not by
    # this call site — mypy's dataclass-transform view of BaseSettings can't
    # see that, hence the narrow ignore.
    return Settings()  # type: ignore[call-arg]
