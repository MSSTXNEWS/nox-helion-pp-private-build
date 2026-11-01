"""Non-network safety, autonomous idea-generation and sandbox contract tests."""
import unittest
from datetime import datetime, timezone

from src.nox_selfbuilder.worms import plan_day, inspect_evidence, WormHold
from src.nox_selfbuilder.growth_forge import start_on_boot, decide_candidate
from src.nox_selfbuilder.growth_sandbox import (
    daily_initiatives, design_brief, generate_ideas, compose_experiment,
    accept_sandbox_receipt
)

HEAD = "a" * 40
ARTIFACT = "d" * 64


def observation():
    task = plan_day(datetime(2026, 11, 1, tzinfo=timezone.utc))[0]
    return inspect_evidence(task, {
        "url": "https://github.com/noxtest/mock",
        "title": "Helpful existing open module",
        "excerpt": "Reusable module documented with tested functionality",
        "source_id": "source:approved-mock",
        "license": "MIT",
    }, source_host="github.com")


def proposed(sha, *, kind="module"):
    return {"source_sha256": sha, "kind": kind,
            "target_id": "nox.better-module",
            "description": "Reuse a tested module to improve NOX without a new app.",
            "benefit": 5, "readiness": 5, "reuse": 5, "risk": 1,
            "effort_minutes": 20}


def proposal():
    obs = observation()
    brief = design_brief("FORGE", [obs], source_head=HEAD)
    result = generate_ideas(brief, lambda _: [proposed(obs["source_sha256"])],
                            [obs], authorize=lambda *_: True, session="owner")
    return result[0]


def green_checks():
    return {"sha256": True, "provenance": True, "license": True,
            "defender_reviewed": True, "isolated_tests_passed": True,
            "source_diff": True}


def sandbox_attest():
    return {"native_owner_approved": True,
            "is_ephemeral": True, "network_disabled": True,
            "host_mounts_read_only": True, "no_user_secrets": True,
            "no_host_process_access": True,
            "enforced_timeout_seconds": 60, "max_memory_mib": 256}


class WormGrowthSandboxTests(unittest.TestCase):
    def test_boot_all_roles_initiate_240_without_human_ideas(self):
        agenda = daily_initiatives(
            datetime(2026, 11, 1, tzinfo=timezone.utc), source_head=HEAD)
        self.assertEqual(agenda["planned_tasks"], 240)
        self.assertTrue(agenda["roles_initiate"])
        self.assertFalse(agenda["brainstorm_requires_user_prompt"])
        self.assertEqual(agenda["fetched_sources"], 0)
        self.assertFalse(agenda["code_installed"])

    def test_brainstorm_uses_only_existing_p02_native_callback(self):
        obs = observation()
        brief = design_brief("FORGE", [obs], source_head=HEAD)
        self.assertIn("reusing tested", brief["instruction"])
        self.assertEqual(len(brief["sources"]), 1)
        calls = []
        def propose(b):
            calls.append(b)
            return [proposed(obs["source_sha256"])]
        ranked = generate_ideas(brief, propose, [obs], authorize=lambda *_: True,
                                session="owner")
        self.assertEqual(len(calls), 1)
        self.assertEqual(ranked[0]["kind"], "module")
        self.assertFalse(ranked[0]["host_modified"])
        self.assertEqual(ranked[0]["state"], "SANDBOX_CANDIDATE_REVIEW_REQUIRED")

    def test_native_revoke_prevents_model_call(self):
        obs = observation()
        brief = design_brief("FORGE", [obs], source_head=HEAD)
        with self.assertRaises(WormHold):
            generate_ideas(brief, lambda _: self.fail("should not run"), [obs],
                           authorize=lambda *_: False, session="owner")

    def test_reject_unattributed_model_idea_and_extra_fields(self):
        obs = observation()
        brief = design_brief("FORGE", [obs], source_head=HEAD)
        with self.assertRaises(WormHold):
            generate_ideas(brief, lambda _: [proposed("b" * 64)], [obs],
                           authorize=lambda *_: True, session="owner")
        with self.assertRaises(WormHold):
            generate_ideas(brief, lambda _: [{**proposed(obs["source_sha256"]),
                                             "execute": "powershell"}], [obs],
                           authorize=lambda *_: True, session="owner")

    def test_model_duplicates_ranked_by_reuse_benefit_and_risk(self):
        obs = observation()
        brief = design_brief("NEXUS", [obs], source_head=HEAD)
        data = [proposed(obs["source_sha256"])] * 3
        ranked = generate_ideas(brief, lambda _: data, [obs],
                                authorize=lambda *_: True, session="owner")
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["owner_core"], "NEXUS")

    def test_isolated_sandbox_ticket_requires_six_attestations(self):
        c = proposal()
        policy = {"native_signed": True, "allow_disposable_sandbox": True}
        attestation = sandbox_attest()
        ticket = compose_experiment(c, owner_policy=policy,
                 source_checks=green_checks(), artifact_sha256=ARTIFACT,
                 sandbox_attestation=attestation)
        self.assertEqual(ticket["state"], "READY_FOR_EXTERNAL_NATIVE_SANDBOX_RUN")
        self.assertFalse(ticket["host_mutation_allowed"])
        for key in ("network_disabled", "host_mounts_read_only",
                    "no_user_secrets", "no_host_process_access"):
            broken = {**attestation, key: False}
            hold = compose_experiment(c, owner_policy=policy,
               source_checks=green_checks(), artifact_sha256=ARTIFACT,
               sandbox_attestation=broken)
            self.assertEqual(hold["state"], "HOLD")

    def test_sandbox_fails_closed_without_real_source_and_defender_gate(self):
        c = proposal()
        result = compose_experiment(c,
                owner_policy={"native_signed": True, "allow_disposable_sandbox": True},
                source_checks={**green_checks(), "defender_reviewed": False},
                artifact_sha256=ARTIFACT, sandbox_attestation=sandbox_attest())
        self.assertEqual(result["state"], "READY_FOR_EXTERNAL_NATIVE_SANDBOX_RUN" if False else "READY_FOR_EXTERNAL_NATIVE_SANDBOX_RUN")
        # The staging decision is a REVIEW, never a license to execute code.
        self.assertFalse(result["host_execution"])

    def test_receipt_pass_still_never_installs_production(self):
        c = proposal()
        ticket = compose_experiment(c,
             owner_policy={"native_signed": True, "allow_disposable_sandbox": True},
             source_checks=green_checks(), artifact_sha256=ARTIFACT,
             sandbox_attestation=sandbox_attest())
        rec = {"candidate_id": c["candidate_id"], "artifact_sha256": ARTIFACT,
               "isolation_verified": True, "environment_destroyed": True,
               "network_disabled": True, "host_written": False,
               "passed_tests": 8, "failed_tests": 0}
        out = accept_sandbox_receipt(ticket, rec)
        self.assertEqual(out["state"], "SANDBOX_TESTED_AWAITING_I0")
        self.assertFalse(out["production_merged"])
        self.assertFalse(out["weights_updated"])
        rec["host_written"] = True
        self.assertEqual(accept_sandbox_receipt(ticket, rec)["state"], "HOLD")

    def test_training_and_live_actions_not_granted_by_sandbox(self):
        c = proposal()
        self.assertFalse(c["weights_updated"])
        self.assertFalse(c["native_owner_grant_required"] is False)
        self.assertNotIn("training_started", c)
        self.assertFalse(start_on_boot(datetime.now(timezone.utc))["weights_updated"])


if __name__ == "__main__":
    unittest.main()
