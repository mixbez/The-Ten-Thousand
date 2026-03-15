"""
Health score calculation logic.
Tier 1: Must have 100% unit test coverage.
"""
from typing import Dict


CATEGORY_WEIGHTS = {
    "sleep": 0.25,
    "energy": 0.15,
    "nutrition": 0.20,
    "movement": 0.20,
    "stress": 0.20,
}

SLEEP_SCORE_MAP = {
    (0, 4): 10,
    (4, 5): 25,
    (5, 6): 45,
    (6, 7): 65,
    (7, 7.5): 85,
    (7.5, 9): 100,
    (9, 999): 75,
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


def score_sleep_consistency(avg_hours: float, variance: float) -> int:
    """Score sleep based on average AND consistency. High variance = penalty."""
    if avg_hours < 0:
        raise ValueError("Sleep hours cannot be negative")
    if variance < 0:
        raise ValueError("Variance cannot be negative")
    base = score_sleep(avg_hours)
    if variance > 4:
        penalty = 30
    elif variance > 2:
        penalty = 15
    elif variance > 1:
        penalty = 5
    else:
        penalty = 0
    return max(0, base - penalty)


def score_morning_energy(rating: int) -> int:
    """Score morning energy on 1-10 scale."""
    if not 1 <= rating <= 10:
        raise ValueError("Morning energy rating must be between 1 and 10")
    return min(100, rating * 10)


def score_brain_fog(frequency: str) -> int:
    """Score nutrition proxy via brain fog/energy crash frequency."""
    freq = frequency.lower().strip()
    if any(w in freq for w in ("никогда", "never", "нет")):
        return 100
    elif any(w in freq for w in ("иногда", "sometimes", "редко")):
        return 55
    elif any(w in freq for w in ("каждый", "каждый день", "daily", "постоянно")):
        return 10
    return 55


def score_sedentary(hours: float) -> int:
    """Score movement proxy via sedentary hours (inverted — less sitting = better)."""
    if hours < 0:
        raise ValueError("Sedentary hours cannot be negative")
    if hours <= 2:
        return 100
    elif hours <= 4:
        return 80
    elif hours <= 6:
        return 55
    elif hours <= 8:
        return 30
    elif hours <= 10:
        return 15
    return 5


def score_nutrition(rating: int) -> int:
    """Score nutrition based on self-reported 1-10 rating (kept for backward compat)."""
    if not 1 <= rating <= 10:
        raise ValueError("Nutrition rating must be between 1 and 10")
    return min(100, rating * 10)


def score_movement(minutes: int) -> int:
    """Score movement based on active minutes per day (kept for backward compat)."""
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
    """Calculate weighted overall health score from deep assessment categories."""
    required = {"sleep", "energy", "nutrition", "movement", "stress"}
    missing = required - set(category_scores.keys())
    if missing:
        raise ValueError(f"Missing categories: {missing}")
    total = sum(
        category_scores[cat] * weight
        for cat, weight in CATEGORY_WEIGHTS.items()
    )
    return round(total, 2)


def score_deep_assessment(
    avg_sleep: float,
    sleep_variance: float,
    morning_energy: int,
    brain_fog: str,
    sedentary_hours: float,
    stress_level: int,
) -> Dict[str, float]:
    """Full deep assessment scoring. Returns per-category and overall scores."""
    scores = {
        "sleep": score_sleep_consistency(avg_sleep, sleep_variance),
        "energy": score_morning_energy(morning_energy),
        "nutrition": score_brain_fog(brain_fog),
        "movement": score_sedentary(sedentary_hours),
        "stress": score_stress(stress_level),
    }
    scores["overall"] = calculate_overall_score(scores)
    return scores


def score_assessment(sleep_hours: float, nutrition_rating: int,
                     movement_minutes: int, stress_level: int) -> Dict[str, float]:
    """Legacy assessment scoring for backward compatibility."""
    scores = {
        "sleep": score_sleep(sleep_hours),
        "nutrition": score_nutrition(nutrition_rating),
        "movement": score_movement(movement_minutes),
        "stress": score_stress(stress_level),
    }
    legacy_weights = {"sleep": 0.30, "nutrition": 0.25, "movement": 0.25, "stress": 0.20}
    scores["overall"] = round(sum(scores[c] * w for c, w in legacy_weights.items()), 2)
    return scores


# v1.3 domain names: sleep / metabolic / physical / mental_recovery
DOMAIN_WEIGHTS_V13 = {
    "sleep": 0.35,
    "metabolic": 0.25,
    "physical": 0.20,
    "mental_recovery": 0.20,
}


def normalize_health_scores(scores: Dict) -> Dict:
    """
    Map any legacy score format to v1.3 domain names.
    Idempotent — already-normalised scores are returned as-is.
    """
    if not scores:
        return {}

    # Already in v1.3 format
    if "metabolic" in scores and "physical" in scores and "mental_recovery" in scores:
        return scores

    normalised: Dict = {}

    # sleep is the same in all versions
    normalised["sleep"] = scores.get("sleep", 0)

    # metabolic ← nutrition (v1.1) or nutrition proxy
    normalised["metabolic"] = scores.get("nutrition", scores.get("metabolic", 0))

    # physical ← movement (v1.1)
    normalised["physical"] = scores.get("movement", scores.get("physical", 0))

    # mental_recovery ← average of stress + energy (v1.1), or stress alone
    stress = scores.get("stress", 0)
    energy = scores.get("energy", stress)
    normalised["mental_recovery"] = round((stress + energy) / 2)

    # preserve overall and biological_age_estimate if present
    if "overall" in scores:
        normalised["overall"] = scores["overall"]
    if "biological_age_estimate" in scores:
        normalised["biological_age_estimate"] = scores["biological_age_estimate"]

    return normalised


def calculate_overall_score_v13(domain_scores: Dict[str, int]) -> float:
    """Weighted overall score using v1.3 domain weights (Sleep 35%, etc.)."""
    required = set(DOMAIN_WEIGHTS_V13.keys())
    missing = required - set(domain_scores.keys())
    if missing:
        raise ValueError(f"Missing domains: {missing}")
    return round(sum(domain_scores[d] * w for d, w in DOMAIN_WEIGHTS_V13.items()), 2)
