"""
Health score calculation logic.
Tier 1: Must have 100% unit test coverage.
"""
from typing import Dict


CATEGORY_WEIGHTS = {
    "sleep": 0.30,
    "nutrition": 0.25,
    "movement": 0.25,
    "stress": 0.20,
}

SLEEP_SCORE_MAP = {
    (0, 4): 10,
    (4, 5): 25,
    (5, 6): 45,
    (6, 7): 65,
    (7, 7.5): 85,
    (7.5, 9): 100,
    (9, 999): 75,  # too much sleep also penalized
}

STRESS_SCORE_MAP = {
    (0, 2): 100,
    (2, 4): 85,
    (4, 6): 65,
    (6, 8): 40,
    (8, 10): 15,
    (10, 11): 5,
}


def score_sleep(hours: float) -> int:
    """Score sleep quality. 7-8h = 100. <4h or >9h = penalized."""
    if hours < 0:
        raise ValueError("Sleep hours cannot be negative")
    for (low, high), score in SLEEP_SCORE_MAP.items():
        if low <= hours < high:
            return score
    return 10


def score_nutrition(rating: int) -> int:
    """Score nutrition based on self-reported 1-10 rating."""
    if not 1 <= rating <= 10:
        raise ValueError("Nutrition rating must be between 1 and 10")
    return min(100, rating * 10)


def score_movement(minutes: int) -> int:
    """Score movement based on active minutes per day."""
    if minutes < 0:
        raise ValueError("Movement minutes cannot be negative")
    if minutes == 0:
        return 5
    if minutes < 10:
        return 20
    if minutes < 20:
        return 40
    if minutes < 30:
        return 60
    if minutes < 45:
        return 75
    if minutes <= 60:
        return 85
    if minutes < 90:
        return 95
    return 100


def score_stress(level: int) -> int:
    """Score stress level (0=no stress, 10=extreme stress)."""
    if not 0 <= level <= 10:
        raise ValueError("Stress level must be between 0 and 10")
    for (low, high), score in STRESS_SCORE_MAP.items():
        if low <= level < high:
            return score
    return 5


def calculate_overall_score(category_scores: Dict[str, int]) -> float:
    """Calculate weighted overall health score."""
    required = {"sleep", "nutrition", "movement", "stress"}
    missing = required - set(category_scores.keys())
    if missing:
        raise ValueError(f"Missing categories: {missing}")

    total = sum(
        category_scores[cat] * weight
        for cat, weight in CATEGORY_WEIGHTS.items()
    )
    return round(total, 2)


def score_assessment(sleep_hours: float, nutrition_rating: int,
                     movement_minutes: int, stress_level: int) -> Dict[str, float]:
    """Full assessment scoring. Returns per-category and overall scores."""
    scores = {
        "sleep": score_sleep(sleep_hours),
        "nutrition": score_nutrition(nutrition_rating),
        "movement": score_movement(movement_minutes),
        "stress": score_stress(stress_level),
    }
    scores["overall"] = calculate_overall_score(scores)
    return scores
