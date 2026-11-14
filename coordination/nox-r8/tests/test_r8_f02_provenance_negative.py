"""F02 negative matrix for copied R8 IPC/SQLite tests and staged WPF sources.

Runs only on a disposable mirrored checkout. This verifies that existing
fail-closed provenance checks actually reject stale copies; it is not a
real-Windows, Qwen or owner-PC acceptance test.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import shutil
import subprocess
import sys


SOURCE = Path(__file__).resolve().parents[1]
TESTS = SOURCE / "tests"
OVERRIDES = SOURCE / "overrides" / "src"
CASES = (
    ("test_r8_ipc_contract.py", "F02_IPC_STALE_TEST_COPY_HOLD", "F02_IPC_STAGED_SOURCE_DRIFT_HOLD"),
    ("test_r8_sqlite_commit_unknown.py", "F02_SQLITE_STALE_TEST_COPY_HOLD", "F02_SQLITE_STAGED_SOURCE_DRIFT_HOLD"),
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(script, cwd):
    try:
        return subprocess.run(
            [sys.executable, str(script)], cwd=cwd, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError("F02_PROVENANCE_TEST_TIMEOUT_HOLD: " + script.name) from exc


def expected_hold(script, cwd, marker):
    result = invoke(script, cwd)
    combined = result.stdout + "\n" + result.stderr
    assert result.returncode != 0 and marker in combined, (
        f"F02_PROVENANCE_FAIL_OPEN_HOLD: {script.name} missing {marker}, "
        f"exit={result.returncode}; tail={combined[-700:]}"
    )


def write_drift(path):
    path.write_bytes(path.read_bytes() + b"\n# F02 intentional stale copy (disposable fixture)\n")


def main():
    expected_inputs = [TESTS / name for name, _, _ in CASES] + [
        OVERRIDES / "MainWindow.xaml.cs", OVERRIDES / "index.html"
    ]
    for path in expected_inputs:
        assert path.is_file(), "F02_CANONICAL_INPUT_MISSING_HOLD: " + str(path)
    before = {path: digest(path) for path in expected_inputs}

    with TemporaryDirectory(prefix="nox-r8-f02-provenance-negative-") as temp:
        checkout = Path(temp)
        staged = checkout / "r8"
        staged_src = staged / "src"
        canonical_tests = checkout / "coordination" / "nox-r8" / "tests"
        canonical_src = checkout / "coordination" / "nox-r8" / "overrides" / "src"
        staged_src.mkdir(parents=True)
        canonical_tests.mkdir(parents=True)
        canonical_src.mkdir(parents=True)
        for name in ("MainWindow.xaml.cs", "index.html"):
            shutil.copyfile(OVERRIDES / name, staged_src / name)
            shutil.copyfile(OVERRIDES / name, canonical_src / name)

        for name, stale_test_marker, stale_src_marker in CASES:
            canonical_test = canonical_tests / name
            copied_test = staged / name
            shutil.copyfile(TESTS / name, canonical_test)
            shutil.copyfile(TESTS / name, copied_test)

            # A copied test and staged native source with the same bytes pass
            # the existing full source-only contract on the disposable mirror.
            result = invoke(copied_test, checkout)
            assert result.returncode == 0, (
                f"F02_PRISTINE_MIRROR_HOLD: {name}; "
                f"exit={result.returncode}; tail={(result.stdout + result.stderr)[-900:]}"
            )

            write_drift(copied_test)
            expected_hold(copied_test, checkout, stale_test_marker)
            shutil.copyfile(TESTS / name, copied_test)

            for native_name in ("MainWindow.xaml.cs", "index.html"):
                native_path = staged_src / native_name
                write_drift(native_path)
                expected_hold(copied_test, checkout, stale_src_marker)
                shutil.copyfile(OVERRIDES / native_name, native_path)

    for path, sha in before.items():
        assert digest(path) == sha, "F02_CANONICAL_SOURCE_MUTATED_HOLD: " + str(path)
    print("F02 SOURCE_ONLY provenance mirror: 2 pristine + 6 stale-copy negative controls PASS; real Qwen/owner PC NOT_TESTED")


if __name__ == "__main__":
    main()
