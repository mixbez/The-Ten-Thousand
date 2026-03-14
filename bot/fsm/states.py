from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    ask_name = State()
    ask_coaching_style = State()
    ask_motivation = State()
    ask_commitment = State()


class AssessmentStates(StatesGroup):
    ask_sleep = State()
    ask_nutrition = State()
    ask_movement = State()
    ask_stress = State()
    calculating = State()


class DailyLoopStates(StatesGroup):
    morning_nudge_sent = State()
    awaiting_evening_reflection = State()
    awaiting_nudge_feedback = State()


class MonthlyAuditStates(StatesGroup):
    in_progress = State()
