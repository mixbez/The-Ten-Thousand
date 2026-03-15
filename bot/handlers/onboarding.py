"""
Phase 0: Personality onboarding handlers.
"""
import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from bot.db.database import async_session_maker
from bot.db.models import User
from bot.fsm.states import OnboardingStates, AssessmentStates
from bot.services.groq_sanitizer import safe_sanitize

logger = logging.getLogger(__name__)
router = Router()

ONBOARDING_QUESTIONS = {
    "ask_name": "Как тебя зовут?",
    "ask_coaching_style": "Как ты предпочитаешь получать коучинг? (disciplined / compassionate / balanced)",
    "ask_motivation": "Какова твоя главная мотивация для улучшения здоровья?",
    "ask_commitment": "Сколько минут в день ты готов посвящать здоровой привычке? (например, 5, 10, 20)",
}


async def check_rate_limit(user: User) -> bool:
    """Returns True if user is within rate limit."""
    from datetime import datetime, timedelta
    from bot.config import settings

    now = datetime.utcnow()
    if user.message_window_start is None or \
       (now - user.message_window_start).total_seconds() > settings.rate_limit_window_seconds:
        user.message_window_start = now
        user.message_count = 1
        return True

    if user.message_count >= settings.max_messages_per_window:
        return False

    user.message_count += 1
    return True


@router.message(OnboardingStates.ask_name)
async def handle_name(message: Message, state: FSMContext):
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        if not await check_rate_limit(user):
            await message.answer("Ты отправляешь сообщения слишком быстро. Подожди несколько минут.")
            await session.commit()
            return

        sanitized = await safe_sanitize(message.text, ONBOARDING_QUESTIONS["ask_name"])

        if sanitized.result == "BLOCK":
            user.block_count += 1
            await session.commit()
            if user.block_count >= 3:
                await message.answer(
                    "Напоминание о правилах использования: я бот для коучинга по здоровью. "
                    "Я обрабатываю только ответы на мои конкретные вопросы. "
                    "Диалог приостановлен на 10 минут."
                )
                return
            await message.answer("Пожалуйста, ответь на вопрос: как тебя зовут?")
            return

        user.block_count = 0
        await state.update_data(name=sanitized.cleaned_text)
        await session.commit()

    await state.set_state(OnboardingStates.ask_coaching_style)
    await message.answer(
        f"Отлично, {sanitized.cleaned_text}!\n\n"
        "Как ты предпочитаешь получать коучинг?\n\n"
        "• *disciplined* — строго, без оправданий\n"
        "• *compassionate* — мягко, с пониманием\n"
        "• *balanced* — сочетание обоих",
        parse_mode="Markdown",
    )


@router.message(OnboardingStates.ask_coaching_style)
async def handle_coaching_style(message: Message, state: FSMContext):
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        sanitized = await safe_sanitize(
            message.text, ONBOARDING_QUESTIONS["ask_coaching_style"]
        )

        if sanitized.result == "BLOCK":
            user.block_count += 1
            await session.commit()
            await message.answer(
                "Выбери один вариант: disciplined, compassionate или balanced"
            )
            return

        style = sanitized.cleaned_text.lower().strip()
        if style not in ("disciplined", "compassionate", "balanced"):
            style = "balanced"

        user.coaching_style = style
        user.block_count = 0
        await state.update_data(coaching_style=style)
        await session.commit()

    await state.set_state(OnboardingStates.ask_motivation)
    await message.answer(
        "Какова твоя главная мотивация для улучшения здоровья? "
        "(например: больше энергии, долголетие, снижение веса, ясность ума)"
    )


@router.message(OnboardingStates.ask_motivation)
async def handle_motivation(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(
        message.text, ONBOARDING_QUESTIONS["ask_motivation"]
    )

    if sanitized.result == "BLOCK":
        await message.answer("Поделись своей мотивацией в нескольких словах.")
        return

    await state.update_data(motivation=sanitized.cleaned_text)
    await state.set_state(OnboardingStates.ask_commitment)
    await message.answer(
        "Сколько минут в день ты реально готов уделять здоровой привычке? "
        "(Напиши число, например: 5, 10, 20)"
    )


@router.message(OnboardingStates.ask_commitment)
async def handle_commitment(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(
        message.text, ONBOARDING_QUESTIONS["ask_commitment"]
    )

    if sanitized.result == "BLOCK":
        await message.answer("Напиши число минут (например: 10).")
        return

    data = await state.get_data()

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        user.motivation = data.get("motivation", "")
        user.fsm_phase = 1
        await session.commit()

    from bot.fsm.states import AssessmentStates
    await state.set_state(AssessmentStates.ask_age_sex)
    await message.answer(
        "Отлично! Теперь составим твой профиль здоровья.\n\n"
        "*Оценка* — 12 вопросов о паттернах, образе жизни и биомаркерах.\n\n"
        "Сколько тебе лет и какой биологический пол? (например: 34, мужской)",
        parse_mode="Markdown",
    )
