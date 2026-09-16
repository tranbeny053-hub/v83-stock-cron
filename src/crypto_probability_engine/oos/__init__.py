"""Out-of-sample paired-evidence infrastructure."""
from crypto_probability_engine.oos.pair_context import (
    CandidateFeature,
    OOSArm,
    OOSArmContext,
    OOSPairContext,
    PairInvalidError,
    PairTarget,
    build_oos_pair_context,
    is_derivatives_run_id,
    is_oos_run_id,
)

__all__ = (
    "OOSArm",
    "OOSArmContext",
    "OOSPairContext",
    "PairInvalidError",
    "PairTarget",
    "CandidateFeature",
    "build_oos_pair_context",
    "is_derivatives_run_id",
    "is_oos_run_id",
    "FreezeGuardMismatch",
    "assert_candidate_freeze",
    "current_freeze_artifacts",
    "write_candidate_freeze",
)

_FREEZE_EXPORTS = frozenset(
    {
        "FreezeGuardMismatch",
        "assert_candidate_freeze",
        "current_freeze_artifacts",
        "write_candidate_freeze",
    }
)


def __getattr__(name: str):
    if name in _FREEZE_EXPORTS:
        from crypto_probability_engine.oos import freeze_guard

        return getattr(freeze_guard, name)
    raise AttributeError(name)
