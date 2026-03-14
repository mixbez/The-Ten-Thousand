import pytest
from bot.scoring_logic import (
    score_sleep, score_nutrition, score_movement, score_stress,
    calculate_overall_score, score_assessment,
)


class TestScoreSleep:
    def test_optimal_sleep(self):
        assert score_sleep(7.5) == 100

    def test_under_4h(self):
        assert score_sleep(3) == 10

    def test_over_9h(self):
        assert score_sleep(10) == 75

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            score_sleep(-1)

    def test_boundary_7h(self):
        assert score_sleep(7) == 85

    def test_boundary_8h(self):
        assert score_sleep(8) == 100

    def test_exactly_4h(self):
        assert score_sleep(4) == 25

    def test_exactly_5h(self):
        assert score_sleep(5) == 45

    def test_exactly_6h(self):
        assert score_sleep(6) == 65


class TestScoreNutrition:
    def test_perfect(self):
        assert score_nutrition(10) == 100

    def test_minimum(self):
        assert score_nutrition(1) == 10

    def test_mid(self):
        assert score_nutrition(5) == 50

    def test_out_of_range_low(self):
        with pytest.raises(ValueError):
            score_nutrition(0)

    def test_out_of_range_high(self):
        with pytest.raises(ValueError):
            score_nutrition(11)


class TestScoreMovement:
    def test_zero(self):
        assert score_movement(0) == 5

    def test_60_min(self):
        assert score_movement(60) == 85

    def test_90_min(self):
        assert score_movement(90) == 100

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            score_movement(-1)

    def test_10_min(self):
        assert score_movement(10) == 40


class TestScoreStress:
    def test_no_stress(self):
        assert score_stress(0) == 100

    def test_max_stress(self):
        assert score_stress(10) == 5

    def test_out_of_range(self):
        with pytest.raises(ValueError):
            score_stress(11)

    def test_out_of_range_negative(self):
        with pytest.raises(ValueError):
            score_stress(-1)


class TestCalculateOverallScore:
    def test_perfect_scores(self):
        scores = {"sleep": 100, "nutrition": 100, "movement": 100, "stress": 100}
        assert calculate_overall_score(scores) == 100.0

    def test_zero_scores(self):
        scores = {"sleep": 0, "nutrition": 0, "movement": 0, "stress": 0}
        assert calculate_overall_score(scores) == 0.0

    def test_missing_category(self):
        with pytest.raises(ValueError):
            calculate_overall_score({"sleep": 100, "nutrition": 100})

    def test_weighted_average(self):
        scores = {"sleep": 100, "nutrition": 0, "movement": 0, "stress": 0}
        result = calculate_overall_score(scores)
        assert result == 30.0  # sleep weight is 0.30


class TestScoreAssessment:
    def test_full_assessment(self):
        result = score_assessment(7.5, 8, 45, 2)
        assert "sleep" in result
        assert "nutrition" in result
        assert "movement" in result
        assert "stress" in result
        assert "overall" in result
        assert 0 <= result["overall"] <= 100
