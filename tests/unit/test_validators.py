import pytest
from pydantic import ValidationError
from bot.validators import (
    SanitizerOutput, ClaudeNudge, ClaireBrainOutput, AssessmentRawAnswers
)


class TestSanitizerOutput:
    def test_pass_result(self):
        obj = SanitizerOutput(result="PASS", cleaned_text="7 hours")
        assert obj.result == "PASS"

    def test_block_result(self):
        obj = SanitizerOutput(result="BLOCK", reason="off-topic")
        assert obj.result == "BLOCK"

    def test_invalid_result(self):
        with pytest.raises(ValidationError):
            SanitizerOutput(result="UNKNOWN")


class TestClaudeNudge:
    def test_valid_nudge(self):
        nudge = ClaudeNudge(
            nudge_text="Drink a glass of water before breakfast.",
            category="nutrition",
            delivery_time="MORNING",
        )
        assert nudge.category == "nutrition"

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            ClaudeNudge(
                nudge_text="Do something",
                category="invalid",
                delivery_time="MORNING",
            )

    def test_short_nudge_text(self):
        with pytest.raises(ValidationError):
            ClaudeNudge(nudge_text="Hi", category="sleep", delivery_time="MORNING")


class TestAssessmentRawAnswers:
    def test_valid(self):
        obj = AssessmentRawAnswers(
            sleep_hours=7.5, nutrition_rating=8, movement_minutes=30, stress_level=3
        )
        assert obj.sleep_hours == 7.5

    def test_invalid_sleep(self):
        with pytest.raises(ValidationError):
            AssessmentRawAnswers(
                sleep_hours=25, nutrition_rating=8, movement_minutes=30, stress_level=3
            )
