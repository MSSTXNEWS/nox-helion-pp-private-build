"""Guard the documented C01-C08 source binding contract."""
from __future__ import annotations

import ast
from dataclasses import MISSING, fields
import inspect
import textwrap
from pathlib import Path
import unittest

from nox_runpod.teacher_mesh.v38.native_bridge_v38 import AttachedNOX, HostBindings
from nox_runpod.teacher_mesh.v38.synaptic_brain import CORE_NAMES, NativePorts, SynapticBrain


class V38BindingContractTests(unittest.TestCase):
    def test_adapter_required_and_optional_host_bindings_match_source(self):
        required = {"authorize", "stop", "s03_recall", "s03_append", "model_stream"}
        optional = {
            "sensors", "self_receipts", "affect", "preferences",
            "available_skills", "queue_status", "memory_scope_authorize",
            "s03_indexed_recall", "s03_backup", "s03_backup_verify",
        }
        host_defaults = {field.name: field.default for field in fields(HostBindings)}
        for name in required:
            self.assertIs(host_defaults[name], MISSING, name)
        for name in optional:
            self.assertIsNone(host_defaults[name], name)

        native_defaults = {field.name: field.default for field in fields(NativePorts)}
        self.assertIs(native_defaults["authorize"], MISSING)
        self.assertIs(native_defaults["stop"], MISSING)
        for name in (
            "sensors", "s03_recall", "self_receipts", "affect", "preferences",
            "available_skills", "queue_status", "memory_scope_authorize",
        ):
            self.assertIsNone(native_defaults[name], name)

        init_source = inspect.getsource(AttachedNOX.__init__)
        for binding in (
            "sensors=host.sensors",
            "s03_recall=self.cache",
            "self_receipts=host.self_receipts",
            "affect=host.affect",
            "preferences=host.preferences",
            "available_skills=host.available_skills",
            "queue_status=host.queue_status",
            "memory_scope_authorize=host.memory_scope_authorize",
        ):
            self.assertIn(binding, init_source)

    def test_each_group_reads_only_its_documented_host_ports(self):
        source = inspect.getsource(SynapticBrain._core)
        tree = ast.parse(textwrap.dedent(source))

        def branch_for(group):
            for node in ast.walk(tree):
                if not isinstance(node, ast.If):
                    continue
                test = node.test
                if (isinstance(test, ast.Compare)
                        and isinstance(test.left, ast.Name)
                        and test.left.id == "code"
                        and len(test.ops) == 1
                        and isinstance(test.comparators[0], ast.Constant)
                        and test.comparators[0].value == group):
                    return node
            self.fail("missing source branch for " + group)

        expected = {
            "C01": {"sensors"},
            "C02": {"s03_recall", "memory_scope_authorize"},
            "C03": {"self_receipts"},
            "C04": {"affect", "preferences"},
            "C05": set(),
            "C06": set(),
            "C07": {"available_skills"},
            "C08": {"queue_status"},
        }
        self.assertEqual(set(CORE_NAMES), set(expected))
        for group, names in expected.items():
            branch = branch_for(group)
            actual = {
                node.attr for node in ast.walk(branch)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "p"
            }
            self.assertEqual(actual, names, group)

        gate_source = inspect.getsource(SynapticBrain._gate)
        self.assertIn("self.ports.stop()", gate_source)
        self.assertIn("self.ports.authorize(session)", gate_source)
        self.assertIn('"stop": False', source)
        self.assertIn('"exec_from_chat": False', source)

    def test_readme_has_an_explicit_eight_group_contract_and_unbound_warning(self):
        readme = Path(__file__).resolve().parents[1] / "README_RU.md"
        text = readme.read_text(encoding="utf-8")
        for group in CORE_NAMES:
            self.assertIn("| " + group + " |", text)
        self.assertIn("C05", text)
        self.assertIn("C06", text)
        self.assertIn("C07", text)
        self.assertIn("C08", text)
        self.assertIn("native_callbacks_bound=false", text)
        self.assertIn("live_vast_installed=false", text)
        self.assertNotIn("Группы параллельно получают данные через реальные native callbacks", text)

    def test_owner_chat_source_does_not_import_the_v38_adapter(self):
        repo_root = Path(__file__).resolve().parents[4]
        owner_chat = (repo_root / "nox-control" / "owner_chat_stream.py").read_text(encoding="utf-8")
        self.assertNotIn("AttachedNOX", owner_chat)
        self.assertNotIn("SynapticBrain", owner_chat)


if __name__ == "__main__":
    unittest.main()
