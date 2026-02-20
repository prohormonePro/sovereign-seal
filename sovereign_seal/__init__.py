"""
sovereign-seal: Deterministic governance layer for autonomous AI agents.

Three functions. One invariant. If it can't prove integrity, it halts.

    from sovereign_seal import SovereignSeal

    seal = SovereignSeal("./ledger")
    seal.append(action="deployed model v2", metadata={"model": "gpt-4o"})
    seal.verify()  # passes or raises
    seal.halt_or_proceed(witnesses=["./replica1", "./replica2"])
"""

from sovereign_seal.core import SovereignSeal
from sovereign_seal.core import (
    SealError, ContinuityBreak, HashMismatch, WitnessDrift, VoiceDrift,
    SealEntry, VerifyResult, WitnessReport,
)

__version__ = "0.1.0"
__all__ = [
    "SovereignSeal",
    "SealError",
    "ContinuityBreak",
    "HashMismatch",
    "WitnessDrift",
    "VoiceDrift",
    "SealEntry",
    "VerifyResult",
    "WitnessReport",
]
