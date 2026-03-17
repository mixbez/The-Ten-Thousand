"""
Inline keyboard callbacks for morning/evening nudge completion tracking.
"""
import uuid
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from bot.db.database import async_session_maker
from bot.db.models import Interaction
from bot.fsm.states import DailyLoopStates

logger = logging.getLogger(__name__)
router = Router()


def nudge_keyboard(interaction_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Сделал", callback_data=f"nudge:done:{interaction_id}")
    builder.button(text="❌ Не сделал", callback_data=f"nudge:skip:{interaction_id}")
    return builder.as_markup()


@router.callback_query(F.data.startswith("nudge:"))
async def handle_nudge_callback(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Неверный формат.")
        return

    _, action, interaction_id = parts

    async with async_session_maker() as session:
        try:
            result = await session.execute(
                select(Interaction).where(Interaction.id == uuid.UUID(interaction_id))
            )
            interaction = result.scalar_one_or_none()
            if not interaction:
                await callback.answer("Действие не найдено.")
                return

            interaction.completed = (action == "done")
            interaction.responded_at = datetime.utcnow()
            interaction.response_text = "✅ Выполнено" if action == "done" else "❌ Пропущено"
            await session.commit()

            # If action is "done" and interaction is a medical request, ask for health data
            if action == "done" and interaction.is_medical_request:
                reply = "Фиксирую ✅"
                await callback.answer(reply)
                await callback.message.answer(
                    "Отлично! Пришли результат теста — я внесу в профиль."
                )
                await state.set_state(DailyLoopStates.awaiting_health_data)
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass
                return
        except Exception as e:
            logger.error(f"nudge callback error: {e}")
            await callback.answer("Ошибка.")
            return

    reply = "Фиксирую ✅" if action == "done" else "Понял, без осуждения ❌"
    await callback.answer(reply)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
