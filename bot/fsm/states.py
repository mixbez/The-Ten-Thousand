from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    ask_name = State()
    ask_coaching_style = State()
    ask_motivation = State()
    ask_commitment = State()


class AssessmentStates(StatesGroup):
    ask_sleep_consistency = State()
    ask_morning_energy = State()
    ask_brain_fog = State()
    ask_sedentary = State()
    ask_stress_detail = State()
    ask_supplements = State()
    calculating = State()


class DailyLoopStates(StatesGroup):
    morning_nudge_sent = State()
    awaiting_evening_reflection = State()
    awaiting_nudge_feedback = State()


class MonthlyAuditStates(StatesGroup):
    in_progress = State()
