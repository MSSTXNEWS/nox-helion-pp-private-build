"""Bounded NSIS source-flow model, not NSIS compilation or Windows execution.

Inject FileOpen/FileWrite error flags into the actual marker instructions.
Unknown instructions fail the model instead of being treated as success.
"""
from pathlib import Path
import re
import unittest


def marker_flow(source, failure=None, initial_error=False):
    start = source.index('  FileOpen $2 "$StageDir\\nox-p01-owned.txt" w')
    previous = source[:start].splitlines()[-1].strip()
    stop = source.index('  SetOutPath "$TEMP"', start)
    lines = ([previous] if previous == 'ClearErrors' else []) + source[start:stop].splitlines()
    code = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith(';')]
    labels = {line[:-1]: i for i, line in enumerate(code) if line.endswith(':')}
    error, opened, exit_code, pc = initial_error, False, None, 0
    writes, closes = 0, 0
    def jump(target, position):
        if target == '0':
            return position + 1
        if target.startswith(('+', '-')):
            return position + int(target)
        return labels[target]
    for _ in range(100):
        if pc >= len(code):
            return dict(reaches_activation=True, opened=opened, explicit_error_level=exit_code, writes=writes, closes=closes)
        line = code[pc]
        parts = re.findall(r'"[^\"]*"|\S+', line)
        op = parts[0]
        if line.endswith(':'):
            pass
        elif op == 'ClearErrors':
            error = False
        elif op == 'FileOpen':
            opened = failure != 'open'
            error |= not opened
        elif op == 'FileWrite':
            if not opened:
                raise AssertionError('write without an open handle')
            error |= failure == 'write'
            writes += failure != 'write'
        elif op == 'FileClose':
            if not opened:
                raise AssertionError('invalid/double close')
            opened = False
            closes += 1
        elif op == 'IfErrors':
            target = parts[1] if error else (parts[2] if len(parts) > 2 else '0')
            error = False  # NSIS IfErrors checks AND clears the flag.
            pc = jump(target, pc)
            continue
        elif op == 'Goto':
            pc = jump(parts[1], pc)
            continue
        elif op == 'SetErrorLevel':
            exit_code = int(parts[1])
        elif op == 'Abort':
            return dict(reaches_activation=False, opened=opened, explicit_error_level=exit_code, writes=writes, closes=closes)
        else:
            raise AssertionError('unmodelled NSIS instruction: ' + line)
        pc += 1
    raise AssertionError('marker flow did not terminate')


class MarkerWriteFlowTests(unittest.TestCase):
    def setUp(self):
        self.source = (Path(__file__).parent / 'NOX-HELION-Setup.nsi').read_text()

    def test_open_failure_aborts_before_activation(self):
        result = marker_flow(self.source, 'open')
        self.assertEqual(result, dict(reaches_activation=False, opened=False, explicit_error_level=2, writes=0, closes=0))

    def test_write_failure_closes_handle_and_never_activates(self):
        result = marker_flow(self.source, 'write')
        self.assertEqual(result, dict(reaches_activation=False, opened=False, explicit_error_level=2, writes=0, closes=1))

    def test_success_closes_handle_then_allows_existing_transaction(self):
        result = marker_flow(self.source)
        self.assertEqual(result, dict(reaches_activation=True, opened=False, explicit_error_level=None, writes=1, closes=1))

    def test_prior_error_cannot_contaminate_marker_operation(self):
        self.assertEqual(marker_flow(self.source, initial_error=True), marker_flow(self.source))


if __name__ == '__main__':
    unittest.main()
