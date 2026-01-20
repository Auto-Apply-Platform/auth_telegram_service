# auth_telegram_service

Telegram бот авторизации через webhook.

## Запуск

1) Скопируйте окружение:

```bash
cp .env.example .env
```

2) Заполните `.env`:

- `TELEGRAM_BOT_TOKEN` — токен Telegram-бота.
- `TELEGRAM_BOT_SECRET` — секрет для заголовка `X-BOT-SECRET`.
- `TELEGRAM_WEBHOOK_PUBLIC_URL` — публичный HTTPS base url.
- `TELEGRAM_WEBHOOK_PATH` — путь webhook (по умолчанию `/telegram/webhook`).
- `BACKEND_BASE_URL` — адрес `website_backend` внутри сети docker.
- `PORT` — порт сервиса.

3) Запустите:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Webhook регистрируется автоматически на старте.
