"""
Example: Live halt demonstration.

An agent is about to do something powerful.
The governance layer stops it.
No theatrics. Just clean proof.

Run:
    PYTHONPATH=. python examples/live_halt_demo.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import shutil
from sovereign_seal import SovereignSeal, SealError


def main():
    print("=" * 60)
    print(" sovereign-seal: Live Halt Demo")
    print(" An agent tries to act. Governance decides.")
    print("=" * 60)

    # Setup
    seal = SovereignSeal("./halt_demo_ledger")
    replica = "./halt_demo_replica"
    os.makedirs(replica, exist_ok=True)

    # Governance rules
    def no_pii_exposure(text: str) -> bool:
        markers = ["ssn:", "credit card:", "password:"]
        return not any(m in text.lower() for m in markers)

    def no_unverified_claims(text: str) -> bool:
        hype = ["guaranteed", "risk-free", "100% effective", "no side effects"]
        return not any(h in text.lower() for h in hype)

    def must_cite_evidence(text: str) -> bool:
        evidence = ["study", "trial", "data", "measured", "tested", "verified"]
        return any(e in text.lower() for e in evidence)

    checks = [no_pii_exposure, no_unverified_claims, must_cite_evidence]

    # -------------------------------------------------------
    # Scenario 1: Agent produces clean, evidence-based output
    # -------------------------------------------------------
    print("\n--- Scenario 1: Clean output ---")
    seal.append(action="Agent generating medical summary")
    seal.export_tip(replica)

    clean_output = (
        "Based on the Phase III clinical trial data (n=2,400), "
        "the compound showed a measured 12% improvement in biomarker levels. "
        "Side effects were observed in 8% of participants. "
        "Further testing is recommended before clinical use."
    )

    try:
        seal.halt_or_proceed(
            witnesses=[replica],
            voice_checks=checks,
            voice_input=clean_output,
        )
        seal.append(action="Output approved", metadata={"output": clean_output[:80]})
        seal.export_tip(replica)
        print(f"Output: {clean_output[:60]}...")
        print("[PASS] Agent may proceed. Output sealed.")
    except SealError as e:
        print(f"[HALT] {e}")

    # -------------------------------------------------------
    # Scenario 2: Agent produces hype with no evidence
    # -------------------------------------------------------
    print("\n--- Scenario 2: Hype with no evidence ---")
    seal.append(action="Agent generating product description")
    seal.export_tip(replica)

    hype_output = (
        "This revolutionary supplement is guaranteed to transform your life! "
        "100% effective with no side effects. Buy now!"
    )

    try:
        seal.halt_or_proceed(
            witnesses=[replica],
            voice_checks=checks,
            voice_input=hype_output,
        )
        seal.append(action="Output approved")
        print("[PASS] Agent may proceed.")
    except SealError as e:
        seal.append(action="Output BLOCKED", metadata={"reason": str(e)})
        seal.export_tip(replica)
        print(f"Output: {hype_output[:60]}...")
        print(f"[HALT] {e}")
        print("        The agent was stopped. The output was not sent.")

    # -------------------------------------------------------
    # Scenario 3: Agent exposes PII
    # -------------------------------------------------------
    print("\n--- Scenario 3: PII exposure attempt ---")
    seal.append(action="Agent generating user report")
    seal.export_tip(replica)

    pii_output = "User profile: John Smith, SSN: 123-45-6789, balance $4,200"

    try:
        seal.halt_or_proceed(
            witnesses=[replica],
            voice_checks=checks,
            voice_input=pii_output,
        )
        print("[PASS] Agent may proceed.")
    except SealError as e:
        seal.append(action="Output BLOCKED - PII", metadata={"reason": str(e)})
        seal.export_tip(replica)
        print(f"Output: [REDACTED - contained PII]")
        print(f"[HALT] {e}")
        print("        The agent was stopped. PII was not exposed.")

    # -------------------------------------------------------
    # Scenario 4: Witness drift (stale replica)
    # -------------------------------------------------------
    print("\n--- Scenario 4: Witness drift ---")
    # Advance primary without updating replica
    seal.append(action="Silent update - replica not notified")
    # Do NOT export tip to replica

    safe_output = "This was tested and verified in controlled conditions."

    try:
        seal.halt_or_proceed(
            witnesses=[replica],
            voice_checks=checks,
            voice_input=safe_output,
        )
        print("[PASS] Agent may proceed.")
    except SealError as e:
        seal.append(action="HALTED - witness drift", metadata={"reason": str(e)})
        # Now sync and continue
        seal.export_tip(replica)
        print(f"[HALT] {e}")
        print("        Even with clean output, stale witnesses = halt.")
        print("        The system chose silence over proceeding unverified.")

    # -------------------------------------------------------
    # Final state
    # -------------------------------------------------------
    print("\n" + "=" * 60)
    result = seal.verify()
    print(f" Chain: {result.lines} entries, all verified")
    print(f" Tip:   {result.tip[:16]}...")
    print(f" Halts: 3 (hype, PII, drift)")
    print(f" Passes: 1 (clean, evidence-based)")
    print(f" The system refused 3 times. That's the feature.")
    print("=" * 60)

    # Cleanup
    shutil.rmtree("./halt_demo_ledger", ignore_errors=True)
    shutil.rmtree("./halt_demo_replica", ignore_errors=True)


if __name__ == "__main__":
    main()
