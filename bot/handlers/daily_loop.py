"""
Phase 2/3: Daily morning nudge and evening reflection handlers.
"""
import logging
import uuid
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StateFilter
from sqlalchemy import select
from bot.db.database import async_session_maker
from bot.db.models import User
from bot.fsm.states import DailyLoopStates
from bot.services.groq_sanitizer import safe_sanitize
from bot.services.claude_brain import safe_claude_call
from bot.services.health_parser import safe_parse_health_data, merge_metrics_into_assessment
from bot.scoring_logic import normalize_health_scores

logger = logging.getLogger(__name__)
router = Router()


@router.message(DailyLoopStates.awaiting_evening_reflection)
async def handle_reflection_response(message: Message, state: FSMContext):
    data = await state.get_data()
    current_question = data.get("reflection_question", "How did today's nudge go?")

    sanitized = await safe_sanitize(message.text, current_question)

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        if sanitized.result == "BLOCK":
            user.block_count += 1
            await session.commit()
            if user.block_count >= 3:
                await message.answer(
                    "Напоминание о правилах: пожалуйста, отвечай только на вопрос рефлексии."
                )
            else:
                await message.answer(f"Ответь на вопрос: {current_question}")
            return

        user_state = {
            "name": "",
            "coaching_style": user.coaching_style or "balanced",
            "motivation": user.motivation or "",
            "health_scores": normalize_health_scores(user.health_scores or {}),
            "assessment_data": user.assessment_data or {},
            "timezone_name": user.timezone_name,
        }

        brain_output = await safe_claude_call(
            user_state=user_state,
            sanitized_input=sanitized.cleaned_text,
            history=[],
            instruction=(
                "Пользователь ответил на вечерний вопрос рефлексии. "
                "Оцени стресс из assessment_data.stress_detail и применяй Stress Filter самостоятельно. "
                "Прими ответ, обнови domain_scores если есть основания, "
                "и подготовь завтрашнее утреннее ACTION на основе главного data gap или слабейшего домена."
            ),
        )

        if brain_output.updated_scores:
            new_domains = brain_output.updated_scores.get("domain_scores", {})
            if new_domains:
                merged = normalize_health_scores(user.health_scores or {})
                merged.update(new_domains)
                user.health_scores = merged

        user.block_count = 0
        await session.commit()

        pass  # daily jobs run on cron — no need to reschedule after each reflection

    await state.clear()
    await message.answer(brain_output.message_to_user)


async def _try_parse_and_store_health_data(message: Message) -> None:
    """
    Shared helper: try to parse health data from message text and store it in assessment_data.
    """
    result = await safe_parse_health_data(message.text)
    if not result.found:
        return  # silently ignore if no health data found

    async with async_session_maker() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = user.scalar_one_or_none()
        if not user:
            return

        # Merge metrics into assessment_data
        existing = user.assessment_data or {}
        user.assessment_data = merge_metrics_into_assessment(existing, result.metrics)
        await session.commit()

    await message.answer(f"Записали: {result.summary_line}")


@router.message(DailyLoopStates.awaiting_health_data)
async def handle_health_data_after_nudge(message: Message, state: FSMContext):
    """
    Handle health data input after user completes a medical nudge.
    """
    result = await safe_parse_health_data(message.text)
    if result.found:
        # Store in database
        async with async_session_maker() as session:
            user = await session.execute(
                select(User).where(User.telegram_id == str(message.from_user.id))
            )
            user = user.scalar_one_or_none()
            if user:
                existing = user.assessment_data or {}
                user.assessment_data = merge_metrics_into_assessment(existing, result.metrics)
                await session.commit()

        await message.answer(f"Записали: {result.summary_line}")
    else:
        await message.answer("Не распознал данные. Попробуй: 'HOMA-IR 1.8' или 'VO2 max 48'.")

    await state.clear()


@router.message(DailyLoopStates.morning_nudge_sent)
async def handle_free_text_during_nudge(message: Message):
    """
    Handle free text input while in morning_nudge_sent state.
    Try to parse health data, but don't clear state (user may still interact with buttons).
    """
    await _try_parse_and_store_health_data(message)


@router.message(StateFilter(None))
async def handle_free_text_no_state(message: Message):
    """
    Catch-all handler for free text when user has no FSM state.
    Only process for fsm_phase >= 2 users (skip onboarding/assessment users).
    """
    async with async_session_maker() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = user.scalar_one_or_none()
        if not user or user.fsm_phase < 2:
            return  # silently ignore non-daily-loop users

    await _try_parse_and_store_health_data(message)

async def _try_parse_and_store_health_data(message: Message) -> None:
    """
    Shared helper: attempt to parse health metrics from free-text message.
    Silent ignore if nothing found. Saves to DB if metrics detected.
    """
    result = await safe_parse_health_data(message.text)
    if not result.found:
        return  # silent ignore

    async with async_session_maker() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = user.scalar_one_or_none()
        if not user:
            return
        existing = user.assessment_data or {}
        user.assessment_data = merge_metrics_into_assessment(existing, result.metrics)
        await session.commit()

    await message.answer(f"Записали: {result.summary_line}")
