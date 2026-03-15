"""
APScheduler-based timezone-aware nudge scheduler.
Uses cron triggers so jobs survive bot restarts (re-registered on startup).
"""
import logging
from datetime import datetime
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from bot.db.database import async_session_maker
from bot.db.models import User, Interaction

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    timezone="UTC",
)


def _utc_hour_minute(local_hour: int, timezone_name: str) -> tuple[int, int]:
    """Convert a local hour to UTC hour/minute for cron scheduling."""
    try:
        tz = pytz.timezone(timezone_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC
    now = datetime.now(tz)
    local_dt = now.replace(hour=local_hour, minute=0, second=0, microsecond=0)
    utc_dt = local_dt.astimezone(pytz.UTC)
    return utc_dt.hour, utc_dt.minute


def register_daily_jobs(user_id: str, timezone_name: str, bot) -> None:
    """Register recurring daily morning + evening jobs for a user."""
    morning_h, morning_m = _utc_hour_minute(8, timezone_name)
    evening_h, evening_m = _utc_hour_minute(20, timezone_name)

    morning_job_id = f"morning_{user_id}"
    evening_job_id = f"evening_{user_id}"

    for job_id in (morning_job_id, evening_job_id):
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    scheduler.add_job(
        send_morning_nudge,
        trigger=CronTrigger(hour=morning_h, minute=morning_m),
        args=[user_id, bot],
        id=morning_job_id,
        replace_existing=True,
    )
    scheduler.add_job(
        send_evening_reflection,
        trigger=CronTrigger(hour=evening_h, minute=evening_m),
        args=[user_id, bot],
        id=evening_job_id,
        replace_existing=True,
    )
    logger.info(
        f"Registered daily jobs for user {user_id}: "
        f"morning {morning_h:02d}:{morning_m:02d} UTC, "
        f"evening {evening_h:02d}:{evening_m:02d} UTC"
    )


async def restore_all_jobs(bot) -> None:
    """Called on startup — re-registers daily jobs for all active users in phase >= 2."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.is_active == True, User.fsm_phase >= 2)
        )
        users = result.scalars().all()

    for user in users:
        register_daily_jobs(str(user.id), user.timezone_name or "UTC", bot)

    logger.info(f"Restored daily jobs for {len(users)} active users")


async def send_morning_nudge(user_id: str, bot) -> None:
    """Generate and send a morning nudge via Claude with inline buttons."""
    import uuid as uuid_mod
    from bot.services.claude_brain import safe_claude_call_v2
    from bot.services.context_builder import build_context, get_today_domain
    from bot.handlers.nudge_callbacks import nudge_keyboard

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.telegram_id or not user.is_active:
            return

        interactions_result = await session.execute(
            select(Interaction)
            .where(Interaction.user_id == user.id)
            .order_by(Interaction.created_at.desc())
            .limit(5)
        )
        recent = interactions_result.scalars().all()

        from bot.scoring_logic import normalize_health_scores
        user_state = {
            "coaching_style": user.coaching_style or "balanced",
            "motivation": user.motivation or "",
            "health_scores": normalize_health_scores(user.health_scores or {}),
            "assessment_data": user.assessment_data or {},
        }
        domain = get_today_domain(user)
        telegram_id = user.telegram_id

    instruction = (
        "Сгенерируй одно утреннее ACTION по focus_domain. "
        "Оцени стресс и применяй Stress Filter. "
        "Если задание повторяется после ✗ — снизь барьер входа. "
        "Действие медицински значимое, ≤15 минут."
    )
    context_str = build_context(user_state, domain, recent, instruction)
    brain_output = await safe_claude_call_v2(context_str)

    # Save interaction record
    async with async_session_maker() as session:
        interaction = Interaction(
            user_id=uuid_mod.UUID(user_id),
            nudge_text=brain_output.message_to_user,
            category=domain,
            delivery_time="MORNING",
        )
        session.add(interaction)
        await session.commit()
        await session.refresh(interaction)
        interaction_id = str(interaction.id)

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=f"🌅 *Утреннее задание*\n\n{brain_output.message_to_user}",
            parse_mode="Markdown",
            reply_markup=nudge_keyboard(interaction_id),
        )
        logger.info(f"Sent morning nudge to user {user_id} (domain: {domain})")
    except Exception as e:
        logger.error(f"Failed to send morning nudge to {user_id}: {e}")


async def send_evening_reflection(user_id: str, bot) -> None:
    """Generate and send an evening reflection question with inline buttons."""
    import uuid as uuid_mod
    from bot.services.claude_brain import safe_claude_call_v2
    from bot.services.context_builder import build_context, get_today_domain
    from bot.handlers.nudge_callbacks import nudge_keyboard

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.telegram_id or not user.is_active:
            return

        interactions_result = await session.execute(
            select(Interaction)
            .where(Interaction.user_id == user.id)
            .order_by(Interaction.created_at.desc())
            .limit(5)
        )
        recent = interactions_result.scalars().all()

        from bot.scoring_logic import normalize_health_scores
        user_state = {
            "coaching_style": user.coaching_style or "balanced",
            "motivation": user.motivation or "",
            "health_scores": normalize_health_scores(user.health_scores or {}),
            "assessment_data": user.assessment_data or {},
        }
        domain = get_today_domain(user)
        telegram_id = user.telegram_id

    instruction = (
        "Задай один вечерний вопрос по focus_domain и сегодняшнему ACTION из history. "
        "Если ✓ — спроси о физиологическом отклике (энергия, концентрация, сон). "
        "Если ✗ или ? — спроси о точке трения, без осуждения. "
        "Один вопрос, не более 2 предложений."
    )
    context_str = build_context(user_state, domain, recent, instruction)
    brain_output = await safe_claude_call_v2(context_str)

    # Save interaction record
    async with async_session_maker() as session:
        interaction = Interaction(
            user_id=uuid_mod.UUID(user_id),
            nudge_text=brain_output.message_to_user,
            category=domain,
            delivery_time="EVENING",
        )
        session.add(interaction)
        await session.commit()
        await session.refresh(interaction)
        interaction_id = str(interaction.id)

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=f"🌙 *Вечерняя рефлексия*\n\n{brain_output.message_to_user}",
            parse_mode="Markdown",
            reply_markup=nudge_keyboard(interaction_id),
        )
        logger.info(f"Sent evening reflection to user {user_id} (domain: {domain})")
    except Exception as e:
        logger.error(f"Failed to send evening reflection to {user_id}: {e}")


async def schedule_nudge(
    user_id: str,
    delivery_time: str,
    timezone_name: str,
    bot,
    nudge_text: str,
    category: str,
) -> None:
    """Legacy one-shot nudge — kept for backward compat with assessment handler."""
    from apscheduler.triggers.date import DateTrigger
    from bot.scheduler_math import get_next_scheduled_time

    run_at = get_next_scheduled_time(delivery_time, timezone_name)
    job_id = f"oneshot_{user_id}_{delivery_time.lower()}"

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        _send_oneshot,
        trigger=DateTrigger(run_date=run_at),
        args=[user_id, nudge_text, bot],
        id=job_id,
        replace_existing=True,
    )
    logger.info(f"Scheduled one-shot {delivery_time} for user {user_id} at {run_at} UTC")


async def _send_oneshot(user_id: str, nudge_text: str, bot) -> None:
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.telegram_id or not user.is_active:
            return
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=f"🌟 *Задание*\n\n{nudge_text}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed one-shot nudge to {user_id}: {e}")
