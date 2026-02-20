"""
Example: Wrap any AI agent with sovereign-seal governance.

This demonstrates the core pattern:
1. Agent decides on an action
2. Governance layer verifies integrity before allowing it
3. Action is sealed with proof after execution
4. If anything is wrong, the agent halts instead of proceeding

Run:
    PYTHONPATH=. python examples/wrap_any_agent.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sovereign_seal import SovereignSeal, SealError


def my_agent_action(task: str) -> str:
    """Simulate an agent doing work. Replace with your actual agent."""
    return f"Completed: {task}"


def main():
    # Initialize governance layer
    seal = SovereignSeal("./demo_ledger")

    # Set up witness replicas (in production, these are on different machines)
    replica = "./demo_replica"
    os.makedirs(replica, exist_ok=True)

    # Define voice checks (governance rules for output)
    def no_hallucinations(text: str) -> bool:
        """Reject outputs that contain known hallucination markers."""
        banned = ["guaranteed", "certainly", "absolutely sure", "100% safe"]
        return not any(b in text.lower() for b in banned)

    # === THE GOVERNANCE LOOP ===
    tasks = [
        "Deploy model update v2.1",
        "Process customer PII batch",
        "Send automated email campaign",
    ]

    for task in tasks:
        print(f"\n--- Task: {task} ---")

        # Step 1: Seal the intent
        seal.append(action=f"INTENT: {task}", metadata={"status": "pending"})
        seal.export_tip(replica)  # Keep witnesses in sync

        # Step 2: Execute the agent
        result = my_agent_action(task)
        print(f"Agent output: {result}")

        # Step 3: Gate check before committing
        try:
            seal.halt_or_proceed(
                witnesses=[replica],
                voice_checks=[no_hallucinations],
                voice_input=result,
            )
            print("[PASS] Governance check passed")
        except SealError as e:
            print(f"[HALT] Governance blocked: {e}")
            # In production: log, alert, do NOT proceed
            continue

        # Step 4: Seal the completion
        entry = seal.append(
            action=f"COMPLETE: {task}",
            metadata={"result": result, "status": "done"},
        )
        seal.export_tip(replica)
        print(f"[SEALED] Hash: {entry.entry_hash[:16]}...")

    # Final verification
    print("\n--- Final Chain Verification ---")
    result = seal.verify()
    print(f"Lines: {result.lines}")
    print(f"Tip:   {result.tip[:16]}...")
    print(f"Valid: {result.valid}")

    # Cleanup demo files
    import shutil
    shutil.rmtree("./demo_ledger", ignore_errors=True)
    shutil.rmtree("./demo_replica", ignore_errors=True)


if __name__ == "__main__":
    main()
