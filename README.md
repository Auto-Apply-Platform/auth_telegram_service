# telegram_service

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
- `TELEGRAM_WHITELIST` — список Telegram user id через запятую.
- `TELEGRAM_SERVICE_INTERNAL_TOKEN` — токен для внутреннего эндпоинта `/internal/notify`.
- `REDIS_URL` — адрес Redis для очереди и дедупликации.
- `NOTIFY_QUEUE` — очередь уведомлений (по умолчанию `queue:notifications`).
- `MANAGER_CHAT_IDS` — список chat_id менеджеров или групп через запятую (для уведомлений о мэтчах).
- `PORT` — порт сервиса.

3) Запустите:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Webhook регистрируется автоматически на старте.

## Как заполнять секреты
- `TELEGRAM_BOT_TOKEN` — возьмите у @BotFather.
- `TELEGRAM_BOT_SECRET` — сгенерируйте длинный случайный секрет (используется в `X-BOT-SECRET`).
- `TELEGRAM_SERVICE_INTERNAL_TOKEN` — внутренний токен для `/internal/notify`.
