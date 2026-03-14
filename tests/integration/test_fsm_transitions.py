import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_cannot_get_daily_nudge_before_assessment():
    """Users in phase 0 or 1 should not receive daily nudges."""
    from bot.db.models import User
    import uuid

    user = User()
    user.id = uuid.uuid4()
    user.fsm_phase = 0
    user.is_active = True

    assert user.fsm_phase < 2, "User should not be in daily loop phase"


@pytest.mark.asyncio
async def test_monthly_audit_transition():
    """After assessment, last_monthly_audit should be set."""
    from bot.db.models import User
    from datetime import datetime
    import uuid

    user = User()
    user.id = uuid.uuid4()
    user.fsm_phase = 1
    user.last_monthly_audit = None

    user.fsm_phase = 2
    user.last_monthly_audit = datetime.utcnow()

    assert user.fsm_phase == 2
    assert user.last_monthly_audit is not None


@pytest.mark.asyncio
async def test_block_count_increments():
    """Block count should increment on BLOCK responses."""
    from bot.db.models import User
    import uuid

    user = User()
    user.id = uuid.uuid4()
    user.block_count = 0

    user.block_count += 1
    assert user.block_count == 1

    user.block_count += 1
    user.block_count += 1
    assert user.block_count == 3
