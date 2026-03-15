"""
Phase 1: Deep health assessment (7 questions) + Phase 1.5 Longevity Insight.
"""
import logging
import re
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from bot.db.database import async_session_maker
from bot.db.models import User
from bot.fsm.states import AssessmentStates
from bot.scoring_logic import score_deep_assessment
from bot.services.groq_sanitizer import safe_sanitize
from bot.services.claude_brain import safe_claude_call

logger = logging.getLogger(__name__)
router = Router()

ASSESSMENT_QUESTIONS = {
    "ask_sleep_consistency": "Сколько часов ты спишь и насколько это стабильно? (например: стабильно 7-8 часов ИЛИ от 4 до 12 в зависимости от дня)",
    "ask_morning_energy": "Как ты себя чувствуешь через 30 минут после пробуждения? Оцени по шкале от 1 до 10.",
    "ask_brain_fog": "Как часто после обеда у тебя бывает туман в голове или резкий спад энергии? (Никогда / Иногда / Каждый день)",
    "ask_sedentary": "Сколько часов в день ты проводишь сидя без перерыва?",
    "ask_stress_detail": "Что является твоим главным источником стресса, и есть ли у тебя ритуал отключения перед сном?",
    "ask_supplements": "Принимаешь ли ты какие-либо лекарства или добавки, которые влияют на концентрацию или энергию?",
}


def _parse_sleep_consistency(text: str) -> tuple[float, float]:
    """Parse sleep answer into (avg_hours, variance). Returns (7.0, 0.0) as fallback."""
    numbers = re.findall(r'\d+(?:[.,]\d+)?', text)
    floats = [float(n.replace(',', '.')) for n in numbers if float(n.replace(',', '.')) <= 24]
    if len(floats) >= 2:
        low, high = min(floats[:2]), max(floats[:2])
        return (low + high) / 2, high - low
    elif len(floats) == 1:
        return floats[0], 0.0
    return 7.0, 0.0


@router.message(AssessmentStates.ask_sleep_consistency)
async def handle_sleep_consistency(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_sleep_consistency"])

    if sanitized.result == "BLOCK":
        await message.answer("Расскажи о своём сне: сколько часов и насколько это постоянно? (например: 7-8 часов стабильно)")
        return

    avg, variance = _parse_sleep_consistency(sanitized.cleaned_text)
    await state.update_data(sleep_text=sanitized.cleaned_text, avg_sleep=avg, sleep_variance=variance)
    await state.set_state(AssessmentStates.ask_morning_energy)
    await message.answer(
        "Понял.\n\n*Утренняя энергия:* Как ты себя чувствуешь через 30 минут после пробуждения?\n"
        "Оцени от 1 до 10, где 1 — еле живой, 10 — полный сил.",
        parse_mode="Markdown",
    )


@router.message(AssessmentStates.ask_morning_energy)
async def handle_morning_energy(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_morning_energy"])

    if sanitized.result == "BLOCK":
        await message.answer("Оцени утреннее самочувствие от 1 до 10.")
        return

    try:
        numbers = re.findall(r'\d+', sanitized.cleaned_text)
        rating = int(numbers[0]) if numbers else 0
        if not 1 <= rating <= 10:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("Введи число от 1 до 10.")
        return

    await state.update_data(morning_energy=rating)
    await state.set_state(AssessmentStates.ask_brain_fog)
    await message.answer(
        "*Питание и энергия:* Как часто после обеда у тебя бывает туман в голове или резкий спад энергии?\n\n"
        "• Никогда\n• Иногда\n• Каждый день",
        parse_mode="Markdown",
    )


@router.message(AssessmentStates.ask_brain_fog)
async def handle_brain_fog(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_brain_fog"])

    if sanitized.result == "BLOCK":
        await message.answer("Ответь: Никогда, Иногда или Каждый день.")
        return

    await state.update_data(brain_fog=sanitized.cleaned_text)
    await state.set_state(AssessmentStates.ask_sedentary)
    await message.answer(
        "*Активность:* Сколько часов в день ты проводишь сидя без перерыва?\n"
        "(работа за компьютером, поездки, просмотр контента — всё считается)",
        parse_mode="Markdown",
    )


@router.message(AssessmentStates.ask_sedentary)
async def handle_sedentary(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_sedentary"])

    if sanitized.result == "BLOCK":
        await message.answer("Ответь числом — сколько часов в день ты сидишь? (например: 8)")
        return

    try:
        numbers = re.findall(r'\d+(?:[.,]\d+)?', sanitized.cleaned_text)
        hours = float(numbers[0].replace(',', '.')) if numbers else -1
        if hours < 0 or hours > 24:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("Введи число часов от 0 до 24.")
        return

    await state.update_data(sedentary_hours=hours)
    await state.set_state(AssessmentStates.ask_stress_detail)
    await message.answer(
        "*Стресс и восстановление:* Что является твоим главным источником стресса?\n"
        "И есть ли у тебя какой-то ритуал отключения перед сном?",
        parse_mode="Markdown",
    )


@router.message(AssessmentStates.ask_stress_detail)
async def handle_stress_detail(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_stress_detail"])

    if sanitized.result == "BLOCK":
        await message.answer("Расскажи: что тебя стрессует, и как ты готовишься ко сну?")
        return

    await state.update_data(stress_detail=sanitized.cleaned_text)
    await state.set_state(AssessmentStates.ask_supplements)
    await message.answer(
        "*Последний вопрос:* Принимаешь ли ты какие-либо лекарства или добавки, "
        "которые влияют на концентрацию или энергию?\n"
        "(кофеин, магний, антидепрессанты, мелатонин и т.д. — если есть, укажи)"
    )


@router.message(AssessmentStates.ask_supplements)
async def handle_supplements(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_supplements"])

    if sanitized.result == "BLOCK":
        await message.answer("Укажи добавки или лекарства, или напиши 'нет'.")
        return

    data = await state.get_data()

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        # Derive numeric stress estimate from stress_detail length and keywords
        stress_text = data.get("stress_detail", "").lower()
        stress_keywords = ["выгора", "тревог", "не сплю", "паник", "постоян", "очень"]
        stress_level = 7 if any(k in stress_text for k in stress_keywords) else 4

        avg_sleep = data.get("avg_sleep", 7.0)
        sleep_variance = data.get("sleep_variance", 0.0)
        morning_energy = data.get("morning_energy", 5)
        brain_fog = data.get("brain_fog", "Иногда")
        sedentary_hours = data.get("sedentary_hours", 6.0)

        scores = score_deep_assessment(
            avg_sleep=avg_sleep,
            sleep_variance=sleep_variance,
            morning_energy=morning_energy,
            brain_fog=brain_fog,
            sedentary_hours=sedentary_hours,
            stress_level=stress_level,
        )

        assessment_data = {
            "sleep_text": data.get("sleep_text", ""),
            "avg_sleep": avg_sleep,
            "sleep_variance": sleep_variance,
            "morning_energy": morning_energy,
            "brain_fog": brain_fog,
            "sedentary_hours": sedentary_hours,
            "stress_detail": data.get("stress_detail", ""),
            "stress_level": stress_level,
            "supplements": sanitized.cleaned_text,
        }

        user.health_scores = scores
        user.assessment_data = assessment_data
        user.fsm_phase = 2
        from datetime import datetime
        user.last_monthly_audit = datetime.utcnow()
        await session.commit()

        user_state = {
            "name": data.get("name", ""),
            "coaching_style": user.coaching_style or "balanced",
            "motivation": user.motivation or "",
            "health_scores": scores,
            "assessment_data": assessment_data,
            "timezone_name": user.timezone_name,
        }

    await state.clear()

    overall = scores["overall"]
    await message.answer(
        f"*Твои показатели:*\n"
        f"• Сон: {scores['sleep']}/100\n"
        f"• Утренняя энергия: {scores['energy']}/100\n"
        f"• Питание: {scores['nutrition']}/100\n"
        f"• Движение: {scores['movement']}/100\n"
        f"• Стресс: {scores['stress']}/100\n"
        f"• *Общий балл: {overall}/100*\n\n"
        f"Анализирую взаимосвязи...",
        parse_mode="Markdown",
    )

    # Phase 1.5 — Longevity Insight via Claude
    brain_output = await safe_claude_call(
        user_state=user_state,
        sanitized_input=None,
        history=[],
        instruction=(
            "Ассессмент завершён. Проведи корреляционный анализ: найди главную 'утечку' "
            "(самый низкий показатель), свяжи её с мотивацией пользователя и дай один "
            "конкретный инсайт — почему именно этот показатель блокирует его цель. "
            "Назови пользователя по имени. Будь прямым и конкретным, без воды. "
            "Затем скажи, что первое утреннее задание придёт завтра утром."
        ),
    )

    await message.answer(brain_output.message_to_user)

    # Register recurring daily jobs now that assessment is complete
    from bot.services.scheduler import register_daily_jobs
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if user:
            register_daily_jobs(str(user.id), user.timezone_name or "UTC", message.bot)
