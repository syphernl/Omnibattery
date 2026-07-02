"""Tests for the adaptive collapse in ``_filter_grid_sample`` (__init__.py).

The grid-sample EMA exists to smooth sensor noise (tens of W), not to delay a
genuine load step (a kettle/EV charger swinging kW). A deviation from the
current EMA state larger than ``max(3 * deadband, 200W)`` is treated as a real
step and passed through immediately (alpha = 1) instead of blended in over
several seconds.

The method is exercised unbound with a light ``SimpleNamespace`` stub for
``self``, matching the pattern in ``test_set_battery_power_skip.py``.
"""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.omnibattery import ChargeDischargeController


def _controller(*, deadband=40, tau=2.0, dt=2.0, ema=None):
    return SimpleNamespace(
        deadband=deadband,
        _grid_filter_tau=tau,
        dt=dt,
        _grid_filter_ema=ema,
    )


def test_small_deviation_is_smoothed():
    """A deviation within the step threshold is blended, not passed straight through."""
    ctrl = _controller(deadband=40, tau=2.0, dt=2.0, ema=1000.0)

    result = ChargeDischargeController._filter_grid_sample(ctrl, 1100.0, 2.0)

    # alpha = dt/(tau+dt) = 2/(2+2) = 0.5 -> halfway between 1000 and 1100.
    assert result == 1050.0
    assert ctrl._grid_filter_ema == 1050.0


def test_large_deviation_passes_through_completely():
    """A deviation over the step threshold (kettle-sized) snaps straight to raw."""
    ctrl = _controller(deadband=40, tau=2.0, dt=2.0, ema=1000.0)

    # Threshold = max(3*40, 200) = 200W; a 2000W jump is far past it.
    result = ChargeDischargeController._filter_grid_sample(ctrl, 3000.0, 2.0)

    assert result == 3000.0
    assert ctrl._grid_filter_ema == 3000.0


def test_step_threshold_floor_protects_tiny_deadband():
    """Even with a very small configured deadband, the 200W floor still applies."""
    ctrl = _controller(deadband=5, tau=2.0, dt=2.0, ema=1000.0)

    # 3*5=15W would trigger passthrough on almost any sample; the 200W floor
    # means a 150W deviation is still smoothed, not passed straight through.
    result = ChargeDischargeController._filter_grid_sample(ctrl, 1150.0, 2.0)

    assert result == 1075.0  # smoothed halfway, not snapped to 1150


def test_deviation_just_over_floor_passes_through():
    ctrl = _controller(deadband=5, tau=2.0, dt=2.0, ema=1000.0)

    result = ChargeDischargeController._filter_grid_sample(ctrl, 1201.0, 2.0)

    assert result == 1201.0


def test_first_sample_seeds_filter_directly():
    ctrl = _controller(ema=None)

    result = ChargeDischargeController._filter_grid_sample(ctrl, 500.0, None)

    assert result == 500.0
    assert ctrl._grid_filter_ema == 500.0
