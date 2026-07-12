"""Tests for the feedforward step detector ``_check_feedforward_step`` (__init__.py).

A confirmed load step lets the control loop command ONE deadbeat cycle instead
of the ~13 s exponential approach of the incremental P term. The detector is
2-sample (candidate + confirmation against the pre-step baseline) with two
anti-hunting guards: a cooldown between fires and a pulse guard that refuses an
opposite-sign step shortly after a fire (induction hob — the slow PD averaging
it out is the desired behavior).

The method is exercised unbound with a ``SimpleNamespace`` stub for ``self``,
matching ``test_filter_grid_sample_adaptive.py``. No freezegun: the method
reads ``time.monotonic()`` internally, so tests shift the STORED timestamps
(candidate arm time, last-fire time) backwards instead, per repo convention.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

from custom_components.omnibattery import ChargeDischargeController
from custom_components.omnibattery.const import (
    FEEDFORWARD_CANDIDATE_MAX_AGE_S,
    FEEDFORWARD_COOLDOWN_S,
    FEEDFORWARD_PULSE_GUARD_S,
    FEEDFORWARD_STEP_FLOOR_W,
)


def _controller(*, deadband=40, previous_error=0.0):
    return SimpleNamespace(
        deadband=deadband,
        previous_error=previous_error,
        _step_candidate=None,
        _last_feedforward_monotonic=None,
        _last_feedforward_sign=0,
    )


def _check(ctrl, error):
    return ChargeDischargeController._check_feedforward_step(ctrl, error)


def test_jump_below_threshold_does_not_arm():
    """An error jump under max(5*deadband, 400W) is normal PD territory."""
    ctrl = _controller(deadband=40, previous_error=0.0)

    assert _check(ctrl, 350.0) is False
    assert ctrl._step_candidate is None


def test_threshold_scales_with_deadband():
    """With a wide deadband, 5*deadband governs instead of the 400W floor."""
    ctrl = _controller(deadband=100, previous_error=0.0)

    assert _check(ctrl, 450.0) is False  # over the floor, under 5*100
    assert ctrl._step_candidate is None


def test_sustained_step_confirms_on_second_sample():
    """Candidate on sample 1, fire on sample 2 when the deviation persists."""
    ctrl = _controller(deadband=40, previous_error=0.0)

    assert _check(ctrl, 500.0) is False  # armed, not fired
    assert ctrl._step_candidate is not None

    ctrl.previous_error = 500.0  # end-of-cycle update by the control loop
    assert _check(ctrl, 480.0) is True  # 480 >= 0.8 * 500, same sign

    assert ctrl._step_candidate is None
    assert ctrl._last_feedforward_sign == 1
    assert ctrl._last_feedforward_monotonic is not None


def test_single_sample_spike_is_rejected():
    """Error returns to baseline on the next sample -> meter spike, no fire."""
    ctrl = _controller(deadband=40, previous_error=0.0)

    assert _check(ctrl, 500.0) is False
    ctrl.previous_error = 500.0
    assert _check(ctrl, 20.0) is False  # deviation collapsed

    assert ctrl._last_feedforward_monotonic is None


def test_partial_persistence_below_confirm_ratio_is_rejected():
    ctrl = _controller(deadband=40, previous_error=0.0)

    assert _check(ctrl, 500.0) is False
    ctrl.previous_error = 500.0
    assert _check(ctrl, 350.0) is False  # 350 < 0.8 * 500


def test_opposite_sign_deviation_is_rejected():
    ctrl = _controller(deadband=40, previous_error=0.0)

    assert _check(ctrl, 500.0) is False
    ctrl.previous_error = 500.0
    assert _check(ctrl, -450.0) is False  # persisted in magnitude, wrong sign


def test_negative_step_confirms_too():
    """Solar/export steps (error jumping negative) fire symmetrically."""
    ctrl = _controller(deadband=40, previous_error=0.0)

    assert _check(ctrl, -600.0) is False
    ctrl.previous_error = -600.0
    assert _check(ctrl, -550.0) is True
    assert ctrl._last_feedforward_sign == -1


def test_unconfirmed_sample_can_arm_a_new_candidate():
    """A failed confirmation still evaluates the current sample as a new jump."""
    ctrl = _controller(deadband=40, previous_error=0.0)

    assert _check(ctrl, 500.0) is False
    ctrl.previous_error = 500.0
    # Confirmation fails (deviation vs baseline 0 is -100), but the jump vs
    # previous_error (500 -> -100 = -600) arms a fresh opposite candidate.
    assert _check(ctrl, -100.0) is False
    assert ctrl._step_candidate is not None
    assert ctrl._step_candidate[1] == -600.0


def test_cooldown_blocks_second_fire():
    ctrl = _controller(deadband=40, previous_error=0.0)
    ctrl._last_feedforward_monotonic = time.monotonic() - (FEEDFORWARD_COOLDOWN_S - 1)
    ctrl._last_feedforward_sign = 1

    assert _check(ctrl, 500.0) is False  # arm
    ctrl.previous_error = 500.0
    assert _check(ctrl, 500.0) is False  # confirmed but inside cooldown


def test_same_sign_fire_allowed_after_cooldown():
    ctrl = _controller(deadband=40, previous_error=0.0)
    ctrl._last_feedforward_monotonic = time.monotonic() - (FEEDFORWARD_COOLDOWN_S + 1)
    ctrl._last_feedforward_sign = 1

    assert _check(ctrl, 500.0) is False
    ctrl.previous_error = 500.0
    assert _check(ctrl, 500.0) is True


def test_pulse_guard_blocks_opposite_sign_within_window():
    """Opposite-sign step after the cooldown but inside the pulse window: a
    pulsing load (induction hob) — the PD averaging it is the good behavior."""
    ctrl = _controller(deadband=40, previous_error=0.0)
    ctrl._last_feedforward_monotonic = time.monotonic() - (FEEDFORWARD_COOLDOWN_S + 5)
    ctrl._last_feedforward_sign = 1

    assert _check(ctrl, -500.0) is False
    ctrl.previous_error = -500.0
    assert _check(ctrl, -500.0) is False  # confirmed, blocked by pulse guard
    assert ctrl._last_feedforward_sign == 1  # state untouched


def test_opposite_sign_allowed_after_pulse_window():
    ctrl = _controller(deadband=40, previous_error=0.0)
    ctrl._last_feedforward_monotonic = time.monotonic() - (FEEDFORWARD_PULSE_GUARD_S + 1)
    ctrl._last_feedforward_sign = 1

    assert _check(ctrl, -500.0) is False
    ctrl.previous_error = -500.0
    assert _check(ctrl, -500.0) is True
    assert ctrl._last_feedforward_sign == -1


def test_stale_candidate_cannot_confirm():
    """Deadband/blocked cycles in between age the candidate past validity."""
    ctrl = _controller(deadband=40, previous_error=0.0)

    assert _check(ctrl, 500.0) is False
    baseline, jump, armed_ts = ctrl._step_candidate
    ctrl._step_candidate = (
        baseline, jump, armed_ts - (FEEDFORWARD_CANDIDATE_MAX_AGE_S + 1)
    )
    ctrl.previous_error = 500.0

    assert _check(ctrl, 500.0) is False
    assert ctrl._last_feedforward_monotonic is None


def test_floor_constant_matches_plan():
    """Threshold floor sits above the adaptive filter's 3*deadband/200W collapse
    threshold on purpose: the filter passes a step through, the feedforward acts."""
    assert FEEDFORWARD_STEP_FLOOR_W == 400
