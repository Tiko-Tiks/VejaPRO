import json
from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_list_value(value: str) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
        return [item.strip() for item in raw.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid",
        validate_by_name=True,
        populate_by_name=True,
    )
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    # Supabase JWT "aud" claim (commonly "authenticated"). Used to validate tokens and
    # to mint internal JWTs that behave like Supabase-issued tokens.
    supabase_jwt_audience: str = Field(
        default="authenticated",
        validation_alias=AliasChoices("SUPABASE_JWT_AUDIENCE", "JWT_AUDIENCE"),
    )
    database_url: str = ""

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    enable_manual_payments: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_MANUAL_PAYMENTS"),
    )
    enable_stripe: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_STRIPE"),
    )
    enable_twilio: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_TWILIO"),
    )
    allow_insecure_webhooks: bool = Field(
        default=False,
        validation_alias=AliasChoices("ALLOW_INSECURE_WEBHOOKS"),
    )
    expose_error_details: bool = Field(
        default=False,
        validation_alias=AliasChoices("EXPOSE_ERROR_DETAILS"),
    )

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_webhook_url: str = ""
    # Optional: exact public URL for Twilio Voice signature validation.
    # If unset, we validate against the inbound request URL (x-forwarded-* aware).
    twilio_voice_webhook_url: str = Field(
        default="",
        validation_alias=AliasChoices("TWILIO_VOICE_WEBHOOK_URL"),
    )

    pii_redaction_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("PII_REDACTION_ENABLED"),
    )
    pii_redaction_fields: list[str] = Field(
        default_factory=lambda: [
            "phone",
            "email",
            "address",
            "ssn",
            "tax_id",
            "passport",
            "national_id",
            "id_number",
        ],
        validation_alias=AliasChoices("PII_REDACTION_FIELDS"),
    )

    rate_limit_webhook_enabled: bool = True
    rate_limit_twilio_ip_per_min: int = 30
    rate_limit_twilio_from_per_min: int = 10
    rate_limit_stripe_ip_per_min: int = 120
    rate_limit_api_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("RATE_LIMIT_API_ENABLED"),
    )
    rate_limit_api_per_min: int = 300

    enable_marketing_module: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_MARKETING_MODULE", "ENABLE_GALLERY"),
    )
    enable_recurring_jobs: bool = False
    enable_notification_outbox: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_NOTIFICATION_OUTBOX"),
    )
    notification_worker_interval_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices("NOTIFICATION_WORKER_INTERVAL_SECONDS"),
    )
    notification_worker_batch_size: int = Field(
        default=50,
        validation_alias=AliasChoices("NOTIFICATION_WORKER_BATCH_SIZE"),
    )
    notification_worker_max_attempts: int = Field(
        default=5,
        validation_alias=AliasChoices("NOTIFICATION_WORKER_MAX_ATTEMPTS"),
    )
    enable_vision_ai: bool = False
    enable_finance_ledger: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_FINANCE_LEDGER"),
    )
    enable_finance_ai_ingest: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_FINANCE_AI_INGEST"),
    )
    enable_finance_auto_rules: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_FINANCE_AUTO_RULES"),
    )

    # --- AI Module ---
    enable_ai_intent: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_AI_INTENT"),
    )
    enable_ai_vision: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_AI_VISION"),
    )
    enable_ai_finance_extract: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_AI_FINANCE_EXTRACT"),
    )
    enable_ai_overrides: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_AI_OVERRIDES"),
    )
    ai_debug_store_raw: bool = Field(
        default=False,
        validation_alias=AliasChoices("AI_DEBUG_STORE_RAW"),
    )
    ai_intent_provider: str = Field(
        default="mock",
        validation_alias=AliasChoices("AI_INTENT_PROVIDER"),
    )
    ai_intent_model: str = Field(
        default="",
        validation_alias=AliasChoices("AI_INTENT_MODEL"),
    )
    ai_intent_timeout_seconds: float = Field(
        default=1.2,
        validation_alias=AliasChoices("AI_INTENT_TIMEOUT_SECONDS"),
    )
    ai_intent_budget_seconds: float = Field(
        default=2.0,
        validation_alias=AliasChoices("AI_INTENT_BUDGET_SECONDS"),
    )
    ai_intent_max_retries: int = Field(
        default=1,
        validation_alias=AliasChoices("AI_INTENT_MAX_RETRIES"),
    )
    ai_timeout_seconds: float = Field(
        default=8.0,
        validation_alias=AliasChoices("AI_TIMEOUT_SECONDS"),
    )
    ai_temperature: float = Field(
        default=0.3,
        validation_alias=AliasChoices("AI_TEMPERATURE"),
    )
    ai_max_tokens: int = Field(
        default=1024,
        validation_alias=AliasChoices("AI_MAX_TOKENS"),
    )
    ai_allowed_providers_raw: str = Field(
        default="groq,claude,openai,mock",
        validation_alias=AliasChoices("AI_ALLOWED_PROVIDERS"),
    )
    ai_allowed_models_groq_raw: str = Field(
        default="llama-3.1-70b,mixtral-8x7b-32768",
        validation_alias=AliasChoices("AI_ALLOWED_MODELS_GROQ"),
    )
    ai_allowed_models_claude_raw: str = Field(
        default="claude-3-5-haiku-20241022,claude-3-5-sonnet-20241022",
        validation_alias=AliasChoices("AI_ALLOWED_MODELS_CLAUDE"),
    )
    ai_allowed_models_openai_raw: str = Field(
        default="gpt-4o-mini-2024-07-18,gpt-4o-2024-08-06",
        validation_alias=AliasChoices("AI_ALLOWED_MODELS_OPENAI"),
    )
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY"),
    )
    groq_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GROQ_API_KEY"),
    )
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY"),
    )

    @property
    def ai_allowed_providers(self) -> list[str]:
        items = _parse_list_value(self.ai_allowed_providers_raw)
        items = [p.lower().strip() for p in items if p.strip()]
        if "mock" not in items:
            items.append("mock")
        return items

    @property
    def ai_allowed_models(self) -> dict[str, list[str]]:
        return {
            "groq": _parse_list_value(self.ai_allowed_models_groq_raw),
            "claude": _parse_list_value(self.ai_allowed_models_claude_raw),
            "openai": _parse_list_value(self.ai_allowed_models_openai_raw),
            "mock": [],
        }
    enable_call_assistant: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_CALL_ASSISTANT"),
    )
    enable_calendar: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_CALENDAR"),
    )
    enable_schedule_engine: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_SCHEDULE_ENGINE"),
    )
    # Single-operator convenience: if set, Voice assistant will schedule holds against this resource_id.
    # If unset, we try to auto-pick the earliest active ADMIN/SUBCONTRACTOR from DB.
    schedule_default_resource_id: str = Field(
        default="",
        validation_alias=AliasChoices("SCHEDULE_DEFAULT_RESOURCE_ID"),
    )
    schedule_hold_duration_minutes: int = Field(
        default=3,
        validation_alias=AliasChoices("HOLD_DURATION_MINUTES"),
    )
    schedule_hold_expiry_interval_seconds: int = Field(
        default=60,
        validation_alias=AliasChoices("SCHEDULE_HOLD_EXPIRY_INTERVAL_SECONDS"),
    )
    schedule_preview_ttl_minutes: int = Field(
        default=15,
        validation_alias=AliasChoices("SCHEDULE_PREVIEW_TTL_MINUTES"),
    )
    schedule_use_server_preview: bool = Field(
        default=True,
        validation_alias=AliasChoices("SCHEDULE_USE_SERVER_PREVIEW"),
    )
    schedule_day_namespace_uuid: str = Field(
        default="cd487f5c-baca-4d84-b0e8-97f7bfef7248",
        validation_alias=AliasChoices("SCHEDULE_DAY_NAMESPACE_UUID"),
    )
    docs_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("DOCS_ENABLED", "docs_enabled"),
    )
    openapi_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("OPENAPI_ENABLED", "openapi_enabled"),
    )

    security_headers_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("SECURITY_HEADERS_ENABLED", "SECURE_HEADERS_ENABLED"),
    )

    admin_ip_allowlist_raw: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_IP_ALLOWLIST"),
    )
    admin_token_endpoint_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("ADMIN_TOKEN_ENDPOINT_ENABLED"),
    )
    admin_token_ttl_hours: int = Field(
        default=12,
        validation_alias=AliasChoices("ADMIN_TOKEN_TTL_HOURS"),
    )
    admin_token_sub: str = Field(
        default="00000000-0000-0000-0000-000000000001",
        validation_alias=AliasChoices("ADMIN_TOKEN_SUB"),
    )
    admin_token_email: str = Field(
        default="admin@test.local",
        validation_alias=AliasChoices("ADMIN_TOKEN_EMAIL"),
    )
    client_token_ttl_hours: int = Field(
        default=168,
        validation_alias=AliasChoices("CLIENT_TOKEN_TTL_HOURS"),
    )

    cors_allow_origins: list[str] = Field(default_factory=list)
    cors_allow_methods: list[str] = Field(
        default_factory=lambda: [
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ]
    )
    cors_allow_headers: list[str] = Field(
        default_factory=lambda: [
            "Authorization",
            "Content-Type",
            "Accept",
            "Stripe-Signature",
        ]
    )

    @field_validator(
        "cors_allow_origins",
        "cors_allow_methods",
        "cors_allow_headers",
        "pii_redaction_fields",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            if value.strip() == "":
                return []
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def admin_ip_allowlist(self) -> list[str]:
        return _parse_list_value(self.admin_ip_allowlist_raw)


@lru_cache
def get_settings() -> Settings:
    return Settings()
