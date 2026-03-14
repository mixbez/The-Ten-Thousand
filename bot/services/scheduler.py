"""
APScheduler-based timezone-aware nudge scheduler.
"""
import logging
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from sqlalchemy import select
from bot.db.database import async_session_maker
from bot.db.models import User, Interaction
from bot.scheduler_math import get_next_scheduled_time

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    timezone="UTC",
)


async def schedule_nudge(
    user_id: str,
    delivery_time: str,
    timezone_name: str,
    bot,
    nudge_text: str,
    category: str,
):
    """Schedule a nudge for the given user at the appropriate local time."""
    run_at = get_next_scheduled_time(delivery_time, timezone_name)
    job_id = f"nudge_{user_id}_{delivery_time.lower()}"

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        send_nudge,
        trigger="date",
        run_date=run_at,
        args=[user_id, nudge_text, bot],
        id=job_id,
        replace_existing=True,
    )
    logger.info(f"Scheduled {delivery_time} nudge for user {user_id} at {run_at} UTC")


async def send_nudge(user_id: str, nudge_text: str, bot):
    """Actually send the scheduled nudge to the user via Telegram."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user or not user.telegram_id or not user.is_active:
            return
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=f"🌟 *Ежедневное задание*\n\n{nudge_text}",
                parse_mode="Markdown",
            )
            logger.info(f"Sent nudge to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send nudge to {user_id}: {e}")
