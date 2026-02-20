"""
Adversarial test suite for sovereign-seal.

Five attacks. Five halts. Deterministic behavior.

Run: python -m unittest tests.test_adversarial -v
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from sovereign_seal import (
    SovereignSeal,
    ContinuityBreak,
    HashMismatch,
    WitnessDrift,
    VoiceDrift,
)


class TestBasicOperations(unittest.TestCase):
    """Verify the happy path works before attacking it."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.seal = SovereignSeal(os.path.join(self.tmpdir, "ledger"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_append_and_verify(self):
        """Append 3 entries, verify chain integrity."""
        self.seal.append(action="init", metadata={"v": 1})
        self.seal.append(action="deploy", metadata={"v": 2})
        self.seal.append(action="test", metadata={"v": 3})

        result = self.seal.verify()
        self.assertTrue(result.valid)
        self.assertEqual(result.lines, 3)
        self.assertEqual(len(result.tip), 64)

    def test_empty_ledger_verifies(self):
        """Empty ledger is valid."""
        result = self.seal.verify()
        self.assertTrue(result.valid)
        self.assertEqual(result.lines, 0)

    def test_tip_advances(self):
        """Each append produces a new tip."""
        e1 = self.seal.append(action="first")
        e2 = self.seal.append(action="second")
        self.assertNotEqual(e1.entry_hash, e2.entry_hash)
        self.assertEqual(self.seal.get_tip(), e2.entry_hash)

    def test_line_count(self):
        """Line count matches append count."""
        for i in range(5):
            self.seal.append(action=f"step {i}")
        self.assertEqual(self.seal.get_line_count(), 5)


class TestAttack1_CorruptEntry(unittest.TestCase):
    """
    ATTACK 1: Corrupt a ledger entry.
    Modify one byte in the middle of the chain.
    Expected: HashMismatch raised.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.seal = SovereignSeal(os.path.join(self.tmpdir, "ledger"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_corrupt_entry_halts(self):
        self.seal.append(action="step 1")
        self.seal.append(action="step 2")
        self.seal.append(action="step 3")

        # Tamper with line 2
        ledger = self.seal.ledger_path
        lines = ledger.read_text(encoding="utf-8").strip().split("\n")
        obj = json.loads(lines[1])
        obj["action"] = "TAMPERED"
        lines[1] = json.dumps(obj, separators=(",", ":"))
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with self.assertRaises(HashMismatch) as ctx:
            self.seal.verify()
        self.assertEqual(ctx.exception.line, 2)


class TestAttack2_BreakContinuity(unittest.TestCase):
    """
    ATTACK 2: Break the prev_hash chain.
    Swap two entries' order or change prev_hash.
    Expected: ContinuityBreak raised.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.seal = SovereignSeal(os.path.join(self.tmpdir, "ledger"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_broken_chain_halts(self):
        self.seal.append(action="step 1")
        self.seal.append(action="step 2")
        self.seal.append(action="step 3")

        # Flip prev_hash on line 3
        ledger = self.seal.ledger_path
        lines = ledger.read_text(encoding="utf-8").strip().split("\n")
        obj = json.loads(lines[2])
        obj["prev_hash"] = "A" * 64  # wrong prev
        lines[2] = json.dumps(obj, separators=(",", ":"))
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with self.assertRaises(ContinuityBreak) as ctx:
            self.seal.verify()
        self.assertEqual(ctx.exception.line, 3)


class TestAttack3_WitnessDrift(unittest.TestCase):
    """
    ATTACK 3: Witnesses disagree on the tip.
    One replica has a different tip than the primary.
    Expected: WitnessDrift raised.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.primary = SovereignSeal(os.path.join(self.tmpdir, "primary"))
        self.replica1 = os.path.join(self.tmpdir, "replica1")
        self.replica2 = os.path.join(self.tmpdir, "replica2")
        os.makedirs(self.replica1, exist_ok=True)
        os.makedirs(self.replica2, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_stale_witness_halts(self):
        # Append entries
        self.primary.append(action="step 1")
        self.primary.append(action="step 2")

        # Export tip to replicas
        self.primary.export_tip(self.replica1)
        self.primary.export_tip(self.replica2)

        # Advance primary without updating replicas
        self.primary.append(action="step 3")

        # Now replica tips are stale
        with self.assertRaises(WitnessDrift) as ctx:
            self.primary.halt_or_proceed(
                witnesses=[self.replica1, self.replica2]
            )
        self.assertEqual(len(ctx.exception.drifts), 2)

    def test_missing_witness_halts(self):
        self.primary.append(action="step 1")

        # Replica exists but has no TIP.sha256
        missing_witness = os.path.join(self.tmpdir, "missing_replica")
        os.makedirs(missing_witness, exist_ok=True)

        with self.assertRaises(WitnessDrift):
            self.primary.halt_or_proceed(witnesses=[missing_witness])

    def test_consensus_passes(self):
        self.primary.append(action="step 1")
        self.primary.export_tip(self.replica1)
        self.primary.export_tip(self.replica2)

        report = self.primary.halt_or_proceed(
            witnesses=[self.replica1, self.replica2]
        )
        self.assertTrue(report.consensus)
        self.assertEqual(len(report.drifts), 0)


class TestAttack4_VoiceDrift(unittest.TestCase):
    """
    ATTACK 4: Output fails governance checks.
    The agent produces output that violates voice rules.
    Expected: VoiceDrift raised.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.seal = SovereignSeal(os.path.join(self.tmpdir, "ledger"))
        self.seal.append(action="init")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def no_banned_phrases(self, text: str) -> bool:
        """Governance check: reject banned phrases."""
        banned = ["as an ai", "i cannot browse", "guaranteed results"]
        lower = text.lower()
        return not any(b in lower for b in banned)

    no_banned_phrases.__name__ = "no_banned_phrases"

    def must_contain_stance(self, text: str) -> bool:
        """Governance check: must contain at least one stance keyword."""
        required = ["verified", "proof", "evidence", "tested"]
        lower = text.lower()
        return any(r in lower for r in required)

    must_contain_stance.__name__ = "must_contain_stance"

    def test_banned_phrase_halts(self):
        with self.assertRaises(VoiceDrift):
            self.seal.halt_or_proceed(
                voice_checks=[self.no_banned_phrases],
                voice_input="As an AI, I cannot verify this claim."
            )

    def test_missing_stance_halts(self):
        with self.assertRaises(VoiceDrift):
            self.seal.halt_or_proceed(
                voice_checks=[self.must_contain_stance],
                voice_input="This product is amazing and life-changing!"
            )

    def test_clean_output_passes(self):
        report = self.seal.halt_or_proceed(
            voice_checks=[self.no_banned_phrases, self.must_contain_stance],
            voice_input="This compound has been tested and shows verified results in clinical trials."
        )
        self.assertTrue(report.consensus)


class TestAttack5_FullReplay(unittest.TestCase):
    """
    ATTACK 5: Replay the entire chain deterministically.
    Verify that the same inputs always produce the same hashes.
    Then tamper and prove replay catches it.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.seal = SovereignSeal(os.path.join(self.tmpdir, "ledger"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_full_replay_100_entries(self):
        """Append 100 entries, verify all, tamper one, catch it."""
        entries = []
        for i in range(100):
            e = self.seal.append(
                action=f"step {i}",
                metadata={"index": i, "data": f"payload_{i}"}
            )
            entries.append(e)

        # Verify passes
        result = self.seal.verify()
        self.assertTrue(result.valid)
        self.assertEqual(result.lines, 100)
        self.assertEqual(result.tip, entries[-1].entry_hash)

        # Tamper with entry 50
        ledger = self.seal.ledger_path
        lines = ledger.read_text(encoding="utf-8").strip().split("\n")
        obj = json.loads(lines[49])
        obj["metadata"]["data"] = "CORRUPTED"
        lines[49] = json.dumps(obj, separators=(",", ":"))
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Verify catches it at line 50
        with self.assertRaises(HashMismatch) as ctx:
            self.seal.verify()
        self.assertEqual(ctx.exception.line, 50)


class TestHaltOrProceedIntegration(unittest.TestCase):
    """Integration test: the full governance gate."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.primary_dir = os.path.join(self.tmpdir, "primary")
        self.replica_dir = os.path.join(self.tmpdir, "replica")
        self.seal = SovereignSeal(self.primary_dir)
        os.makedirs(self.replica_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_full_governance_pass(self):
        """All three gates pass: chain + witnesses + voice."""
        self.seal.append(action="deploy agent")
        self.seal.export_tip(self.replica_dir)

        def no_harm(text):
            return "harm" not in text.lower()

        report = self.seal.halt_or_proceed(
            witnesses=[self.replica_dir],
            voice_checks=[no_harm],
            voice_input="Agent completed task safely."
        )
        self.assertTrue(report.consensus)

    def test_on_halt_callback(self):
        """The on_halt callback fires on failure."""
        self.seal.append(action="deploy")

        halt_log = []

        def log_halt(err):
            halt_log.append(str(err))

        # Missing witness = drift
        with self.assertRaises(WitnessDrift):
            self.seal.halt_or_proceed(
                witnesses=[self.replica_dir],  # no TIP.sha256
                on_halt=log_halt,
            )

        self.assertEqual(len(halt_log), 1)
        self.assertIn("drift", halt_log[0].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
