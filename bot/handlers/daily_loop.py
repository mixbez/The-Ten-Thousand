"""
Phase 2/3: Daily morning nudge and evening reflection handlers.
"""
import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from bot.db.database import async_session_maker
from bot.db.models import User
from bot.fsm.states import DailyLoopStates
from bot.services.groq_sanitizer import safe_sanitize
from bot.services.claude_brain import safe_claude_call
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
