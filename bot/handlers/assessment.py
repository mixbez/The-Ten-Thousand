"""
Phase 1: Health baseline assessment handlers.
"""
import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from bot.db.database import async_session_maker
from bot.db.models import User
from bot.fsm.states import AssessmentStates
from bot.scoring_logic import score_assessment
from bot.services.groq_sanitizer import safe_sanitize

logger = logging.getLogger(__name__)
router = Router()

ASSESSMENT_QUESTIONS = {
    "ask_sleep": "Сколько часов ты спишь в среднем за ночь?",
    "ask_nutrition": "Оцени качество питания по шкале 1-10 (1=фастфуд, 10=только цельные продукты).",
    "ask_movement": "Сколько минут физической активности у тебя в среднем в день?",
    "ask_stress": "Оцени уровень стресса по шкале 0-10 (0=спокойствие, 10=выгорание).",
}


@router.message(AssessmentStates.ask_sleep)
async def handle_sleep(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_sleep"])

    if sanitized.result == "BLOCK":
        await message.answer("Ответь на вопрос: сколько часов ты спишь? (например: 7)")
        return

    try:
        hours = float(sanitized.cleaned_text.split()[0])
        if not 0 <= hours <= 24:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("Введи число от 0 до 24 (например: 7.5).")
        return

    await state.update_data(sleep_hours=hours)
    await state.set_state(AssessmentStates.ask_nutrition)
    await message.answer(
        "Понял.\n\n*Питание:* Оцени качество своего рациона от 1 до 10.\n"
        "(1 = в основном обработанная еда, 10 = цельные продукты, сбалансированное питание)",
        parse_mode="Markdown",
    )


@router.message(AssessmentStates.ask_nutrition)
async def handle_nutrition(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_nutrition"])

    if sanitized.result == "BLOCK":
        await message.answer("Оцени питание по шкале 1-10.")
        return

    try:
        rating = int(sanitized.cleaned_text.split()[0])
        if not 1 <= rating <= 10:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("Введи число от 1 до 10.")
        return

    await state.update_data(nutrition_rating=rating)
    await state.set_state(AssessmentStates.ask_movement)
    await message.answer(
        "*Движение:* Сколько минут физической активности у тебя в день? "
        "(ходьба, зал, спорт — всё считается)",
        parse_mode="Markdown",
    )


@router.message(AssessmentStates.ask_movement)
async def handle_movement(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_movement"])

    if sanitized.result == "BLOCK":
        await message.answer("Ответь: сколько минут физической активности в день? (например: 30)")
        return

    try:
        minutes = int(sanitized.cleaned_text.split()[0])
        if minutes < 0:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("Введи неотрицательное число (например: 30).")
        return

    await state.update_data(movement_minutes=minutes)
    await state.set_state(AssessmentStates.ask_stress)
    await message.answer(
        "*Стресс:* Оцени свой ежедневный уровень стресса от 0 до 10.\n"
        "(0 = полное спокойствие, 10 = постоянное напряжение)",
        parse_mode="Markdown",
    )


@router.message(AssessmentStates.ask_stress)
async def handle_stress(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_stress"])

    if sanitized.result == "BLOCK":
        await message.answer("Оцени стресс по шкале 0-10.")
        return

    try:
        level = int(sanitized.cleaned_text.split()[0])
        if not 0 <= level <= 10:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("Введи число от 0 до 10.")
        return

    data = await state.get_data()

    try:
        scores = score_assessment(
            sleep_hours=data["sleep_hours"],
            nutrition_rating=data["nutrition_rating"],
            movement_minutes=data["movement_minutes"],
            stress_level=level,
        )
    except Exception as e:
        logger.error(f"Scoring error: {e}")
        await message.answer("Что-то пошло не так при расчёте баллов. Попробуй /start заново.")
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        user.health_scores = scores
        user.fsm_phase = 2
        from datetime import datetime
        user.last_monthly_audit = datetime.utcnow()
        await session.commit()

    overall = scores["overall"]
    await state.clear()

    await message.answer(
        f"*Оценка завершена!*\n\n"
        f"Твои базовые показатели:\n"
        f"• Сон: {scores['sleep']}/100\n"
        f"• Питание: {scores['nutrition']}/100\n"
        f"• Движение: {scores['movement']}/100\n"
        f"• Стресс: {scores['stress']}/100\n"
        f"• *Общий балл: {overall}/100*\n\n"
        f"Ежедневные напоминания начнутся завтра утром. "
        f"Буду заходить к тебе каждое утро и вечер.\n\n"
        f"Используй /timezone, чтобы указать свой часовой пояс.",
        parse_mode="Markdown",
    )
