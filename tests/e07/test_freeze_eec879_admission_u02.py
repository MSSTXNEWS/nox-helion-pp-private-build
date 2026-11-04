"""Strict frozen E06→independent E07 source/Setup admission (not release PASS)."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'coordination/e07/independent_setup_e07.py'
SPEC = importlib.util.spec_from_file_location('nox_e07_frozen_u02', SCRIPT)
E07 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E07)
SOURCE = 'eec879d78eef343a8bfc6a4653961bb951d1c208'
SETUP_SHA = '217cf34a3fb577f6bf20fcec2d10ebcdf4b0b616b54816bc0cdf4b78009050b0'
SOURCE_ZIP_SHA = '50cf2e318c8757bbc35b95d425d8ca33449bdc8c743a9945a3c93269c9b9628d'
HOME_SHA = '5661491ddf07b3f5fa7c8097ff64838209057bee6a0bec8ed867b8c8553a40d0'
SETUP_SIZE = 87338388


def fixture(base):
    setup = base / 'NOX_HELION_EXPRESS_CANDIDATE_SETUP.exe'
    # Sparse placeholder: positive tests mock SHA verification; executable not run.
    with setup.open('wb') as out:
        out.truncate(SETUP_SIZE)
    (base / ('NOX_HELION_EXPRESS_SOURCE_' + SOURCE + '.zip')).write_bytes(b'fake-zip')
    build = dict(schema='nox.express.onehost.same-sha.v1', source_commit=SOURCE,
                 physical_setup_built=True, setup_sha256=SETUP_SHA, setup_bytes=SETUP_SIZE,
                 build_outcome='success', classification='DIAGNOSTIC_CANDIDATE_NOT_RELEASE',
                 release_accepted=False, independent_e07='NOT_RUN')
    candidate = dict(schema='NOX-E06-ONEHOST-CANDIDATE-v1',source_git_sha=SOURCE,
                     setup_sha256=SETUP_SHA,setup_bytes=SETUP_SIZE,
                     wpf_sha256='a',backend_sha256='b',manifest_sha256='c',
                     backend_native_stdio_windows_exe_smoke='PASS',
                     wpf_source_compilation='PASS',wpf_installed_interactive_qa='NOT_RUN',
                     e07='NOT_ACCEPTED',release_accepted=False,
                     original_home_provenance=dict(five_primary_installed_uia='NOT_RUN',
                        release_accepted=False,published_home_bytes=99768,
                        published_home_sha256=HOME_SHA))
    smoke = dict(schema='NOX-T06-INSTALLED-SMOKE-v1',
            phase='INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PROVIDER_OFFLINE_HOLD_NOT_E07',
            environment='GITHUB_WINDOWS_EPHEMERAL_BRIDGE_NOT_E07',setup_sha256=SETUP_SHA,
            installed_wpf_sha256='a',installed_backend_sha256='b',manifest_sha256='c',
            e07_independent_acceptance='NOT_RUN',release_accepted=False,
            manifest_files_checked=485,
            installer_lifecycle=dict(uninstall_owned_files_checked=485,**{
                k:{'code':0} for k in ('install','verify','update','rollback','uninstall')}))
    for name, doc in [('BUILD_RECEIPT.json',build),('ONEHOST_CANDIDATE_RECEIPT.json',candidate),
                      ('T06_INSTALLED_SMOKE.json',smoke)]:
        (base / name).write_text(json.dumps(doc),encoding='utf-8')
    return setup


class FrozenEec879AdmissionU02(unittest.TestCase):
    def test_positive_physical_receipts_source_and_pe_structure(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); setup=fixture(base)
            pe=bytearray(128);pe[0:2]=b'MZ';struct.pack_into('<I',pe,0x3c,64)
            pe[64:68]=b'PE\0\0'
            with patch.object(E07,'sha256',return_value=SOURCE_ZIP_SHA) as zipped, \
                 patch.object(E07,'installed_file_sha_locked',return_value=(SETUP_SHA,bytes(pe))) as checked:
                got=E07.setup_lock_original(setup,base,frozen='eec879')
                self.assertEqual(got['source_sha'],SOURCE)
                self.assertEqual(got['setup_sha256'],SETUP_SHA)
                self.assertEqual(got['source_zip_sha256'],SOURCE_ZIP_SHA)
                self.assertEqual(got['owned_count_source_pinned'],485)
                self.assertFalse(got['release_accepted'])
                zipped.assert_called_once()
                self.assertEqual(checked.call_args.args[2],SETUP_SIZE)
                self.assertEqual(checked.call_args.args[3],SETUP_SHA)
    def test_wrong_source_or_setup_or_home_never_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);setup=fixture(base)
            for name,key,wrong,code in [
                ('BUILD_RECEIPT.json','source_commit','f'*40,'E07_ORIGINAL_BUILD_RECEIPT_HOLD'),
                ('BUILD_RECEIPT.json','setup_sha256','0'*64,'E07_ORIGINAL_BUILD_RECEIPT_HOLD'),
                ('ONEHOST_CANDIDATE_RECEIPT.json','setup_sha256','0'*64,'E07_ORIGINAL_ONEHOST_RECEIPT_HOLD'),
                ('T06_INSTALLED_SMOKE.json','manifest_files_checked',484,'E07_ORIGINAL_SAMEVM_RECEIPT_HOLD')]:
                doc=json.loads((base/name).read_text());old=doc[key];doc[key]=wrong
                (base/name).write_text(json.dumps(doc))
                with self.subTest(name=name,key=key):
                    with self.assertRaisesRegex(E07.Hold,code):
                        E07.setup_lock_original(setup,base,frozen='eec879')
                doc[key]=old;(base/name).write_text(json.dumps(doc))
            p=base/'ONEHOST_CANDIDATE_RECEIPT.json';doc=json.loads(p.read_text());
            doc['original_home_provenance']['published_home_sha256']='0'*64
            p.write_text(json.dumps(doc))
            with self.assertRaisesRegex(E07.Hold,'E07_ORIGINAL_HOME_RECEIPT_HOLD'):
                E07.setup_lock_original(setup,base,frozen='eec879')
    def test_wrong_source_zip_and_real_setup_digest_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);setup=fixture(base)
            with patch.object(E07,'sha256',return_value='0'*64):
                with self.assertRaisesRegex(E07.Hold,'E07_ORIGINAL_SOURCE_ZIP_SHA_HOLD'):
                    E07.setup_lock_original(setup,base,frozen='eec879')
            with patch.object(E07,'sha256',return_value=SOURCE_ZIP_SHA):
                with self.assertRaises(E07.Hold):
                    E07.setup_lock_original(setup,base,frozen='eec879')
    def test_legacy_freeze_stays_independent_and_workflow_pinned(self):
        workflow=(ROOT/'.github/workflows/nox-express-freeze-e07.yml').read_text()
        for x in (SOURCE,SETUP_SHA,'run-id: 41809242875',
                  'NOX-EXPRESS-ONEHOST-eec879d78eef343a8bfc6a4653961bb951d1c208',
                  '--artifact-kind original-eec879',
                  'independent_e07','release_accepted',
                  "'${{ steps.test.outcome }}' -ne 'success'"):
            self.assertIn(x,workflow)
        self.assertIn('E07_REAL_MODEL_AND_VISUAL_ACCEPTANCE_NOT_COMPLETE',SCRIPT.read_text())
        self.assertEqual(E07.ORIGINAL_E06_SOURCE,'fe21790af418c8c1083946595811b67c9c03c49d')
        self.assertEqual(E07.ORIGINAL_E06_SETUP_SHA,
                         '1b78fba3fa158673814b31f211063022fd2bff0ae7ff25f14ba3db2a47c484c2')
        with self.assertRaisesRegex(E07.Hold,'E07_ORIGINAL_PIN_KIND_HOLD'):
            E07.setup_lock_original(Path('no.exe'),Path('no'),frozen='unknown')


if __name__ == '__main__':
    unittest.main()
