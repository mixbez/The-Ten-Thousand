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
            "guid": str(user.id),
            "phase": user.fsm_phase,
            "personality": user.personality,
            "coaching_style": user.coaching_style,
            "health_scores": user.health_scores or {},
            "timezone_name": user.timezone_name,
        }

        brain_output = await safe_claude_call(
            user_state=user_state,
            sanitized_input=sanitized.cleaned_text,
            history=[],
            instruction="User has responded to their evening reflection. Acknowledge, update scores if needed, and prepare tomorrow's morning nudge.",
        )

        if brain_output.updated_scores:
            user.health_scores = {**user.health_scores, **brain_output.updated_scores}

        user.block_count = 0
        await session.commit()

        if brain_output.next_interaction:
            from bot.services.scheduler import schedule_nudge
            from bot.main import bot
            await schedule_nudge(
                user_id=str(user.id),
                delivery_time=brain_output.next_interaction.delivery_time,
                timezone_name=user.timezone_name,
                bot=bot,
                nudge_text=brain_output.next_interaction.nudge_text,
                category=brain_output.next_interaction.category,
            )

    await state.clear()
    await message.answer(brain_output.message)
