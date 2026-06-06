"""Sprint 1 news influence defaults.

News influence is intentionally no-op in Sprint 1.
"""

from types import MappingProxyType

NEWS_INFLUENCE_WEIGHTS = MappingProxyType(
    {
        "confidence_adj_frac": 0.0,
        "timeout_adj_frac": 0.0,
        "alpha_evidence_frac": 0.0,
        "omega_pressure_frac": 0.0,
        "sigma_pressure_frac": 0.0,
    }
)

