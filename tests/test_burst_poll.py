"""Tests for the transient burst-poll boost (infra/coordinator.py).

Right after the control loop writes a REAL power command change, the delivered-
power reading (ac_power / battery_power) should refresh faster for a few
seconds so ``_measured_battery_power()`` isn't stale during the actuator ramp.
``group_scan_interval_s`` is the pure function the poll loop consults each
cycle; ``start_burst_poll`` / ``_set_battery_power`` wire it up.

No freezegun: timestamps are plain ``time.monotonic()`` floats manipulated
directly, per repo convention (HA's dt_util can't be frozen by freezegun).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.omnibattery import ChargeDischargeController
from custom_components.omnibattery.const import (
    BURST_POLL_INTERVAL_S,
    BURST_POLL_WINDOW_S,
    SCAN_INTERVAL,
)
from custom_components.omnibattery.drivers import SetpointResult
from custom_components.omnibattery.infra.coordinator import group_scan_interval_s
from tests.conftest import FakeCoordinator
from tests.test_set_battery_power_skip import _controller


NOMINAL = SCAN_INTERVAL["high"]


def test_delivered_power_group_boosted_within_window():
    """Within the burst window, a group carrying ac_power polls at the boosted cadence."""
    now = 100.0
    boost_until = now + 3.0  # still inside the window

    assert group_scan_interval_s(("ac_power",), NOMINAL, boost_until, now) == (
        BURST_POLL_INTERVAL_S
    )


def test_delivered_power_group_reverts_after_window():
    """Once the window has elapsed, the group falls back to its nominal interval."""
    now = 100.0
    boost_until = now - 0.001  # window already expired

    assert group_scan_interval_s(("ac_power",), NOMINAL, boost_until, now) == NOMINAL


def test_unrelated_group_is_never_boosted():
    """A group without a delivered-power key is unaffected even inside the window."""
    now = 100.0
    boost_until = now + 3.0

    assert group_scan_interval_s(
        ("battery_soc",), NOMINAL, boost_until, now
    ) == NOMINAL


def test_battery_power_key_also_boosted():
    """battery_power (Zendure's fallback delivered-power key) is boosted too."""
    now = 100.0
    boost_until = now + 3.0

    assert group_scan_interval_s(("battery_power",), NOMINAL, boost_until, now) == (
        BURST_POLL_INTERVAL_S
    )


def test_no_boost_armed_defaults_to_nominal():
    now = 100.0
    assert group_scan_interval_s(("ac_power",), NOMINAL, 0.0, now) == NOMINAL


async def test_real_write_arms_burst_poll():
    """A real write that changes the commanded power arms the coordinator's boost."""
    coord = FakeCoordinator(
        name="BAT1",
        is_available=True,
        rs485_user_disabled=False,
        balance_hold=False,
        min_soc=10,
        data={"force_mode": 0, "set_charge_power": 0, "set_discharge_power": 0},
        apply_power=AsyncMock(
            return_value=SetpointResult(ok=True, net_power_w=-300, confirmed=True, battery_power_w=-300)
        ),
    )
    ctrl = _controller()

    assert coord.boost_fast_poll_until == 0.0

    await ChargeDischargeController._set_battery_power(ctrl, coord, 0, 300)

    assert coord.boost_fast_poll_until > 0.0


async def test_skip_if_unchanged_does_not_arm_burst_poll():
    """The skip-if-unchanged path (no real write) must not arm the boost."""
    coord = FakeCoordinator(
        name="BAT1",
        is_available=True,
        rs485_user_disabled=False,
        balance_hold=False,
        min_soc=10,
        data={"force_mode": 0, "set_charge_power": 0, "set_discharge_power": 0},
        apply_power=AsyncMock(),
    )
    ctrl = _controller()

    result = await ChargeDischargeController._set_battery_power(ctrl, coord, 0, 0)

    assert result is True
    coord.apply_power.assert_not_called()
    assert coord.boost_fast_poll_until == 0.0


def test_start_burst_poll_window_matches_constant():
    """The coordinator method arms exactly BURST_POLL_WINDOW_S ahead of now."""
    coord = FakeCoordinator()
    import time

    before = time.monotonic()
    coord.start_burst_poll()
    after = time.monotonic()

    assert before + BURST_POLL_WINDOW_S <= coord.boost_fast_poll_until <= after + BURST_POLL_WINDOW_S
