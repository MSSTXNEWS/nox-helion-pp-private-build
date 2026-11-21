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

    def test_redacted_historical_s03_keeps_provenance_not_prompt_text(self):
        revision = "a" * 64
        base = {"persona_id": "persona-A", "revision": revision}
        old = {**base, "id": "old", "source_sha256": "b" * 64,
               "text": "", "status": "SUPERSEDED", "superseded_by": "current"}
        current = {**base, "id": "current", "source_sha256": "c" * 64,
                   "text": "Current verified fact.", "status": "ACTIVE",
                   "superseded_by": None}
        revoked = {**base, "id": "revoked", "source_sha256": "d" * 64,
                   "text": "", "status": "REVOKED", "superseded_by": None}
        result = plan_prompt(
            persona="NOX", system="Be precise.", conversation=[],
            verified_s03=[old, current, revoked], current_user="Continue.",
            token_counter=lambda msgs: sum(len(m["content"]) for m in msgs) // 4 + 1,
            token_budget=2048, owner_persona_id="persona-A",
            current_s03_revision=revision)
        self.assertEqual(result["selected_s03_ids"], ["current"])
        self.assertEqual([(ref["id"], ref["status"]) for ref
                          in result["historical_s03_refs"]],
                         [("old", "SUPERSEDED"), ("revoked", "REVOKED")])
        self.assertNotIn('"untrusted_text":""',
                         "\\n".join(msg["content"] for msg in result["messages"]))
        with self.assertRaisesRegex(ContextHold, "HOLD_CONTEXT_S03"):
            plan_prompt(persona="NOX", system="Be precise.", conversation=[],
                        verified_s03=[{**current, "text": ""}], current_user="Continue.",
                        token_counter=lambda msgs: 10, token_budget=2048,
                        owner_persona_id="persona-A", current_s03_revision=revision)
        with self.assertRaisesRegex(ContextHold, "HOLD_CONTEXT_S03"):
            _plan([], scoped=False)
            # The unscoped format cannot smuggle an empty active fact.


if __name__ == "__main__":
    unittest.main()
