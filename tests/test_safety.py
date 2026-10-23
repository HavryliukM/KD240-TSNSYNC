import math

from kd240sync import config, safety


def _sc():
    return config.load().safety


def test_default_gains_are_robustly_stable():
    t = config.load().receiver.torque_pd
    sc = _sc()
    assert safety.robust_stable(t.kp_a_per_deg, t.kd_a_per_dps, t.ki_a_per_deg_s,
                                0.005, sc.ka_rad_s2_per_a, sc.ka_lo, sc.ka_hi, sc.tau_i_s)


def test_unstable_gains_are_scaled_down_not_zeroed():
    v, warns = safety.clamp_gains(1.0, 0.1, 0.1, 5.0, 9999.0, 9999.0, 0.005, _sc())
    assert warns
    assert 0.0 < v["kp"] < 0.05
    assert v["torque_limit_a"] <= 2.0 and v["slew_a_s"] <= 1000.0 and v["max_error_deg"] <= 180.0
    sc = _sc()
    assert safety.robust_stable(v["kp"], v["kd"], v["ki"], 0.005,
                                sc.ka_rad_s2_per_a, sc.ka_lo, sc.ka_hi, sc.tau_i_s)


def test_stable_gains_pass_unchanged():
    v, warns = safety.clamp_gains(0.011, 0.00045, 0.0, 0.1, 20.0, 60.0, 0.005, _sc())
    assert not warns and v["kp"] == 0.011


def _sup(max_err=60.0):
    return safety.Supervisor(_sc(), 0.005, max_err, 2500.0)


def test_supervisor_ok_in_normal_operation():
    s = _sup()
    for i in range(400):
        assert s.check(i * 0.005, 1.0 * math.sin(i / 20), 0.1, 1.5, 300.0) is None


def test_supervisor_detects_error_spike():
    s = _sup()
    assert s.check(0.0, 1.0, 0.0, 1.5, 0.0) is None
    assert "skok" in s.check(0.005, 1.0 + 50.0, 0.0, 1.5, 0.0)


def test_supervisor_detects_limit_and_overspeed_and_nan():
    s = _sup(max_err=20.0)
    assert "chyba" in s.check(0.0, 25.0, 0.0, 1.5, 0.0)
    assert "rychlost" in _sup().check(0.0, 0.0, 0.0, 1.5, 4000.0)
    assert "neciselna" in _sup().check(0.0, float("nan"), 0.0, 1.5, 0.0)


def test_supervisor_detects_saturation_and_oscillation_and_stall():
    s = _sup()
    reason = None
    for i in range(400):
        reason = s.check(i * 0.005, 10.0, 1.5, 1.5, 0.0)
        if reason:
            break
    assert reason and "nasyten" in reason
    s = _sup()
    reason = None
    for i in range(400):
        reason = s.check(i * 0.005, 6.0 if i % 2 else -6.0, 0.0, 1.5, 0.0)
        if reason:
            break
    assert reason is not None
    s = _sup()
    assert s.check(0.0, 0.0, 0.0, 1.5, 0.0) is None
    assert "vypadok" in s.check(1.0, 0.0, 0.0, 1.5, 0.0)
