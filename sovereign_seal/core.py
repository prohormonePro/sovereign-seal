"""
sovereign_seal.core — Deterministic governance layer for AI agents.

This module implements a hash-chain ledger with witness verification.
An agent wrapped in SovereignSeal cannot act without proving:

1. Its history is unbroken (hash chain continuity)
2. Its state matches all witnesses (cross-node consensus)
3. Its outputs pass governance checks (halt-or-proceed gate)

If any check fails, the system halts. It chooses silence over drift.

No dependencies beyond the Python standard library.
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


# ============================================================
# Exceptions
# ============================================================

class SealError(Exception):
    """Base exception for all seal failures."""
    pass


class ContinuityBreak(SealError):
    """Hash chain is broken. A previous entry was tampered with."""
    def __init__(self, line: int, expected: str, found: str):
        self.line = line
        self.expected = expected
        self.found = found
        super().__init__(
            f"Continuity break at line {line}: "
            f"expected prev={expected[:16]}..., found prev={found[:16]}..."
        )


class HashMismatch(SealError):
    """Recomputed hash doesn't match stored hash. Entry was modified."""
    def __init__(self, line: int, stored: str, recomputed: str):
        self.line = line
        self.stored = stored
        self.recomputed = recomputed
        super().__init__(
            f"Hash mismatch at line {line}: "
            f"stored={stored[:16]}..., recomputed={recomputed[:16]}..."
        )


class WitnessDrift(SealError):
    """One or more witnesses disagree on the current tip."""
    def __init__(self, drifts: list):
        self.drifts = drifts
        names = ", ".join(d["witness"] for d in drifts)
        super().__init__(f"Witness drift detected: {names}")


class VoiceDrift(SealError):
    """Output failed a governance voice check."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Voice drift: {reason}")


# ============================================================
# Data types
# ============================================================

ZERO_HASH = "0" * 64


@dataclass
class SealEntry:
    """A single entry in the hash chain."""
    kind: str
    utc: str
    action: str
    metadata: dict
    prev_hash: str
    entry_hash: str


@dataclass
class VerifyResult:
    """Result of a full chain verification."""
    valid: bool
    lines: int
    tip: str
    first_utc: Optional[str] = None
    last_utc: Optional[str] = None
    error: Optional[SealError] = None


@dataclass
class WitnessReport:
    """Result of cross-witness verification."""
    consensus: bool
    local_tip: str
    witnesses: list = field(default_factory=list)
    drifts: list = field(default_factory=list)


# ============================================================
# Core: SovereignSeal
# ============================================================

class SovereignSeal:
    """
    Deterministic governance layer for autonomous AI agents.

    Usage:
        seal = SovereignSeal("./my_ledger")
        seal.append(action="ran inference", metadata={"model": "gpt-4o"})

        # Verify full chain integrity
        result = seal.verify()

        # Gate: halt if chain or witnesses are broken
        seal.halt_or_proceed(witnesses=["./replica1", "./replica2"])

        # Gate with voice checks
        seal.halt_or_proceed(
            witnesses=["./replica1"],
            voice_checks=[lambda text: "error" not in text.lower()],
            voice_input="Model output looks good"
        )

    The ledger is an append-only NDJSON file. Each line contains:
    - kind: event type (default "SEAL_EVENT")
    - utc: ISO 8601 timestamp
    - action: human-readable description of what happened
    - metadata: arbitrary JSON-serializable data
    - prev_hash: SHA-256 of the previous entry (or 64 zeros for genesis)
    - entry_hash: SHA-256 of this entry's preimage (all fields except entry_hash)

    Verification recomputes every hash from scratch. If any hash doesn't
    match, or any prev_hash breaks the chain, the system raises and halts.
    """

    def __init__(self, ledger_dir: str, tip_filename: str = "TIP.sha256"):
        """
        Args:
            ledger_dir: Directory for the ledger file and tip pointer.
            tip_filename: Name of the file that holds the current tip hash.
        """
        self.ledger_dir = Path(ledger_dir)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)

        self.ledger_path = self.ledger_dir / "LEDGER.ndjson"
        self.tip_path = self.ledger_dir / tip_filename

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def append(
        self,
        action: str,
        metadata: Optional[dict] = None,
        kind: str = "SEAL_EVENT",
    ) -> SealEntry:
        """
        Append a new entry to the ledger.

        Args:
            action: Human-readable description of the action.
            metadata: Arbitrary JSON-serializable data.
            kind: Event type (default "SEAL_EVENT").

        Returns:
            The SealEntry that was appended.
        """
        metadata = metadata or {}
        prev = self._read_tip()
        utc = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

        preimage = self._build_preimage(kind, utc, action, metadata, prev)
        entry_hash = self._sha256(preimage)

        line = json.loads(preimage)
        line["entry_hash"] = entry_hash
        line_json = json.dumps(line, separators=(",", ":"), sort_keys=False)

        # Append to ledger (atomic-ish: write + flush)
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(line_json + "\n")
            f.flush()
            os.fsync(f.fileno())

        # Update tip
        self._write_tip(entry_hash)

        return SealEntry(
            kind=kind,
            utc=utc,
            action=action,
            metadata=metadata,
            prev_hash=prev,
            entry_hash=entry_hash,
        )

    def verify(self) -> VerifyResult:
        """
        Re-verify the entire ledger from genesis.

        Rebuilds every preimage, recomputes every hash, checks every
        prev_hash link. If anything is wrong, raises ContinuityBreak
        or HashMismatch.

        Returns:
            VerifyResult with line count, tip, and timestamps.

        Raises:
            ContinuityBreak: If prev_hash chain is broken.
            HashMismatch: If any entry's hash doesn't match its preimage.
        """
        if not self.ledger_path.exists():
            return VerifyResult(valid=True, lines=0, tip=ZERO_HASH)

        prev_expected = ZERO_HASH
        first_utc = None
        last_utc = None
        idx = 0

        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                idx += 1
                obj = json.loads(ln)

                # Check continuity
                stored_prev = obj.get("prev_hash", ZERO_HASH)
                if stored_prev != prev_expected:
                    raise ContinuityBreak(idx, prev_expected, stored_prev)

                # Rebuild preimage and verify hash
                preimage = self._build_preimage(
                    obj["kind"], obj["utc"], obj["action"],
                    obj.get("metadata", {}), obj["prev_hash"],
                )
                recomputed = self._sha256(preimage)
                stored_hash = obj["entry_hash"]

                if stored_hash != recomputed:
                    raise HashMismatch(idx, stored_hash, recomputed)

                prev_expected = stored_hash
                if first_utc is None:
                    first_utc = obj["utc"]
                last_utc = obj["utc"]

        if idx == 0:
            return VerifyResult(valid=True, lines=0, tip=ZERO_HASH)

        return VerifyResult(
            valid=True,
            lines=idx,
            tip=prev_expected,
            first_utc=first_utc,
            last_utc=last_utc,
        )

    def halt_or_proceed(
        self,
        witnesses: Optional[list] = None,
        voice_checks: Optional[list] = None,
        voice_input: Optional[str] = None,
        on_halt: Optional[Callable] = None,
    ) -> WitnessReport:
        """
        The governance gate. Three checks, any failure = halt.

        1. Chain integrity (verify full ledger)
        2. Witness consensus (all witnesses agree on tip)
        3. Voice checks (optional output governance)

        Args:
            witnesses: List of paths to other ledger directories.
                       Each must contain a TIP.sha256 file.
            voice_checks: List of callables that take a string and return bool.
                          If any returns False, the system halts with VoiceDrift.
            voice_input: The text to run through voice_checks.
            on_halt: Optional callback invoked on halt (receives the exception).

        Returns:
            WitnessReport if all checks pass.

        Raises:
            ContinuityBreak: Chain is broken.
            HashMismatch: Entry was tampered.
            WitnessDrift: Witnesses disagree.
            VoiceDrift: Output failed governance check.
        """
        # Gate 1: Chain integrity
        result = self.verify()

        # Gate 2: Witness consensus
        report = WitnessReport(
            consensus=True,
            local_tip=result.tip,
        )

        if witnesses:
            for witness_path in witnesses:
                wp = Path(witness_path)
                tip_file = wp / "TIP.sha256"
                witness_info = {"witness": str(wp), "tip": None, "match": False}

                if tip_file.exists():
                    witness_tip = tip_file.read_text(encoding="utf-8").strip()
                    witness_info["tip"] = witness_tip
                    witness_info["match"] = (witness_tip == result.tip)
                else:
                    witness_info["tip"] = "MISSING"
                    witness_info["match"] = False

                report.witnesses.append(witness_info)
                if not witness_info["match"]:
                    report.drifts.append(witness_info)

            if report.drifts:
                report.consensus = False
                err = WitnessDrift(report.drifts)
                if on_halt:
                    on_halt(err)
                raise err

        # Gate 3: Voice checks
        if voice_checks and voice_input is not None:
            for check in voice_checks:
                if not check(voice_input):
                    reason = getattr(check, "__name__", "unnamed_check")
                    err = VoiceDrift(reason)
                    if on_halt:
                        on_halt(err)
                    raise err

        return report

    def get_tip(self) -> str:
        """Return the current tip hash."""
        return self._read_tip()

    def get_line_count(self) -> int:
        """Return the number of entries in the ledger."""
        if not self.ledger_path.exists():
            return 0
        count = 0
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for ln in f:
                if ln.strip():
                    count += 1
        return count

    def export_tip(self, target_dir: str) -> str:
        """
        Export the current tip to another directory (witness replication).

        Args:
            target_dir: Directory to write TIP.sha256 into.

        Returns:
            The tip hash that was exported.
        """
        tip = self._read_tip()
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "TIP.sha256").write_text(tip + "\n", encoding="utf-8")
        return tip

    # --------------------------------------------------------
    # Internal
    # --------------------------------------------------------

    def _build_preimage(
        self, kind: str, utc: str, action: str,
        metadata: dict, prev_hash: str,
    ) -> str:
        """Build the canonical JSON preimage for hashing."""
        pre = {
            "kind": kind,
            "utc": utc,
            "action": action,
            "metadata": metadata,
            "prev_hash": prev_hash,
        }
        return json.dumps(pre, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _sha256(data: str) -> str:
        """SHA-256 of a UTF-8 string, uppercase hex."""
        return hashlib.sha256(data.encode("utf-8")).hexdigest().upper()

    def _read_tip(self) -> str:
        """Read the current tip, or return ZERO_HASH if no ledger."""
        if self.tip_path.exists():
            tip = self.tip_path.read_text(encoding="utf-8").strip()
            if len(tip) == 64:
                return tip

        # Fall back to reading last non-empty line of ledger (streaming)
        if self.ledger_path.exists():
            last_line = None
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                for ln in f:
                    if ln.strip():
                        last_line = ln
            if last_line:
                last = json.loads(last_line)
                return last.get("entry_hash", ZERO_HASH)

        return ZERO_HASH

    def _write_tip(self, tip: str) -> None:
        """Write tip to the pointer file."""
        self.tip_path.write_text(tip + "\n", encoding="utf-8")
