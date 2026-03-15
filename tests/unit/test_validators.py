import pytest
from pydantic import ValidationError
from bot.validators import (
    SanitizerOutput, ClaudeNudge, LongevityBrainOutput, NextInteraction,
    InternalAnalysis, AssessmentRawAnswers
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
            nudge_text="Выпей стакан воды перед завтраком.",
            category="nutrition",
            delivery_time="MORNING",
        )
        assert nudge.category == "nutrition"

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            ClaudeNudge(
                nudge_text="Сделай что-нибудь",
                category="invalid",
                delivery_time="MORNING",
            )

    def test_short_nudge_text(self):
        with pytest.raises(ValidationError):
            ClaudeNudge(nudge_text="Привет", category="sleep", delivery_time="MORNING")


class TestLongevityBrainOutput:
    def test_valid_output(self):
        obj = LongevityBrainOutput(
            message_to_user="Постпрандиальная гипергликемия блокирует аутофагию.",
            next_interaction=NextInteraction(
                type="ACTION",
                content="Сдай анализ: глюкоза + инсулин натощак.",
                schedule_tag="MORNING",
                medical_flag=True,
            ),
        )
        assert obj.next_interaction.medical_flag is True

    def test_with_internal_analysis(self):
        obj = LongevityBrainOutput(
            internal_analysis=InternalAnalysis(
                detected_risks=["Инсулинорезистентность"],
                data_gaps=["HOMA-IR", "ApoB"],
                logic_chain="HOMA-IR > 1.5 коррелирует с висцеральным жиром.",
            ),
            message_to_user="Нужен анализ.",
        )
        assert "HOMA-IR" in obj.internal_analysis.data_gaps

    def test_message_required(self):
        with pytest.raises(ValidationError):
            LongevityBrainOutput()

    def test_invalid_schedule_tag(self):
        with pytest.raises(ValidationError):
            NextInteraction(type="ACTION", content="Что-то сделай", schedule_tag="AFTERNOON")

    def test_no_next_interaction(self):
        obj = LongevityBrainOutput(message_to_user="Данные получены.")
        assert obj.next_interaction is None

    def test_internal_analysis_defaults(self):
        ia = InternalAnalysis()
        assert ia.detected_risks == []
        assert ia.data_gaps == []
        assert ia.logic_chain == ""


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
