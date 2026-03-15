import pytest
from bot.scoring_logic import (
    score_sleep, score_nutrition, score_movement, score_stress,
    score_sleep_consistency, score_morning_energy, score_brain_fog, score_sedentary,
    calculate_overall_score, score_assessment, score_deep_assessment,
    normalize_health_scores, calculate_overall_score_v13,
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
        scores = {"sleep": 100, "energy": 100, "nutrition": 100, "movement": 100, "stress": 100}
        assert calculate_overall_score(scores) == 100.0

    def test_zero_scores(self):
        scores = {"sleep": 0, "energy": 0, "nutrition": 0, "movement": 0, "stress": 0}
        assert calculate_overall_score(scores) == 0.0

    def test_missing_category(self):
        with pytest.raises(ValueError):
            calculate_overall_score({"sleep": 100, "nutrition": 100})

    def test_weighted_average(self):
        scores = {"sleep": 100, "energy": 0, "nutrition": 0, "movement": 0, "stress": 0}
        result = calculate_overall_score(scores)
        assert result == 25.0  # sleep weight is 0.25


class TestScoreAssessment:
    def test_full_assessment(self):
        result = score_assessment(7.5, 8, 45, 2)
        assert "sleep" in result
        assert "nutrition" in result
        assert "movement" in result
        assert "stress" in result
        assert "overall" in result
        assert 0 <= result["overall"] <= 100


class TestScoreSleepConsistency:
    def test_stable_good_sleep(self):
        assert score_sleep_consistency(7.5, 0.5) == 100

    def test_good_avg_high_variance(self):
        score = score_sleep_consistency(7.5, 5.0)
        assert score == 70  # 100 - 30 penalty

    def test_medium_variance(self):
        score = score_sleep_consistency(7.5, 2.5)
        assert score == 85  # 100 - 15

    def test_small_variance(self):
        score = score_sleep_consistency(7.5, 1.5)
        assert score == 95  # 100 - 5

    def test_negative_hours_raises(self):
        with pytest.raises(ValueError):
            score_sleep_consistency(-1, 0)

    def test_negative_variance_raises(self):
        with pytest.raises(ValueError):
            score_sleep_consistency(7, -1)


class TestScoreMorningEnergy:
    def test_max_energy(self):
        assert score_morning_energy(10) == 100

    def test_min_energy(self):
        assert score_morning_energy(1) == 10

    def test_mid_energy(self):
        assert score_morning_energy(5) == 50

    def test_out_of_range_low(self):
        with pytest.raises(ValueError):
            score_morning_energy(0)

    def test_out_of_range_high(self):
        with pytest.raises(ValueError):
            score_morning_energy(11)


class TestScoreBrainFog:
    def test_never(self):
        assert score_brain_fog("Никогда") == 100

    def test_sometimes(self):
        assert score_brain_fog("Иногда") == 55

    def test_daily(self):
        assert score_brain_fog("Каждый день") == 10

    def test_english_never(self):
        assert score_brain_fog("never") == 100

    def test_unknown_defaults_to_sometimes(self):
        assert score_brain_fog("не знаю") == 55


class TestScoreSedentary:
    def test_very_active(self):
        assert score_sedentary(1) == 100

    def test_moderate(self):
        assert score_sedentary(5) == 55

    def test_desk_job(self):
        assert score_sedentary(8) == 30

    def test_extreme(self):
        assert score_sedentary(12) == 5

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            score_sedentary(-1)


class TestScoreDeepAssessment:
    def test_full_deep_assessment(self):
        result = score_deep_assessment(7.5, 0.5, 8, "Никогда", 3.0, 2)
        assert "sleep" in result
        assert "energy" in result
        assert "nutrition" in result
        assert "movement" in result
        assert "stress" in result
        assert "overall" in result
        assert 0 <= result["overall"] <= 100

    def test_worst_case(self):
        result = score_deep_assessment(3.0, 8.0, 1, "Каждый день", 12.0, 10)
        assert result["overall"] < 30


class TestNormalizeHealthScores:
    def test_legacy_v11_format(self):
        old = {"sleep": 80, "energy": 60, "nutrition": 55, "movement": 30, "stress": 65, "overall": 59.5}
        result = normalize_health_scores(old)
        assert "metabolic" in result
        assert "physical" in result
        assert "mental_recovery" in result
        assert result["sleep"] == 80
        assert result["metabolic"] == 55   # from nutrition
        assert result["physical"] == 30    # from movement
        assert result["mental_recovery"] == 62  # avg(stress=65, energy=60)

    def test_already_v13_format(self):
        v13 = {"sleep": 80, "metabolic": 60, "physical": 70, "mental_recovery": 75}
        result = normalize_health_scores(v13)
        assert result == v13

    def test_empty_scores(self):
        assert normalize_health_scores({}) == {}

    def test_preserves_overall(self):
        old = {"sleep": 80, "energy": 60, "nutrition": 55, "movement": 30, "stress": 65, "overall": 59.5}
        result = normalize_health_scores(old)
        assert result["overall"] == 59.5


class TestCalculateOverallScoreV13:
    def test_perfect(self):
        scores = {"sleep": 100, "metabolic": 100, "physical": 100, "mental_recovery": 100}
        assert calculate_overall_score_v13(scores) == 100.0

    def test_weights(self):
        # sleep=100 at 35%, rest=0 → 35.0
        scores = {"sleep": 100, "metabolic": 0, "physical": 0, "mental_recovery": 0}
        assert calculate_overall_score_v13(scores) == 35.0

    def test_missing_domain_raises(self):
        with pytest.raises(ValueError):
            calculate_overall_score_v13({"sleep": 100})
