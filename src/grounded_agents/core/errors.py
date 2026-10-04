"""Error taxonomy.

Content failures (a draft that cites nothing, a verifier objection) are *not* exceptions: they
are item states. Exceptions are for things that stop a run or break a contract.
"""


class GroundedError(Exception):
    """Base class for every error raised by this package."""


class InvalidTransition(GroundedError):
    """An item tried to move to a state the transition table does not allow."""


class InvalidOutput(GroundedError):
    """Model output failed schema validation. Keeps JSON paths, never the model's text."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


class BudgetExhausted(GroundedError):
    """The next call would exceed the per-run or per-day cap. Raised *before* spending."""

    def __init__(self, scope: str, detail: str = ""):
        self.scope = scope
        super().__init__(f"{scope} budget exhausted" + (f": {detail}" if detail else ""))


class CallBudgetExceeded(GroundedError):
    """A single call cost more than its cap. The money is already spent; the run stops."""

    def __init__(self, actual_usd: float, cap_usd: float):
        self.actual_usd = actual_usd
        self.cap_usd = cap_usd
        super().__init__(f"call cost {actual_usd:.4f} USD above the {cap_usd:.4f} USD cap")


class ProviderUnavailable(GroundedError):
    """The model provider could not answer (network, auth, missing package, no script)."""


class RunTimeout(GroundedError):
    """The run exceeded its manifest's timeout_s. Checked between model calls."""


class ManifestError(GroundedError):
    """A worker manifest is missing fields or has invalid values."""


class TierViolation(GroundedError):
    """A worker tried to do something its autonomy tier does not allow."""


class SealError(GroundedError):
    """The eval seal is missing, stale, red, or the frozen set was modified."""
