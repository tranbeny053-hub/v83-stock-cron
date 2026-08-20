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
)
