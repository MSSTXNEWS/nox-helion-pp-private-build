"""Deterministic POSITIVE/NEGATIVE QA for the original E07 handoff preflight."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from check_preflight_order_r14 import check

GOOD = '''python qa/source_ready/strict_receipt_json_r13.py --original $Original729Receipt --owner $Owner729Receipt --onehost $OneHostReceipt
if ($LASTEXITCODE -ne 0) { throw 'INVALID_E07_RECEIPT' }
$source=Get-Content -Raw $Original729Receipt | ConvertFrom-Json
$owner=Get-Content -Raw $Owner729Receipt | ConvertFrom-Json
$onehost=Get-Content -Raw $OneHostReceipt | ConvertFrom-Json
[IO.FileMode]::CreateNew
E07_BUILDID_SEALED
'''

class TestPreflightOrder(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root/'coordination/e06/Emit-E07ImmutableHandoff.ps1'
        self.script.parent.mkdir(parents=True)
        self.helper = self.root/'qa/source_ready/strict_receipt_json_r13.py'
        self.helper.parent.mkdir(parents=True)
        self.helper.write_text('# reviewed fixture only')
        self.sha = hashlib.sha256(self.helper.read_bytes()).hexdigest()
        self.script.write_text(GOOD)

    def verify(self):
        return check(self.root, expected_helper_sha=self.sha)

    def test_valid_preflight_only_source(self):
        result = self.verify()
        self.assertEqual(result['status'], 'PASS_SOURCE_ORDER_ONLY')
        self.assertFalse(result['release_accepted'])

    def test_missing_helper_holds(self):
        self.helper.unlink()
        with self.assertRaisesRegex(ValueError, 'NOT_ADMITTED'): self.verify()

    def test_modified_helper_holds(self):
        self.helper.write_text('print("skip")')
        with self.assertRaisesRegex(ValueError, 'SHA_MISMATCH'): self.verify()

    def test_comment_only_helper_holds(self):
        self.script.write_text(GOOD.replace('python qa/source_ready', '#python qa/source_ready'))
        with self.assertRaisesRegex(ValueError, 'CALL_NOT_BEFORE'): self.verify()

    def test_helper_after_parser_holds(self):
        line=GOOD.splitlines()[0]
        self.script.write_text(GOOD.replace(line+'\n','')+'\n'+line)
        with self.assertRaisesRegex(ValueError, 'CALL_NOT_BEFORE'): self.verify()

    def test_missing_guard_holds(self):
        self.script.write_text(GOOD.replace("if ($LASTEXITCODE -ne 0) { throw 'INVALID_E07_RECEIPT' }", 'Write-Host OK'))
        with self.assertRaisesRegex(ValueError, 'IMMEDIATELY_GUARDED'): self.verify()

    def test_unrelated_command_before_guard_holds(self):
        self.script.write_text(GOOD.replace('if ($LASTEXITCODE', 'some.exe --version\nif ($LASTEXITCODE'))
        with self.assertRaisesRegex(ValueError, 'IMMEDIATELY_GUARDED'): self.verify()

    def test_wrong_owner_receipt_holds(self):
        self.script.write_text(GOOD.replace('$Owner729Receipt', '$WrongOwner'))
        with self.assertRaisesRegex(ValueError, 'CALL_NOT_BEFORE'): self.verify()

    def test_no_throw_guard_holds(self):
        self.script.write_text(GOOD.replace("throw 'INVALID_E07_RECEIPT'",'Write-Host PASS'))
        with self.assertRaisesRegex(ValueError, 'IMMEDIATELY_GUARDED'): self.verify()

    def test_no_build_seal_holds(self):
        self.script.write_text(GOOD.replace('E07_BUILDID_SEALED',''))
        with self.assertRaisesRegex(ValueError, 'IMMUTABLE_SEAL'): self.verify()

    def test_double_build_seal_holds(self):
        self.script.write_text(GOOD+'E07_BUILDID_SEALED')
        with self.assertRaisesRegex(ValueError, 'IMMUTABLE_SEAL'): self.verify()

    def test_no_create_new_holds(self):
        self.script.write_text(GOOD.replace('CreateNew','Create'))
        with self.assertRaisesRegex(ValueError, 'IMMUTABLE_SEAL'): self.verify()

    def test_multiline_comment_holds(self):
        self.script.write_text('<#\n'+GOOD+'#>\n')
        with self.assertRaisesRegex(ValueError, 'BLOCK_COMMENT'): self.verify()

    def test_helper_in_here_string_does_not_execute(self):
        invocation_and_guard = GOOD.split('$source=')[0]
        fake = "$evidence = @'\n" + invocation_and_guard + "'@\n$source=" + GOOD.split('$source=')[1]
        self.script.write_text(fake)
        with self.assertRaisesRegex(ValueError, 'HERESTRING'):
            self.verify()

    def test_helper_inside_dead_conditional_not_accepted(self):
        invocation_and_guard = GOOD.split('$source=')[0]
        fake = 'if ($false) {\n' + invocation_and_guard + '}\n$source=' + GOOD.split('$source=')[1]
        self.script.write_text(fake)
        with self.assertRaisesRegex(ValueError, 'TOP_LEVEL'):
            self.verify()

    def test_non_throw_message_does_not_satisfy_guard(self):
        self.script.write_text(GOOD.replace("throw 'INVALID_E07_RECEIPT'", 'Write-Host "throw"'))
        with self.assertRaisesRegex(ValueError, 'IMMEDIATELY_GUARDED'):
            self.verify()

    def test_nested_function_not_accepted(self):
        invocation_and_guard = GOOD.split('$source=')[0]
        fake = 'function NeverCalled {\n' + invocation_and_guard + '}\n$source=' + GOOD.split('$source=')[1]
        self.script.write_text(fake)
        with self.assertRaisesRegex(ValueError, 'TOP_LEVEL'):
            self.verify()

if __name__ == '__main__': unittest.main()
