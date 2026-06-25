"""Tests for ``_feedforward_base`` — the measured-power anchor for fast actuators.

The incremental PD normally increments from the last command (``previous_power``).
For a FAST actuator it re-anchors to the battery's MEASURED power once command and
reality disagree by more than the deadband, so a load shift is tracked in one step
instead of integrated up from a stale assumption. SLOW actuators (Zendure HTTP,
telemetry lags the command by seconds) keep the command anchor. The method is
exercised unbound with a light stub, so no full controller is built.
"""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.omnibattery import ChargeDischargeController
from custom_components.omnibattery.const import FAST_ACTUATOR_MAX_LATENCY_S


def _base(measured, *, previous_power, latency, deadband=40):
    return ChargeDischargeController._feedforward_base(
        SimpleNamespace(
            previous_power=previous_power,
            _actuator_latency_s=latency,
            deadband=deadband,
        ),
        measured,
    )


def test_fast_actuator_reanchors_on_drift():
    # Commanded -500 W, but only -200 W delivered (load shifted): drift 300 W > 40 W
    # deadband → anchor to the measured reality.
    assert _base(-200, previous_power=-500, latency=0.3) == -200


def test_fast_actuator_keeps_command_when_tracking_well():
    # Measured ≈ command (within deadband) → keep the clean command base, no noise.
    assert _base(-490, previous_power=-500, latency=0.3) == -500


def test_slow_actuator_never_reanchors():
    # Zendure-class latency: telemetry lags the ramp, so anchoring would stall.
    assert _base(-200, previous_power=-500, latency=3.0) == -500


def test_falls_back_to_command_when_no_measurement():
    assert _base(None, previous_power=-500, latency=0.3) == -500


def test_boundary_latency_is_fast():
    # Exactly at the threshold counts as fast (<=), so it re-anchors on drift.
    assert _base(0, previous_power=-500, latency=FAST_ACTUATOR_MAX_LATENCY_S) == 0
