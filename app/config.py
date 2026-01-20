from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    telegram_bot_secret: str = ""
    telegram_webhook_public_url: str = ""
    telegram_webhook_path: str = "/telegram/webhook"
    backend_base_url: str = "http://website_backend:5000"
    port: int = 8080

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @property
    def webhook_url(self) -> str:
        base = self.telegram_webhook_public_url.rstrip("/")
        path = self.telegram_webhook_path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"


settings = Settings()
