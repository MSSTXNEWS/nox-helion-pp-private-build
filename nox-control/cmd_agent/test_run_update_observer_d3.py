"""D3 observer regression: command failures cannot be masked by output formatters.

Never imports run_update.py: importing it would try an actual Vast SSH operation.
Runs only the literal REMOTE script in a mock executable PATH, with no credentials.
"""
import ast
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


def observer_command():
    module = ast.parse(Path(__file__).with_name("run_update.py").read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "REMOTE" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("REMOTE literal missing")


class OwnerObserverFailClosedTest(unittest.TestCase):
    def run_observer(self, failure):
        with tempfile.TemporaryDirectory() as directory:
            scripts = {
                "supervisorctl": """#!/bin/sh
if [ "$1" != status ]; then exit 20; fi
if [ "$#" -gt 1 ]; then
  if [ "$NOX_FAIL" = train ]; then exit 31; fi
  printf 'nox-train-qwen9b-t131u RUNNING pid 1\nnox-train-keeper RUNNING pid 2\n'
else
  if [ "$NOX_FAIL" = svc ]; then exit 32; fi
  printf 'nox-proxy RUNNING pid 3\n'
fi
""",
                "df": """#!/bin/sh
if [ "$NOX_FAIL" = disk ]; then exit 33; fi
printf 'Filesystem Size Used Avail Use%% Mounted on\n/dev/mock 1G 0G 1G 0%% /\n'
""",
                "nvidia-smi": "#!/bin/sh\nprintf '0, 2 %%, 100 MiB\\n'\n",
                "python3": "#!/bin/sh\nprintf 'pending:0 ready:0 running:0 done:0 failed:0 hold:0\\n'\n",
            }
            for name, script in scripts.items():
                target = Path(directory) / name
                target.write_text(script)
                target.chmod(0o700)
            env = dict(os.environ, NOX_FAIL=failure, PATH=directory + os.pathsep + os.environ["PATH"])
            return subprocess.run(["/bin/sh", "-c", observer_command()],
                                  capture_output=True, text=True, env=env, timeout=10)

    def test_required_sources_fail_closed_before_formatting(self):
        for source, expected_rc, following_stage in (
            ("train", 41, "== gpu"),
            ("disk", 43, "== tasks"),
            ("svc", 44, None),
        ):
            with self.subTest(source=source):
                completed = self.run_observer(source)
                self.assertEqual(completed.returncode, expected_rc, completed.stdout)
                if following_stage is not None:
                    self.assertNotIn(following_stage, completed.stdout)
                self.assertNotIn("nox-train-keeper RUNNING pid 2", completed.stderr)

    def test_successful_mock_telemetry_keeps_bounded_sections(self):
        completed = self.run_observer("none")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for marker in ("== train", "== gpu", "== disk", "== tasks", "== svc"):
            self.assertIn(marker, completed.stdout)
        self.assertIn("pending:0 ready:0", completed.stdout)


if __name__ == "__main__":
    unittest.main()
