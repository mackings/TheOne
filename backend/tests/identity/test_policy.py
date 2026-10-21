from app.identity.domain.policy import Decision, Thresholds, decide

T = Thresholds(match_accept=0.55, match_stepup=0.40, spoof_stepup=0.60, spoof_reject=0.90, high_risk_margin=0.10)


def test_accept():
    assert decide(0.70, 0.1, None, T).decision == Decision.ACCEPT


def test_stepup_band():
    assert decide(0.50, 0.1, None, T).decision == Decision.STEP_UP


def test_reject_low_match():
    assert decide(0.30, 0.1, None, T).decision == Decision.REJECT


def test_spoof_forces_stepup():
    assert decide(0.80, 0.65, None, T).decision == Decision.STEP_UP


def test_spoof_reject_wins():
    assert decide(0.95, 0.95, None, T).decision == Decision.REJECT


def test_high_risk_context_raises_threshold():
    r = decide(0.60, 0.1, "high_value_transfer", T)
    assert r.decision == Decision.STEP_UP
    assert r.effective_accept_threshold == 0.65
    assert decide(0.60, 0.1, "balance_enquiry", T).decision == Decision.ACCEPT
