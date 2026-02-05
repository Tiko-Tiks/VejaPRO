from functools import lru_cache
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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


    rate_limit_webhook_enabled: bool = True
    rate_limit_twilio_ip_per_min: int = 30
    rate_limit_twilio_from_per_min: int = 10
    rate_limit_stripe_ip_per_min: int = 120

    enable_marketing_module: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_MARKETING_MODULE", "ENABLE_GALLERY"),
    )
    enable_recurring_jobs: bool = False
    enable_vision_ai: bool = False
    enable_robot_adapter: bool = False
    docs_enabled: bool = Field(default=True)
    openapi_enabled: bool = Field(default=True)

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

    @field_validator("cors_allow_origins", "cors_allow_methods", "cors_allow_headers", mode="before")
    @classmethod
    def _split_csv(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            if value.strip() == "":
                return []
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

@lru_cache

def get_settings() -> Settings:
    return Settings()
