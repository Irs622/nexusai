"""Architecture Fitness Test — State Machine Transition Matrix.

Verifies full state transition matrix enforcement across all 10 AgentState values.
"""

from __future__ import annotations

from nexusai.brain.state_machine import AgentState, AgentStateMachine, InvalidStateTransitionError


def test_full_state_machine_transition_matrix():
    """Verify matrix of allowed and forbidden transitions across all AgentState values."""
    all_states = list(AgentState)

    for source_state in all_states:
        sm = AgentStateMachine(initial_state=source_state)
        allowed_targets = AgentStateMachine.ALLOWED_TRANSITIONS.get(source_state, set())

        for target_state in all_states:
            if target_state in allowed_targets:
                assert sm.can_transition_to(target_state) is True, (
                    f"Transition {source_state} -> {target_state} should be ALLOWED!"
                )
            else:
                assert sm.can_transition_to(target_state) is False, (
                    f"Transition {source_state} -> {target_state} should be FORBIDDEN!"
                )


if __name__ == "__main__":
    test_full_state_machine_transition_matrix()
    print("ALL STATE MACHINE MATRIX FITNESS TESTS PASSED SUCCESSFULLY!")
