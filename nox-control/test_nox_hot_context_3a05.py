#!/usr/bin/env python3
"""3A05 source-only regression: owner-scoped chat cannot cross PersonaID."""
import unittest

from nox_hot_context import ContextHold, plan_prompt


def _plan(conversation, *, owner="persona-A", scoped=True):
    return plan_prompt(
        persona="NOX", system="Be precise.",
        conversation=conversation, verified_s03=[],
        current_user="Continue our discussion.",
        token_counter=lambda msgs: sum(len(m["content"]) for m in msgs) // 4 + 1,
        token_budget=2048,
        **({"owner_persona_id": owner, "current_s03_revision": "a" * 64} if scoped else {}),
    )


class ScopedConversationTests(unittest.TestCase):
    def test_matching_persona_turn_preserved(self):
        turn = {"id": "t1", "role": "assistant", "content": "Previous turn.", "persona_id": "persona-A"}
        result = _plan([turn])
        self.assertTrue(result["owner_scope_supplied_and_matched"])
        self.assertTrue(any(m.get("content") == "Previous turn." for m in result["messages"]))

    def test_wrong_persona_held_before_prompt(self):
        turn = {"id": "t1", "role": "assistant", "content": "Other person's turn.", "persona_id": "persona-B"}
        with self.assertRaisesRegex(ContextHold, "HOLD_CONTEXT_TURN_PERSONA"):
            _plan([turn])

    def test_missing_persona_metadata_held_for_scoped_snapshot(self):
        turn = {"id": "t1", "role": "assistant", "content": "Unscoped history."}
        with self.assertRaisesRegex(ContextHold, "HOLD_CONTEXT_TURN_SCOPE"):
            _plan([turn])

    def test_legacy_unscoped_turn_unchanged(self):
        turn = {"id": "t1", "role": "assistant", "content": "Legacy history."}
        result = _plan([turn], scoped=False)
        self.assertFalse(result["owner_scope_supplied_and_matched"])
        self.assertTrue(any(m.get("content") == "Legacy history." for m in result["messages"]))


if __name__ == "__main__":
    unittest.main()
