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
from sqlalchemy import select, delete
from bot.db.database import async_session_maker
from bot.db.models import User, Interaction
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
    is_admin = str(message.from_user.id) == settings.admin_telegram_id
    admin_override = is_admin and "--admin" in (message.text or "")

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Сначала напиши /start.")
            return

        if not admin_override and is_monthly_cooldown_active(user.last_monthly_audit, settings.monthly_cooldown_days):
            days_left = days_until_cooldown_expires(
                user.last_monthly_audit, settings.monthly_cooldown_days
            )
            await message.answer(
                f"Ежемесячный аудит пока недоступен. Откроется через *{days_left} дн.*",
                parse_mode="Markdown",
            )
            return

        from bot.fsm.states import AssessmentStates
        from bot.handlers.assessment import ASSESSMENT_QUESTIONS
        await state.set_state(AssessmentStates.ask_age_sex)
        await message.answer("Время для ежемесячного аудита — 12 вопросов, чтобы увидеть динамику.")
        await message.answer(ASSESSMENT_QUESTIONS["ask_age_sex"])


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


@router.message(Command("hard_reset"))
async def cmd_hard_reset(message: Message, state: FSMContext):
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if user:
            await session.execute(delete(Interaction).where(Interaction.user_id == user.id))
            await session.delete(user)
            await session.commit()

    await state.clear()
    await message.answer(
        "Все твои данные удалены. Напиши /start, чтобы начать заново."
    )


@router.message(Command("get_info"))
async def cmd_get_info(message: Message):
    """Show user all data stored about them."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Данных нет. Напиши /start, чтобы зарегистрироваться.")
            return

    ad = user.assessment_data or {}
    hs = user.health_scores or {}

    lines = ["*Данные, которые мы храним о тебе:*\n"]

    # Profile
    lines.append("*— Профиль —*")
    lines.append(f"Возраст: {ad.get('age') or '—'}")
    lines.append(f"Пол: {ad.get('sex') or '—'}")
    lines.append(f"Работа: {ad.get('occupation') or '—'}")
    lines.append(f"Стиль коучинга: {user.coaching_style or '—'}")
    lines.append(f"Мотивация: {user.motivation or '—'}")
    lines.append(f"Часовой пояс: {user.timezone_name or 'UTC'}")

    # Health inputs
    lines.append("\n*— Данные о здоровье —*")
    lines.append(f"Сон (среднее): {ad.get('avg_sleep', '—')} ч")
    lines.append(f"Сон (вариабельность): {ad.get('sleep_variance', '—')} ч")
    lines.append(f"Утренняя энергия: {ad.get('morning_energy', '—')}/10")
    lines.append(f"Туман в голове: {ad.get('brain_fog') or '—'}")
    lines.append(f"Сидячее время: {ad.get('sedentary_hours', '—')} ч/день")
    lines.append(f"Физическая активность: {ad.get('exercise') or '—'}")
    lines.append(f"Стресс: {ad.get('stress_detail') or '—'}")

    # Medical
    lines.append("\n*— Медицинское —*")
    lines.append(f"Препараты/добавки: {ad.get('medications') or '—'}")
    lines.append(f"Вещества: {ad.get('substances') or '—'}")
    lines.append(f"Анализы крови: {ad.get('blood_work') or '—'}")
    lines.append(f"Состояния/диагнозы: {ad.get('conditions') or '—'}")

    # Health data log (collected via bot)
    health_log = ad.get('health_data_log', [])
    if health_log:
        lines.append(f"\n*— Данные от тебя —*")
        for entry in health_log[-5:]:  # Show last 5 entries
            lines.append(f"• {entry}")

    # Scores
    if hs:
        lines.append("\n*— Баллы здоровья —*")
        score_labels = {
            "sleep": "Сон",
            "metabolic": "Метаболика",
            "physical": "Физическое",
            "mental_recovery": "Ментальное восстановление",
            "overall": "Общий балл",
        }
        for key, label in score_labels.items():
            if key in hs:
                lines.append(f"{label}: {hs[key]}")

    # Meta
    lines.append("\n*— Служебное —*")
    lines.append(f"Аккаунт создан: {user.created_at.strftime('%Y-%m-%d') if user.created_at else '—'}")
    last_audit = user.last_monthly_audit.strftime('%Y-%m-%d') if user.last_monthly_audit else '—'
    lines.append(f"Последний аудит: {last_audit}")
    lines.append(f"Статус: {'активен' if user.is_active else 'приостановлен'}")
    lines.append(f"\nЧтобы удалить все данные — напиши /hard\\_reset.")

    await message.answer("\n".join(lines), parse_mode="Markdown")


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
