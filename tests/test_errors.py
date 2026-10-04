from grounded_agents.core import errors


def test_invalid_output_keeps_error_paths():
    err = errors.InvalidOutput(["$.claims: missing"])
    assert err.errors == ["$.claims: missing"]
    assert "$.claims: missing" in str(err)


def test_call_budget_exceeded_keeps_amounts():
    err = errors.CallBudgetExceeded(actual_usd=0.12, cap_usd=0.05)
    assert (err.actual_usd, err.cap_usd) == (0.12, 0.05)


def test_budget_exhausted_scope():
    assert errors.BudgetExhausted("day").scope == "day"


def test_all_errors_share_a_base():
    for cls in (errors.InvalidTransition, errors.InvalidOutput, errors.BudgetExhausted,
                errors.CallBudgetExceeded, errors.ProviderUnavailable, errors.ManifestError,
                errors.TierViolation, errors.SealError):
        assert issubclass(cls, errors.GroundedError)
