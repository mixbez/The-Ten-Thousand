"""
Phase 1: Deep health assessment (12 questions) + Phase 1.5 Longevity Insight.
"""
import logging
import re
from datetime import datetime
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from bot.db.database import async_session_maker
from bot.db.models import User
from bot.fsm.states import AssessmentStates
from bot.scoring_logic import score_deep_assessment, normalize_health_scores
from bot.services.groq_sanitizer import safe_sanitize
from bot.services.claude_brain import safe_claude_call

logger = logging.getLogger(__name__)
router = Router()

ASSESSMENT_QUESTIONS = {
    "ask_age_sex": "Сколько тебе лет и какой биологический пол? (например: 34, мужской)",
    "ask_occupation": "Кем работаешь и как выглядит типичный рабочий день? (офис, физический труд, ненормированный график — опиши в двух словах)",
    "ask_substances": "Алкоголь, курение, что-то ещё? Без осуждения — это важно для метаболического профиля. (например: 3-4 бокала вина в неделю, не курю)",
    "ask_medications": "Принимаешь лекарства или добавки на постоянной основе? (антидепрессанты, статины, магний, витамин D и т.д. — или напиши 'нет')",
    "ask_sleep_consistency": "Сон: сколько часов спишь и насколько стабильно? (например: стабильно 7-8 ч, или от 4 до 12 в зависимости от дня)",
    "ask_morning_energy": "Как чувствуешь себя через 30 минут после пробуждения? Оцени от 1 до 10.",
    "ask_brain_fog": "Как часто после обеда бывает туман в голове или резкий спад энергии? (Никогда / Иногда / Каждый день)",
    "ask_exercise": "Физическая активность: что делаешь, как часто, сколько по времени? (или 'ничего' — это тоже данные)",
    "ask_sedentary": "Сколько часов в день сидишь суммарно? И как часто встаёшь — примерно каждые сколько минут? (например: 9 часов, встаю каждые 45 мин)",
    "ask_blood_work": "Сдавал(-а) когда-нибудь расширенный анализ крови? Если помнишь — укажи цифры: глюкоза, холестерин, HbA1c, витамин D. Если нет — напиши 'нет'.",
    "ask_conditions": "Есть ли диагностированные заболевания или хронические состояния? (диабет, гипертония, тревожность, СДВГ и т.д. — или 'нет')",
    "ask_stress_detail": "Главный источник стресса прямо сейчас? И есть ли какой-то ритуал перед сном — или сразу в телефон?",
}


def _parse_sleep_consistency(text: str) -> tuple[float, float]:
    """Parse sleep answer into (avg_hours, variance). Returns (7.0, 1.0) as fallback."""
    t = text.lower()
    numbers = re.findall(r'\d+(?:[.,]\d+)?', text)
    floats = [float(n.replace(',', '.')) for n in numbers if float(n.replace(',', '.')) <= 24]

    if len(floats) >= 2:
        low, high = min(floats[:2]), max(floats[:2])
        avg, numeric_variance = (low + high) / 2, high - low
    elif len(floats) == 1:
        avg, numeric_variance = floats[0], 0.0
    else:
        avg, numeric_variance = 7.0, 1.0

    # Override with qualitative instability keywords — they trump narrow numeric range
    if any(w in t for w in ("очень нестабильно", "крайне нестабильно", "сильно варьируется",
                             "очень по-разному", "очень разный", "абсолютно нестабильно")):
        variance = max(numeric_variance, 5.0)
    elif any(w in t for w in ("нестабильно", "непостоянно", "по-разному", "варьируется",
                               "непредсказуемо", "нерегулярно", "разный", "по разному")):
        variance = max(numeric_variance, 3.0)
    elif any(w in t for w in ("иногда", "бывает", "не всегда", "не регулярно")):
        variance = max(numeric_variance, 2.0)
    else:
        variance = numeric_variance

    return avg, variance


def _parse_age(text: str) -> int:
    """Extract age from text. Returns 0 if not found."""
    numbers = re.findall(r'\b(\d{1,3})\b', text)
    for n in numbers:
        age = int(n)
        if 10 <= age <= 120:
            return age
    return 0


def _parse_sex(text: str) -> str:
    """Extract biological sex from text."""
    t = text.lower()
    if any(w in t for w in ("женщ", "female", "жен", "ж,")):
        return "женский"
    if any(w in t for w in ("мужчин", "male", "муж", "м,")):
        return "мужской"
    return text.strip()


# ── Q1: age + sex ──────────────────────────────────────────────────────────────

@router.message(AssessmentStates.ask_age_sex)
async def handle_age_sex(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_age_sex"])

    if sanitized.result == "BLOCK":
        await message.answer("Укажи возраст и биологический пол (например: 34, мужской).")
        return

    age = _parse_age(sanitized.cleaned_text)
    sex = _parse_sex(sanitized.cleaned_text)
    await state.update_data(age=age, sex=sex)
    await state.set_state(AssessmentStates.ask_occupation)
    await message.answer(ASSESSMENT_QUESTIONS["ask_occupation"])


# ── Q2: occupation ─────────────────────────────────────────────────────────────

@router.message(AssessmentStates.ask_occupation)
async def handle_occupation(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_occupation"])

    if sanitized.result == "BLOCK":
        await message.answer("Расскажи о работе и типичном рабочем дне в двух словах.")
        return

    await state.update_data(occupation=sanitized.cleaned_text)
    await state.set_state(AssessmentStates.ask_substances)
    await message.answer(ASSESSMENT_QUESTIONS["ask_substances"])


# ── Q3: substances ─────────────────────────────────────────────────────────────

@router.message(AssessmentStates.ask_substances)
async def handle_substances(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_substances"])

    if sanitized.result == "BLOCK":
        await message.answer("Укажи употребление алкоголя, табака или других веществ — или напиши 'нет'.")
        return

    await state.update_data(substances=sanitized.cleaned_text)
    await state.set_state(AssessmentStates.ask_medications)
    await message.answer(ASSESSMENT_QUESTIONS["ask_medications"])


# ── Q4: medications ────────────────────────────────────────────────────────────

@router.message(AssessmentStates.ask_medications)
async def handle_medications(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_medications"])

    if sanitized.result == "BLOCK":
        await message.answer("Укажи лекарства или добавки — или напиши 'нет'.")
        return

    await state.update_data(medications=sanitized.cleaned_text)
    await state.set_state(AssessmentStates.ask_sleep_consistency)
    await message.answer(ASSESSMENT_QUESTIONS["ask_sleep_consistency"])


# ── Q5: sleep consistency ──────────────────────────────────────────────────────

@router.message(AssessmentStates.ask_sleep_consistency)
async def handle_sleep_consistency(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_sleep_consistency"])

    if sanitized.result == "BLOCK":
        await message.answer("Расскажи о сне: сколько часов и насколько стабильно? (например: 7-8 часов стабильно)")
        return

    avg, variance = _parse_sleep_consistency(sanitized.cleaned_text)
    await state.update_data(sleep_text=sanitized.cleaned_text, avg_sleep=avg, sleep_variance=variance)
    await state.set_state(AssessmentStates.ask_morning_energy)
    await message.answer(ASSESSMENT_QUESTIONS["ask_morning_energy"])


# ── Q6: morning energy ─────────────────────────────────────────────────────────

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
    await message.answer(ASSESSMENT_QUESTIONS["ask_brain_fog"])


# ── Q7: brain fog ──────────────────────────────────────────────────────────────

@router.message(AssessmentStates.ask_brain_fog)
async def handle_brain_fog(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_brain_fog"])

    if sanitized.result == "BLOCK":
        await message.answer("Ответь: Никогда, Иногда или Каждый день.")
        return

    await state.update_data(brain_fog=sanitized.cleaned_text)
    await state.set_state(AssessmentStates.ask_exercise)
    await message.answer(ASSESSMENT_QUESTIONS["ask_exercise"])


# ── Q8: exercise ───────────────────────────────────────────────────────────────

@router.message(AssessmentStates.ask_exercise)
async def handle_exercise(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_exercise"])

    if sanitized.result == "BLOCK":
        await message.answer("Расскажи о физической активности — или напиши 'ничего'.")
        return

    await state.update_data(exercise=sanitized.cleaned_text)
    await state.set_state(AssessmentStates.ask_sedentary)
    await message.answer(ASSESSMENT_QUESTIONS["ask_sedentary"])


# ── Q9: sedentary ──────────────────────────────────────────────────────────────

@router.message(AssessmentStates.ask_sedentary)
async def handle_sedentary(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_sedentary"])

    if sanitized.result == "BLOCK":
        await message.answer("Ответь: сколько часов сидишь суммарно и как часто встаёшь? (например: 9 часов, каждые 45 мин)")
        return

    try:
        numbers = re.findall(r'\d+(?:[.,]\d+)?', sanitized.cleaned_text)
        floats = [float(n.replace(',', '.')) for n in numbers]
        # First number ≤ 24 = hours; remaining numbers = possible break interval in minutes
        hours_candidates = [n for n in floats if n <= 24]
        minutes_candidates = [n for n in floats if n > 24 or (n <= 24 and floats.index(n) > 0)]
        hours = hours_candidates[0] if hours_candidates else -1
        if hours < 0 or hours > 24:
            raise ValueError
        # Break interval: look for minute values (typically 15-120)
        break_minutes = next((n for n in floats if 15 <= n <= 120 and n != hours), None)
    except (ValueError, IndexError):
        await message.answer("Введи число часов от 0 до 24.")
        return

    await state.update_data(sedentary_hours=hours, sedentary_break_minutes=break_minutes)
    await state.set_state(AssessmentStates.ask_blood_work)
    await message.answer(ASSESSMENT_QUESTIONS["ask_blood_work"])


# ── Q10: blood work ────────────────────────────────────────────────────────────

@router.message(AssessmentStates.ask_blood_work)
async def handle_blood_work(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_blood_work"])

    if sanitized.result == "BLOCK":
        await message.answer("Укажи результаты анализов крови — или напиши 'нет'.")
        return

    await state.update_data(blood_work=sanitized.cleaned_text)
    await state.set_state(AssessmentStates.ask_conditions)
    await message.answer(ASSESSMENT_QUESTIONS["ask_conditions"])


# ── Q11: conditions ────────────────────────────────────────────────────────────

@router.message(AssessmentStates.ask_conditions)
async def handle_conditions(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_conditions"])

    if sanitized.result == "BLOCK":
        await message.answer("Укажи хронические заболевания или состояния — или напиши 'нет'.")
        return

    await state.update_data(conditions=sanitized.cleaned_text)
    await state.set_state(AssessmentStates.ask_stress_detail)
    await message.answer(ASSESSMENT_QUESTIONS["ask_stress_detail"])


# ── Q12: stress detail (final) ────────────────────────────────────────────────

@router.message(AssessmentStates.ask_stress_detail)
async def handle_stress_detail(message: Message, state: FSMContext):
    sanitized = await safe_sanitize(message.text, ASSESSMENT_QUESTIONS["ask_stress_detail"])

    if sanitized.result == "BLOCK":
        await message.answer("Расскажи: что тебя стрессует, и как готовишься ко сну?")
        return

    await state.update_data(stress_detail=sanitized.cleaned_text)
    data = await state.get_data()

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        # Detect monthly re-assessment before overwriting fsm_phase
        is_monthly = user.fsm_phase >= 2

        avg_sleep = data.get("avg_sleep", 7.0)
        sleep_variance = data.get("sleep_variance", 0.0)
        morning_energy = data.get("morning_energy", 5)
        brain_fog = data.get("brain_fog", "Иногда")
        sedentary_hours = data.get("sedentary_hours", 6.0)
        sedentary_break_minutes = data.get("sedentary_break_minutes")
        exercise_text = data.get("exercise", "")

        scores = score_deep_assessment(
            avg_sleep=avg_sleep,
            sleep_variance=sleep_variance,
            morning_energy=morning_energy,
            brain_fog=brain_fog,
            sedentary_hours=sedentary_hours,
            stress_level=5,  # neutral; Claude assesses from stress_detail
            exercise_text=exercise_text,
            sedentary_break_minutes=sedentary_break_minutes,
        )

        assessment_data = {
            "age": data.get("age", 0),
            "sex": data.get("sex", ""),
            "occupation": data.get("occupation", ""),
            "substances": data.get("substances", ""),
            "medications": data.get("medications", ""),
            "sleep_text": data.get("sleep_text", ""),
            "avg_sleep": avg_sleep,
            "sleep_variance": sleep_variance,
            "morning_energy": morning_energy,
            "brain_fog": brain_fog,
            "exercise": exercise_text,
            "sedentary_hours": sedentary_hours,
            "sedentary_break_minutes": sedentary_break_minutes,
            "blood_work": data.get("blood_work", ""),
            "conditions": data.get("conditions", ""),
            "stress_detail": sanitized.cleaned_text,
        }

        normalised_scores = normalize_health_scores(scores)

        user.health_scores = normalised_scores
        user.assessment_data = assessment_data
        user.fsm_phase = 2
        user.last_monthly_audit = datetime.utcnow()
        await session.commit()

        user_state = {
            "name": data.get("name", ""),
            "coaching_style": user.coaching_style or "balanced",
            "motivation": user.motivation or "",
            "health_scores": normalised_scores,
            "assessment_data": assessment_data,
            "timezone_name": user.timezone_name,
        }

    await state.clear()

    overall = scores["overall"]
    await message.answer(
        f"*Твои показатели:*\n"
        f"• Сон: {scores['sleep']}/100\n"
        f"• Метаболика: {scores.get('nutrition', scores.get('metabolic', 0))}/100\n"
        f"• Физическая активность: {scores.get('movement', scores.get('physical', 0))}/100\n"
        f"• Ментальное восстановление: {scores['stress']}/100\n"
        f"• *Общий балл: {overall}/100*\n\n"
        f"Анализирую данные...",
        parse_mode="Markdown",
    )

    if is_monthly:
        instruction = (
            "Ежемесячный аудит завершён. Сравни текущие данные с предыдущим ассессментом "
            "(он в assessment_data). Отметь что улучшилось, что ухудшилось, что не изменилось. "
            "Скорректируй приоритеты на следующий месяц. Без воды."
        )
    else:
        instruction = (
            "Ассессмент завершён. Это первичный профиль пользователя. "
            "Проведи корреляционный анализ по принципам Медицины 3.0: оцени стресс из stress_detail, "
            "применяй Stress Filter самостоятельно. Определи главный data gap (что нужно измерить в "
            "первую очередь) и главную 'утечку' (слабейший домен). Свяжи с мотивацией через конкретный "
            "биологический механизм. Учти наличие вредных привычек, лекарств и хронических состояний "
            "в своём анализе."
        )

    brain_output = await safe_claude_call(
        user_state=user_state,
        sanitized_input=None,
        history=[],
        instruction=instruction,
    )

    await message.answer(brain_output.message_to_user)

    # Generate 30-day nudge plan
    from bot.services.claude_brain import generate_nudge_plan
    from datetime import date as date_type
    nudge_plan = await generate_nudge_plan(normalised_scores, assessment_data)
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        u = result.scalar_one_or_none()
        if u:
            u.nudge_plan = nudge_plan
            u.nudge_plan_start = date_type.today()
            await session.commit()

    # Register recurring daily jobs now that assessment is complete
    from bot.services.scheduler import register_daily_jobs
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == str(message.from_user.id))
        )
        user = result.scalar_one_or_none()
        if user:
            register_daily_jobs(str(user.id), user.timezone_name or "UTC", message.bot)
