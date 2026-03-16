"""
Compact context builder — minimal but high-signal context for Claude.
Builds base (scores + medical) + domain-specific fields + interaction history.
"""
from datetime import date
from typing import Dict, List, Optional
from bot.db.models import Interaction


DOMAIN_FIELDS = {
    "sleep":     ("sleep_text", "sleep_variance", "morning_energy"),
    "mental_recovery": ("stress_detail",),
    "metabolic": ("blood_work", "substances", "brain_fog"),
    "physical":  ("exercise", "sedentary_hours"),
    "medical":   ("blood_work", "conditions", "medications"),
}


def get_today_domain(user) -> str:
    """Pick today's focus domain from nudge_plan, falling back to weakest score."""
    from bot.scoring_logic import normalize_health_scores

    plan = user.nudge_plan
    start = user.nudge_plan_start

    if plan and start:
        day_offset = (date.today() - start).days
        return plan[day_offset % len(plan)]

    # Fallback: weakest domain
    scores = normalize_health_scores(user.health_scores or {})
    domain_scores = {k: v for k, v in scores.items()
                     if k in ("sleep", "metabolic", "physical", "mental_recovery")}
    if domain_scores:
        return min(domain_scores, key=domain_scores.get)
    return "sleep"


def build_context(
    user_state: Dict,
    domain: str,
    recent_interactions: List[Interaction],
    instruction: str,
    sanitized_input: Optional[str] = None,
) -> str:
    ad = user_state.get("assessment_data", {})
    hs = user_state.get("health_scores", {})
    sex_short = "м" if "муж" in str(ad.get("sex", "")).lower() else "ж"

    parts = [
        f"scores: sleep={hs.get('sleep','?')} meta={hs.get('metabolic','?')} "
        f"phys={hs.get('physical','?')} mr={hs.get('mental_recovery','?')} medical={hs.get('medical','?')} total={hs.get('overall','?')}",
        f"u: {ad.get('age','?')}{sex_short} | style: {user_state.get('coaching_style','balanced')} | goal: {user_state.get('motivation','')}",
        f"rx: {ad.get('medications','—')} | dx: {ad.get('conditions','—')}",
        f"focus: {domain}",
    ]

    # Domain-specific fields
    fields = DOMAIN_FIELDS.get(domain, ())
    domain_parts = [f"{f}: {ad[f]}" for f in fields if ad.get(f) not in (None, "")]
    if domain_parts:
        parts.append(" | ".join(domain_parts))

    # Interaction history (last 5)
    if recent_interactions:
        today = date.today()
        hist = []
        for i in recent_interactions:
            days_ago = (today - i.created_at.date()).days
            label = "сегодня" if days_ago == 0 else f"d-{days_ago}"
            if i.responded_at:
                status = "✓" if i.completed else "✗"
            else:
                status = "?"
            text_short = (i.nudge_text or "")[:70].replace("\n", " ")
            hist.append(f"  {label} [{i.category or '?'}] \"{text_short}\" → {status}")
        parts.append("history:\n" + "\n".join(hist))

    parts.append(f"instruction: {instruction}")
    if sanitized_input:
        parts.append(f"user_input: {sanitized_input}")

    return "\n".join(parts)
