"""Regression tests for peak-shaving conservation decisions.

When SOC is below the peak-shaving threshold, a below-limit household load
must leave the battery idle. The old logic stopped an existing discharge but
kept an existing charge command alive by moving the target to the current grid
reading, producing a zero PD error that latched the charge indefinitely.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.omnibattery import ChargeDischargeController


def _controller(*, previous_power: float):
    ctrl = object.__new__(ChargeDischargeController)
    ctrl.capacity_protection_enabled = True
    ctrl.capacity_protection_soc_threshold = 25
    ctrl.capacity_protection_limit = 3000
    ctrl.coordinators = [SimpleNamespace(data={"battery_soc": 24})]
    ctrl.previous_power = previous_power
    ctrl._excluded_included_adjustment = 0.0
    ctrl._setpoint_offsets = {"user_target": 0.0}
    ctrl._setpoint_overrides = {}
    ctrl._capacity_protection_active = False
    ctrl._capacity_protection_force_idle = False
    ctrl._capacity_protection_status = {}
    return ctrl


@pytest.mark.parametrize("previous_power", [10.1, -500.0])
def test_conserving_stops_any_existing_battery_command(previous_power):
    ctrl = _controller(previous_power=previous_power)
    # Keep the reconstructed household load at 321.4 W for either command sign.
    grid_power = 321.4 + previous_power

    target, sensor = ctrl._apply_capacity_protection(grid_power, active_target=0.0)

    assert sensor == pytest.approx(grid_power)
    assert target == pytest.approx(grid_power)
    assert ctrl._capacity_protection_force_idle is True
    assert ctrl._capacity_protection_status["action"] == "conserving"


def test_conserving_idle_does_not_request_redundant_stop():
    ctrl = _controller(previous_power=0.0)

    ctrl._apply_capacity_protection(321.4, active_target=0.0)

    assert ctrl._capacity_protection_force_idle is False
    assert ctrl._capacity_protection_status["action"] == "conserving"


def test_solar_surplus_charge_remains_allowed():
    ctrl = _controller(previous_power=10.1)
    # Grid - battery charge = -100 W: genuine surplus remains after serving the house.
    grid_power = -89.9

    target, sensor = ctrl._apply_capacity_protection(grid_power, active_target=0.0)

    assert sensor == pytest.approx(grid_power)
    assert target == 0.0
    assert ctrl._capacity_protection_force_idle is False
    assert ctrl._capacity_protection_status["action"] == "charging"
