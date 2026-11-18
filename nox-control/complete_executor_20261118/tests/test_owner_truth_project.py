"""Focused source test of the existing prompt wrapper's callback-pin migration."""
import importlib.util
from pathlib import Path
import types
import unittest


HERE = Path(__file__).parent


def modules():
    raw = (HERE/'owner_subagent_dispatcher.py').read_bytes()
    callback = types.ModuleType('owner_subagent_callback_test')
    callback.__file__ = '/root/nox/scripts/owner_subagent_dispatcher.py'
    exec(compile(raw, callback.__file__, 'exec'), callback.__dict__)
    spec = importlib.util.spec_from_file_location('truth_pin_test', HERE/'owner_subagent_instruction_truth_project.py')
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    return raw, callback, wrapper


class TruthPinTests(unittest.TestCase):
    def test_three_original_roles_keep_truthful_prompt_and_native_functions(self):
        raw, callback, wrapper = modules()
        fixture = '1C: runtime\n2B: memory\n2D: weights\n'
        original = callback.model_instruction
        original_leaf = callback.execute_native_leaf
        expected = {role:original(fixture, role).replace(wrapper.OLD, wrapper.NEW, 1)
                    for role in ('runtime', 'memory', 'weights')}
        wrapper.bind(callback, lambda path:raw)
        for role in ('runtime', 'memory', 'weights'):
            with self.subTest(role=role):
                self.assertEqual(callback.model_instruction(fixture, role), expected[role])
                self.assertNotIn(wrapper.OLD, callback.model_instruction(fixture, role))
        self.assertIs(callback.execute_native_leaf, original_leaf)

    def test_unpinned_callback_remains_blocked(self):
        raw, callback, wrapper = modules()
        with self.assertRaisesRegex(RuntimeError, 'HOLD_SUBAGENT_TRUTH_SOURCE_PIN'):
            wrapper.bind(callback, lambda path:raw+b'\n')


if __name__ == '__main__':
    unittest.main()
