from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    ask_name = State()
    ask_coaching_style = State()
    ask_motivation = State()
    ask_commitment = State()


class AssessmentStates(StatesGroup):
    ask_age_sex = State()
    ask_occupation = State()
    ask_substances = State()
    ask_medications = State()
    ask_sleep_consistency = State()
    ask_morning_energy = State()
    ask_brain_fog = State()
    ask_exercise = State()
    ask_sedentary = State()
    ask_blood_work = State()
    ask_conditions = State()
    ask_stress_detail = State()


class DailyLoopStates(StatesGroup):
    morning_nudge_sent = State()
    awaiting_evening_reflection = State()
    awaiting_nudge_feedback = State()


class MonthlyAuditStates(StatesGroup):
    in_progress = State()
