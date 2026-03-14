"""
Pydantic validators for all AI outputs.
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class SanitizerOutput(BaseModel):
    result: Literal["PASS", "BLOCK"]
    cleaned_text: Optional[str] = None
    reason: Optional[str] = None


class ClaudeNudge(BaseModel):
    nudge_text: str = Field(min_length=10, max_length=500)
    category: Literal["sleep", "nutrition", "movement", "stress"]
    delivery_time: Literal["MORNING", "EVENING"]
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    score_delta: int = Field(default=0, ge=-10, le=10)


class ClaudeReflection(BaseModel):
    question_text: str = Field(min_length=10, max_length=300)
    category: Literal["sleep", "nutrition", "movement", "stress"]


class ClaudeAssessmentResponse(BaseModel):
    acknowledgment: str = Field(min_length=5, max_length=200)
    next_question: Optional[str] = None
    is_complete: bool = False


class ClaireBrainOutput(BaseModel):
    message: str = Field(min_length=5, max_length=1000)
    next_interaction: Optional[ClaudeNudge] = None
    updated_scores: Optional[dict] = None
    phase_transition: Optional[int] = None


class AssessmentRawAnswers(BaseModel):
    sleep_hours: float = Field(ge=0, le=24)
    nutrition_rating: int = Field(ge=1, le=10)
    movement_minutes: int = Field(ge=0, le=1440)
    stress_level: int = Field(ge=0, le=10)
