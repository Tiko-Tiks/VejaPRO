from functools import lru_cache
import json
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
    database_url: str = ""

    DOCS_ENABLED: bool = True
    OPENAPI_ENABLED: bool = True

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
    audit_log_retention_days: int = Field(
        default=90,
        validation_alias=AliasChoices("AUDIT_LOG_RETENTION_DAYS"),
    )

    rate_limit_webhook_enabled: bool = True
    rate_limit_twilio_ip_per_min: int = 30
    rate_limit_twilio_from_per_min: int = 10
    rate_limit_stripe_ip_per_min: int = 120
    rate_limit_api_enabled: bool = False
    rate_limit_api_per_min: int = 300

    enable_marketing_module: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_MARKETING_MODULE", "ENABLE_GALLERY"),
    )
    enable_recurring_jobs: bool = False
    enable_vision_ai: bool = False
    enable_robot_adapter: bool = False
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
    docs_enabled: bool = Field(default=True)
    openapi_enabled: bool = Field(default=True)

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
    cors_allow_methods: list[str] = Field(default_factory=lambda: [
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ])
    cors_allow_headers: list[str] = Field(default_factory=lambda: [
        "Authorization",
        "Content-Type",
        "Accept",
        "Stripe-Signature",
    ])

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
