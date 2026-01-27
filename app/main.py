from contextlib import asynccontextmanager
import contextlib
import asyncio
from datetime import datetime, timezone
import json
import logging
import uuid

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update, User
from fastapi import FastAPI, Header, HTTPException, Request
import httpx
from pydantic import BaseModel
from redis.asyncio import Redis

from app.config import settings

router = Router()
logger = logging.getLogger(__name__)
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)

QUEUE_NAME = "queue:vacancy_ingest"
DEDUP_TTL_SECONDS = 60 * 60 * 24 * 7
NOTIFY_QUEUE = settings.notify_queue


def _build_confirm_keyboard(login_token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить вход",
                    callback_data=f"confirm:{login_token}",
                )
            ]
        ]
    )


async def _confirm_login(login_token: str, user: User | None) -> str:
    payload = {
        "login_token": login_token,
        "telegram_user_id": user.id if user else None,
        "username": user.username if user else None,
        "first_name": user.first_name if user else None,
        "last_name": user.last_name if user else None,
        "allowed": user.id in settings.telegram_whitelist_set if user else False,
    }
    if payload["telegram_user_id"] is None:
        return "Не удалось определить пользователя Telegram."
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(
                f"{settings.backend_base_url}/auth/telegram/confirm",
                headers={"X-BOT-SECRET": settings.telegram_bot_secret},
                json=payload,
            )
        except httpx.RequestError:
            return "Ошибка подтверждения. Попробуйте позже."
    if response.status_code in {404, 410}:
        return "QR устарел. Обновите страницу входа."
    if response.status_code != 200:
        return "Ошибка подтверждения. Попробуйте позже."
    data = response.json()
    status = data.get("status")
    if status == "APPROVED":
        return "Вход подтверждён. Вернитесь на сайт."
    return "Доступ запрещён. Обратитесь к администратору."


@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject) -> None:
    if not command.args:
        try:
            await message.answer("Отсканируйте QR-код для входа.")
        except TelegramBadRequest as exc:
            logger.warning("telegram_answer_error chat_id=%s error=%s", message.chat.id, exc)
        return
    try:
        await message.answer(
            "Нажмите кнопку, чтобы подтвердить вход.",
            reply_markup=_build_confirm_keyboard(command.args),
        )
    except TelegramBadRequest as exc:
        logger.warning("telegram_answer_error chat_id=%s error=%s", message.chat.id, exc)


@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirm(callback: CallbackQuery) -> None:
    login_token = callback.data.split(":", 1)[1]
    reply = await _confirm_login(login_token, callback.from_user)
    await callback.answer()
    if callback.message:
        try:
            await callback.message.answer(reply)
        except TelegramBadRequest as exc:
            logger.warning("telegram_answer_error chat_id=%s error=%s", callback.message.chat.id, exc)


def _shorten_text(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[:limit - 3]}..."


def _extract_message_text(message: Message) -> str | None:
    if message.text:
        return message.text
    if message.caption:
        return message.caption
    return None


async def _enqueue_task(
    *,
    text: str,
    chat_id: int,
    message_id: int,
    user_id: int,
    username: str | None,
) -> None:
    task_id = str(uuid.uuid4())
    dedup_key = f"dedup:bot:{chat_id}:{message_id}"
    is_new = await redis_client.set(dedup_key, task_id, ex=DEDUP_TTL_SECONDS, nx=True)
    if not is_new:
        logger.info(
            "bot_duplicate user_id=%s chat_id=%s message_id=%s",
            user_id,
            chat_id,
            message_id,
        )
        return

    task = {
        "task_id": task_id,
        "source": "telegram_bot",
        "raw_text": text,
        "telegram": {
            "chat_id": chat_id,
            "message_id": message_id,
            "user_id": user_id,
            "username": username,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await redis_client.rpush(QUEUE_NAME, json.dumps(task))
    except Exception as exc:
        logger.warning(
            "queue_error user_id=%s chat_id=%s message_id=%s error=%s",
            user_id,
            chat_id,
            message_id,
            exc,
        )
        return
    logger.info(
        "queued_vacancy user_id=%s chat_id=%s message_id=%s",
        user_id,
        chat_id,
        message_id,
    )


async def _notification_loop() -> None:
    manager_ids = settings.manager_chat_ids_list
    while True:
        item = await redis_client.blpop([NOTIFY_QUEUE], timeout=5)
        if not item:
            continue
        _, raw = item
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        text = payload.get("text")
        if not text:
            continue
        if not manager_ids:
            continue
        for chat_id in manager_ids:
            try:
                await bot.send_message(chat_id, text)
            except Exception as exc:
                logger.warning("notify_manager_error chat_id=%s error=%s", chat_id, exc)


@router.message()
async def handle_incoming_message(message: Message) -> None:
    if message.text and message.text.startswith("/"):
        return
    user_id = message.from_user.id if message.from_user else None
    chat_id = message.chat.id
    message_id = message.message_id
    if user_id is None or user_id not in settings.telegram_whitelist_set:
        logger.info(
            "telegram_denied user_id=%s chat_id=%s message_id=%s",
            user_id,
            chat_id,
            message_id,
        )
        try:
            await message.answer("Доступ запрещён.")
        except TelegramBadRequest as exc:
            logger.warning("telegram_answer_error chat_id=%s error=%s", chat_id, exc)
        return
    text = _extract_message_text(message)
    if not text:
        logger.info(
            "telegram_no_text user_id=%s chat_id=%s message_id=%s",
            user_id,
            chat_id,
            message_id,
        )
        try:
            await message.answer("Не вижу текста. Пришлите текстом.")
        except TelegramBadRequest as exc:
            logger.warning("telegram_answer_error chat_id=%s error=%s", chat_id, exc)
        return
    try:
        await message.answer("Заявка принята!")
    except TelegramBadRequest as exc:
        logger.warning("telegram_answer_error chat_id=%s error=%s", chat_id, exc)
    logger.info(
        "telegram_received user_id=%s chat_id=%s message_id=%s text_preview=%s",
        user_id,
        chat_id,
        message_id,
        _shorten_text(text),
    )
    asyncio.create_task(
        _enqueue_task(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            username=message.from_user.username if message.from_user else None,
        )
    )


bot = Bot(settings.telegram_bot_token)
dp = Dispatcher()
dp.include_router(router)


@asynccontextmanager
async def lifespan(_: FastAPI):
    notify_task = asyncio.create_task(_notification_loop())
    if settings.telegram_webhook_public_url:
        await bot.set_webhook(settings.webhook_url)
    try:
        yield
    finally:
        notify_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await notify_task
        await redis_client.close()
        await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.post(settings.telegram_webhook_path)
async def telegram_webhook(request: Request) -> dict[str, str]:
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"status": "ok"}


class NotifyPayload(BaseModel):
    chat_id: int
    text: str


@app.post("/internal/notify")
async def notify_user(
    payload: NotifyPayload,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> dict[str, bool]:
    if not x_internal_token or x_internal_token != settings.telegram_service_internal_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    await bot.send_message(payload.chat_id, payload.text)
    return {"ok": True}
