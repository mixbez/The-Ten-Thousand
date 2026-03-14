"""
Telegram command handlers: /start, /timezone, /personality, /monthly, /stop, /link
"""
import logging
import uuid
from datetime import datetime
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from bot.db.database import async_session_maker
from bot.db.models import User
from bot.fsm.states import OnboardingStates
from bot.scheduler_math import is_monthly_cooldown_active, days_until_cooldown_expires
from bot.config import settings

logger = logging.getLogger(__name__)
router = Router()


async def get_or_create_user(telegram_id: str, session) -> User:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    async with async_session_maker() as session:
        user = await get_or_create_user(str(message.from_user.id), session)

        if user.fsm_phase == 0:
            await state.set_state(OnboardingStates.ask_name)
            await message.answer(
                "Добро пожаловать в *10 000* — твой путь к 10 000 дополнительным дням жизни.\n\n"
                "Я твой проактивный коуч по здоровью. Каждый день буду присылать "
                "микро-действия, подобранные под твой образ жизни.\n\n"
                "Начнём с нескольких коротких вопросов.\n\n"
                "Как тебя зовут?",
                parse_mode="Markdown",
            )
        else:
            await message.answer(
                f"С возвращением! Ты на фазе {user.fsm_phase}. "
                "Я продолжу присылать ежедневные напоминания. Используй /stop, чтобы поставить на паузу."
            )


@router.message(Command("timezone"))
async def cmd_timezone(message: Message):
    await message.answer(
        "Напиши название своего часового пояса (например, `Europe/Moscow`, `Asia/Yekaterinburg`, `Europe/Berlin`).\n\n"
        "Это нужно, чтобы присылать утреннее напоминание в 8:00 и вечернее — в 20:00 по твоему времени.",
        parse_mode="Markdown",
    )


@router.message(Command("personality"))
async def cmd_personality(message: Message):
    await message.answer(
        "Стиль коучинга можно изменить.\n\n"
        "Ответь одним из вариантов:\n"
        "• *disciplined* — строго, без оправданий\n"
        "• *compassionate* — мягко, с пониманием\n"
        "• *balanced* — сочетание обоих",
        parse_mode="Markdown",
    )


@router.message(Command("monthly"))
async def cmd_monthly(message: Message, state: FSMContext):
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Сначала напиши /start.")
            return

        if is_monthly_cooldown_active(user.last_monthly_audit, settings.monthly_cooldown_days):
            days_left = days_until_cooldown_expires(
                user.last_monthly_audit, settings.monthly_cooldown_days
            )
            await message.answer(
                f"Ежемесячный аудит пока недоступен. Откроется через *{days_left} дн.*",
                parse_mode="Markdown",
            )
            return

        from bot.fsm.states import AssessmentStates
        await state.set_state(AssessmentStates.ask_sleep_consistency)
        await message.answer(
            "Время для ежемесячного аудита!\n\n"
            "Переоценим твои паттерны.\n\n"
            "*Сон:* Сколько часов ты спишь и насколько это стабильно?\n"
            "(например: стабильно 7-8 часов ИЛИ от 4 до 12 в зависимости от дня)",
            parse_mode="Markdown",
        )


@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext):
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if user:
            user.is_active = False
            await session.commit()

    await state.clear()
    await message.answer(
        "Напоминания приостановлены. Данные сохранены. Напиши /start, чтобы продолжить."
    )


@router.message(Command("link"))
async def cmd_link(message: Message):
    """Opt-in: link Telegram ID for account recovery."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if user:
            await message.answer(
                f"Твой идентификатор для восстановления: `{user.id}`\n\n"
                "Сохрани его. На новом устройстве используй /recover <ID>.",
                parse_mode="Markdown",
            )
        else:
            await message.answer("Сначала напиши /start.")
