"""Characterization tests for the excluded-device load logic.

These pin the *current* behavior of the two excluded-device methods on
ChargeDischargeController before they are extracted into an external_loads
module, so the extraction can be proven to change nothing.

No hardware and no real Home Assistant: the controller is built via __new__
(its real __init__ needs live coordinators) and fed a fake hass whose
``states.get`` returns lightweight state stand-ins. Both methods only read
``config_entry.data`` and ``hass.states``, plus ``previous_power`` for the
charge/discharge branch.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.marstek_venus_energy_manager import ChargeDischargeController


# ----------------------------------------------------------------------
# Test doubles
# ----------------------------------------------------------------------

class _FakeStates:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, entity_id):
        return self._mapping.get(entity_id)


def _state(value, unit="W"):
    """A minimal stand-in for a Home Assistant State object."""
    return SimpleNamespace(state=str(value), attributes={"unit_of_measurement": unit})


def _controller(excluded_devices, states=None, previous_power=0.0):
    ctrl = ChargeDischargeController.__new__(ChargeDischargeController)
    ctrl.config_entry = SimpleNamespace(data={"excluded_devices": excluded_devices})
    ctrl.hass = SimpleNamespace(states=_FakeStates(states or {}))
    ctrl.previous_power = previous_power
    ctrl._excluded_included_adjustment = None
    return ctrl


def _device(**overrides):
    """A telemetry excluded device with sensible defaults; override per test."""
    base = {
        "enabled": True,
        "ev_charger_no_telemetry": False,
        "power_sensor": "sensor.dev",
        "included_in_consumption": True,
        "allow_solar_surplus": False,
    }
    base.update(overrides)
    return base


# ----------------------------------------------------------------------
# _excluded_devices_consumption_delta_kw  (returns kW; W->kW converted)
# ----------------------------------------------------------------------

def test_delta_kw_no_devices_is_zero():
    assert _controller([])._excluded_devices_consumption_delta_kw() == 0.0


def test_delta_kw_included_device_is_subtracted():
    ctrl = _controller([_device(included_in_consumption=True)],
                       {"sensor.dev": _state(500)})
    assert ctrl._excluded_devices_consumption_delta_kw() == pytest.approx(-0.5)


def test_delta_kw_not_included_device_is_added():
    ctrl = _controller([_device(included_in_consumption=False)],
                       {"sensor.dev": _state(500)})
    assert ctrl._excluded_devices_consumption_delta_kw() == pytest.approx(0.5)


def test_delta_kw_kilowatt_unit_not_reconverted():
    ctrl = _controller([_device(included_in_consumption=True)],
                       {"sensor.dev": _state(0.5, unit="kW")})
    assert ctrl._excluded_devices_consumption_delta_kw() == pytest.approx(-0.5)


def test_delta_kw_two_devices_net():
    devices = [
        _device(power_sensor="sensor.a", included_in_consumption=True),
        _device(power_sensor="sensor.b", included_in_consumption=False),
    ]
    ctrl = _controller(devices,
                       {"sensor.a": _state(500), "sensor.b": _state(200)})
    # -0.5 (subtracted) + 0.2 (added)
    assert ctrl._excluded_devices_consumption_delta_kw() == pytest.approx(-0.3)


@pytest.mark.parametrize("device, states", [
    (_device(enabled=False), {"sensor.dev": _state(500)}),
    (_device(ev_charger_no_telemetry=True), {"sensor.dev": _state(500)}),
    (_device(power_sensor=None), {}),
    (_device(), {"sensor.dev": _state("unavailable")}),
    (_device(), {}),  # sensor missing entirely
])
def test_delta_kw_skips_unusable_devices(device, states):
    assert _controller([device], states)._excluded_devices_consumption_delta_kw() == 0.0


# ----------------------------------------------------------------------
# _calculate_excluded_devices_adjustment  (returns W; NO unit conversion)
# Positive = reduce battery discharge, negative = increase it.
# ----------------------------------------------------------------------

def test_adjustment_no_devices_is_zero_and_resets_included():
    ctrl = _controller([])
    assert ctrl._calculate_excluded_devices_adjustment(0.0) == 0.0
    assert ctrl._excluded_included_adjustment == 0.0


def test_adjustment_included_no_surplus_subtracts():
    ctrl = _controller([_device(included_in_consumption=True, allow_solar_surplus=False)],
                       {"sensor.dev": _state(500)})
    assert ctrl._calculate_excluded_devices_adjustment(0.0) == pytest.approx(500.0)
    assert ctrl._excluded_included_adjustment == pytest.approx(500.0)


def test_adjustment_not_included_adds_discharge():
    ctrl = _controller([_device(included_in_consumption=False)],
                       {"sensor.dev": _state(500)})
    assert ctrl._calculate_excluded_devices_adjustment(0.0) == pytest.approx(-500.0)
    assert ctrl._excluded_included_adjustment == pytest.approx(0.0)


def test_adjustment_solar_surplus_while_charging_is_neutral():
    # included + allow_solar_surplus + charging (previous_power >= 0) -> no adjustment
    ctrl = _controller(
        [_device(included_in_consumption=True, allow_solar_surplus=True)],
        {"sensor.dev": _state(500)},
        previous_power=100.0,
    )
    assert ctrl._calculate_excluded_devices_adjustment(0.0) == pytest.approx(0.0)
    assert ctrl._excluded_included_adjustment == pytest.approx(0.0)


def test_adjustment_solar_surplus_while_discharging_full_exclusion():
    # included + allow_solar_surplus + discharging (previous_power < 0) -> subtract
    ctrl = _controller(
        [_device(included_in_consumption=True, allow_solar_surplus=True)],
        {"sensor.dev": _state(500)},
        previous_power=-100.0,
    )
    assert ctrl._calculate_excluded_devices_adjustment(0.0) == pytest.approx(500.0)
    assert ctrl._excluded_included_adjustment == pytest.approx(500.0)


@pytest.mark.parametrize("device", [
    _device(enabled=False),
    _device(ev_charger_no_telemetry=True),
    _device(power_sensor=None),
])
def test_adjustment_skips_unusable_devices(device):
    ctrl = _controller([device], {"sensor.dev": _state(500)})
    assert ctrl._calculate_excluded_devices_adjustment(0.0) == 0.0
