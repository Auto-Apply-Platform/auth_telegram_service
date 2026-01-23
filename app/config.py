from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    telegram_bot_secret: str = ""
    telegram_webhook_public_url: str = ""
    telegram_webhook_path: str = "/telegram/webhook"
    backend_base_url: str = "http://website_backend:5000"
    telegram_whitelist: str = ""
    telegram_service_internal_token: str
    vaccancy_collector_base_url: str
    vaccancy_collector_ingest_path: str = "/api/v1/vacancies/ingest"
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

    @property
    def public_base_url(self) -> str:
        return self.telegram_webhook_public_url.rstrip("/")

    @property
    def telegram_whitelist_set(self) -> set[int]:
        if not self.telegram_whitelist:
            return set()
        result: set[int] = set()
        for item in self.telegram_whitelist.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                result.add(int(item))
            except ValueError:
                continue
        return result


settings = Settings()
