from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    database_url: str = ""

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    rate_limit_webhook_enabled: bool = True
    rate_limit_twilio_ip_per_min: int = 30
    rate_limit_twilio_from_per_min: int = 10
    rate_limit_stripe_ip_per_min: int = 120

    enable_vision_ai: bool = False
    enable_robot_adapter: bool = False
    enable_gallery: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache

def get_settings() -> Settings:
    return Settings()
