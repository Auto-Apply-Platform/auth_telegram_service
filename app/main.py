from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update, User
from fastapi import FastAPI, Request
import httpx

from app.config import settings

router = Router()


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
        await message.answer("Отсканируйте QR-код для входа.")
        return
    await message.answer(
        "Нажмите кнопку, чтобы подтвердить вход.",
        reply_markup=_build_confirm_keyboard(command.args),
    )


@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirm(callback: CallbackQuery) -> None:
    login_token = callback.data.split(":", 1)[1]
    reply = await _confirm_login(login_token, callback.from_user)
    await callback.answer()
    if callback.message:
        await callback.message.answer(reply)


bot = Bot(settings.telegram_bot_token)
dp = Dispatcher()
dp.include_router(router)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.telegram_webhook_public_url:
        await bot.set_webhook(settings.webhook_url)
    try:
        yield
    finally:
        await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.post(settings.telegram_webhook_path)
async def telegram_webhook(request: Request) -> dict[str, str]:
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"status": "ok"}
