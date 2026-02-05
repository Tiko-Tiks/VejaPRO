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
    allow_insecure_webhooks: bool = Field(
        default=False,
        validation_alias=AliasChoices("ALLOW_INSECURE_WEBHOOKS"),
    )

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_webhook_url: str = ""

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
