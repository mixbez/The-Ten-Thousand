"""
Pydantic validators for all AI outputs.
"""
from typing import Optional, Literal, List
from pydantic import BaseModel, Field


class SanitizerOutput(BaseModel):
    result: Literal["PASS", "BLOCK"]
    cleaned_text: Optional[str] = None
    reason: Optional[str] = None


class NextInteraction(BaseModel):
    type: Literal["ACTION", "NUDGE", "REFLECTION", "ASSESSMENT"]
    content: str = Field(min_length=5, max_length=1000)
    schedule_tag: Literal["MORNING", "EVENING", "IMMEDIATE"]
    medical_flag: bool = False


class InternalAnalysis(BaseModel):
    detected_risks: List[str] = []
    data_gaps: List[str] = []
    logic_chain: str = ""


class LongevityBrainOutput(BaseModel):
    internal_analysis: Optional[InternalAnalysis] = None
    updated_scores: Optional[dict] = None
    message_to_user: str = Field(min_length=5, max_length=2000)
    next_interaction: Optional[NextInteraction] = None


# Backward-compat alias
class ClaudeNudge(BaseModel):
    nudge_text: str = Field(min_length=10, max_length=500)
    category: Literal["sleep", "nutrition", "movement", "stress", "energy"]
    delivery_time: Literal["MORNING", "EVENING"]
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    score_delta: int = Field(default=0, ge=-10, le=10)


class AssessmentRawAnswers(BaseModel):
    sleep_hours: float = Field(ge=0, le=24)
    nutrition_rating: int = Field(ge=1, le=10)
    movement_minutes: int = Field(ge=0, le=1440)
    stress_level: int = Field(ge=0, le=10)
