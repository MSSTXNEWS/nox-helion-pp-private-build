import base64, hashlib, importlib.util, io, json, os, pathlib, tempfile, unittest
from contextlib import redirect_stdout
from unittest.mock import patch

SOURCE=pathlib.Path(__file__).resolve().parents[1]/'owner_memory_chat_acceptance.py'

class FailureDoesNotRunDependentStages(unittest.TestCase):
    def test_s03_recovery_hold_skips_all_downstream_stages(self):
        spec=importlib.util.spec_from_file_location('a3_acceptance', SOURCE)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        executed=[]
        raw_first=b'def main():\n    return 2\n'
        raw_second=b'raise RuntimeError("MUST_NOT_EVEN_IMPORT_SECOND")\n'
        raw_third=b'raise RuntimeError("MUST_NOT_EVEN_IMPORT_THIRD")\n'
        names=('owner_s03_recover_activate.py','owner_chat_layout_entry.py','owner_browser_qa_entry.py')
        raws=(raw_first,raw_second,raw_third)
        module.STAGES=tuple((n,hashlib.sha256(raw).hexdigest()) for n,raw in zip(names,raws))
        module.BUNDLE={n:base64.b64encode(raw).decode() for n,raw in zip(names,raws)}
        module.emit=lambda kind,data:executed.append((kind,data))
        with tempfile.TemporaryDirectory() as t, patch.object(module,'Path',lambda _:pathlib.Path(t)):
            result=module.main()
        self.assertEqual(result,2)
        self.assertEqual(len([x for x in executed if x[0]=='memory_chat_component_hold']),1)
        self.assertEqual(executed[0][1]['component'],names[0])
        self.assertEqual(executed[0][1]['reason'],'HOLD_ACCEPTANCE_COMPONENT_RESULT')
        self.assertEqual(len(executed),2)
        self.assertEqual(executed[-1][1]['failed'][0]['component'],names[0])

    def test_s03_system_exit_does_not_bypass_receipt_or_run_dependent_stages(self):
        for raw_first in (
            b'def main():\n    raise SystemExit(0)\n',
            b'raise SystemExit(0)\n',
        ):
            with self.subTest(raw_first=raw_first):
                spec=importlib.util.spec_from_file_location('a3_exit_acceptance', SOURCE)
                module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                emitted=[]
                raws=(raw_first, b'raise AssertionError("SECOND_STAGE_MUST_NOT_RUN")\n')
                names=('owner_s03_recover_activate.py','owner_chat_layout_entry.py')
                module.STAGES=tuple((name,hashlib.sha256(raw).hexdigest()) for name,raw in zip(names,raws))
                module.BUNDLE={name:base64.b64encode(raw).decode() for name,raw in zip(names,raws)}
                module.emit=lambda kind,data:emitted.append((kind,data))
                with tempfile.TemporaryDirectory() as t, patch.object(module,'Path',lambda _:pathlib.Path(t)):
                    result=module.main()
                self.assertEqual(result,2)
                self.assertEqual(len(emitted),2)
                self.assertEqual(emitted[0],('memory_chat_component_hold',
                    {'component':names[0], 'reason':'HOLD_ACCEPTANCE_COMPONENT_SYSTEM_EXIT'}))
                self.assertEqual(emitted[1][0],'memory_chat_batch')
                self.assertEqual(emitted[1][1]['failed'],[emitted[0][1]])


    def test_program_stop_blocks_s03_and_all_dependent_stages(self):
        """Program-level STOP is a native STOP location; never enter S03."""
        spec=importlib.util.spec_from_file_location('a3_program_stop', SOURCE)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        name='owner_s03_recover_activate.py'
        raw=(b'BUNDLE=__NOX_BUNDLE_JSON__\n'
             b'def main():\n'
             b'    BUNDLE["s03_stage_executed"]=True\n'
             b'    return 0\n')
        # Deliberately fail if the S03 stage is entered at all.
        module.STAGES=((name,hashlib.sha256(raw).hexdigest()),)
        module.BUNDLE={name:base64.b64encode(raw).decode()}
        emitted=[]
        module.emit=lambda kind,data:emitted.append((kind,data))
        with tempfile.TemporaryDirectory() as t:
            flag=pathlib.Path(t)/'program/STOP'
            flag.parent.mkdir()
            flag.touch()
            with patch.object(module,'Path',lambda _:pathlib.Path(t)):
                with redirect_stdout(io.StringIO()) as output:
                    result=module.main()
        self.assertEqual(result,2)
        self.assertNotIn('s03_stage_executed',module.BUNDLE)
        self.assertNotIn('NOX_MAINT_REPAIR_COMPLETE=true',output.getvalue())
        self.assertEqual(emitted,[
            ('memory_chat_batch',{
                'failed':[{'component':name,'reason':'HOLD_OWNER_STOP'}],
                'training_started':False,'private_content_exported':False}),
        ])

    def test_stop_during_final_stage_cannot_claim_success(self):
        spec=importlib.util.spec_from_file_location('a3_stop_acceptance', SOURCE)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as t:
            name='owner_s03_recover_activate.py'
            raw=(
                b'from pathlib import Path\n'
                b'def main():\n'
                + f'    (Path({t!r}) / "STOP").touch()\n'.encode()
                + b'    return 0\n'
            )
            module.STAGES=((name,hashlib.sha256(raw).hexdigest()),)
            module.BUNDLE={name:base64.b64encode(raw).decode()}
            emitted=[]
            module.emit=lambda kind,data:emitted.append((kind,data))
            with patch.object(module,'Path',lambda _:pathlib.Path(t)):
                result=module.main()
        self.assertEqual(result,2)
        self.assertEqual(emitted,[
            ('memory_chat_component_hold',{'component':name,'reason':'HOLD_OWNER_STOP'}),
            ('memory_chat_batch',{
                'failed':[{'component':name,'reason':'HOLD_OWNER_STOP'}],
                'training_started':False,'private_content_exported':False}),
        ])

    def test_browser_receipt_requires_native_stream_and_s03_readback(self):
        spec=importlib.util.spec_from_file_location('a3_receipt_acceptance', SOURCE)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        name='owner_browser_qa_entry.py'
        raw=b'def main():\n    return None\n'
        # Use a real source payload; only the private synthetic receipt is simulated.
        module.STAGES=((name, hashlib.sha256(raw).hexdigest()),)
        module.BUNDLE={name:base64.b64encode(raw).decode()}
        emitted=[]
        module.emit=lambda kind,data:emitted.append((kind,data))
        request, source='701', 'e'*40
        with tempfile.TemporaryDirectory() as t:
            receipt=pathlib.Path(t)/'state/owner_browser_qa'/request/'receipt.json'
            receipt.parent.mkdir(parents=True)
            with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':request,'NOX_OWNER_SOURCE_SHA':source}), patch.object(module,'Path',lambda _:pathlib.Path(t)):
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(module.main(),2)
                self.assertNotIn('NOX_MAINT_REPAIR_COMPLETE=true',output.getvalue())
                self.assertEqual(emitted[0][1]['reason'],'HOLD_BROWSER_QA_RECEIPT_MISSING')
                proof={'schema':'NOX_OWNER_NATIVE_BROWSER_QA_V1','request':request,'source_sha':source,
                       'state':'PASSED','functional_acceptance_verified':True,
                       'actual_native_model_stream_verified':True,'s03_readback_verified':True,
                       'screenshot_capture_verified':True,'synthetic_backend_used':False,
                       'private_text_or_credentials_exported':False,
                       'actual_native_backend':True,'nonloopback_auth':True,
                       'empty_dialog_history_verified':True,'synthetic_number_sequence_pass':True,
                       'progressive_stream_render_verified':True,
                       'stop_visible_during_generation':True,
                       'two_turn_mode':True,
                       'multiturn_dialog_history_verified':True,
                       'multiturn_canonical_s03_verified':True,
                       'multiturn_second_native_equal':True,
                       'multiturn_second_terminal_saved':True,
                       'multiturn_second_visible_progressive':True,
                       'multiturn_second_stop_visible':True,
                       'multiturn_second_numeric_pass':True,
                       'multiturn_browser_acceptance_verified':True,
                       'multiturn_native_post_count':2}
                # This receipt was written BEFORE the browser stage; all fields
                # match, but accepting it would replay a prior acceptance.
                receipt.write_text(json.dumps(proof))
                emitted.clear()
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(module.main(),2)
                self.assertNotIn('NOX_MAINT_REPAIR_COMPLETE=true',output.getvalue())
                self.assertEqual(emitted[0][1]['reason'],'HOLD_BROWSER_QA_RECEIPT_STALE')

                def install_fresh_receipt_stage(payload):
                    # Synthetic writer only: no claim of live serving acceptance.
                    raw_fresh=(
                        'import json\nfrom pathlib import Path\n'
                        'def main():\n'
                        f'    Path({str(receipt)!r}).write_text({json.dumps(payload)!r})\n'
                        '    return None\n'
                    ).encode()
                    module.STAGES=((name,hashlib.sha256(raw_fresh).hexdigest()),)
                    module.BUNDLE={name:base64.b64encode(raw_fresh).decode()}

                proof['s03_readback_verified']=False
                install_fresh_receipt_stage(proof)
                emitted.clear()
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(module.main(),2)
                self.assertEqual(emitted[0][1]['reason'],'HOLD_BROWSER_QA_RECEIPT_INCOMPLETE')

                proof['s03_readback_verified']=True
                # The native producer reports these independent observations.
                # A successful exit or one-turn memory readback alone is not
                # evidence of progressive streaming and authenticated backend.
                for missing_evidence in (
                    'actual_native_backend', 'nonloopback_auth',
                    'empty_dialog_history_verified', 'synthetic_number_sequence_pass',
                    'progressive_stream_render_verified', 'stop_visible_during_generation'):
                    proof[missing_evidence]=False
                    install_fresh_receipt_stage(proof)
                    emitted.clear()
                    with self.subTest(missing_evidence=missing_evidence), redirect_stdout(io.StringIO()):
                        self.assertEqual(module.main(),2)
                        self.assertEqual(emitted[0][1]['reason'],
                                         'HOLD_BROWSER_QA_RECEIPT_INCOMPLETE')
                    proof[missing_evidence]=True
                # A green first turn does not establish four-message S03;
                # the producer requires a separately bound canonical S03 proof.
                for missing_multiturn in (
                    'two_turn_mode', 'multiturn_dialog_history_verified',
                    'multiturn_canonical_s03_verified', 'multiturn_second_native_equal',
                    'multiturn_second_terminal_saved', 'multiturn_second_visible_progressive',
                    'multiturn_second_stop_visible', 'multiturn_second_numeric_pass',
                    'multiturn_browser_acceptance_verified'):
                    proof[missing_multiturn]=False
                    install_fresh_receipt_stage(proof)
                    emitted.clear()
                    with self.subTest(missing_multiturn=missing_multiturn), redirect_stdout(io.StringIO()):
                        self.assertEqual(module.main(),2)
                        self.assertEqual(emitted[0][1]['reason'],
                                         'HOLD_BROWSER_QA_RECEIPT_INCOMPLETE')
                    proof[missing_multiturn]=True
                for wrong_native_post_count in (None, 1, 3, True, '2'):
                    proof['multiturn_native_post_count']=wrong_native_post_count
                    install_fresh_receipt_stage(proof)
                    emitted.clear()
                    with self.subTest(native_posts=wrong_native_post_count), redirect_stdout(io.StringIO()):
                        self.assertEqual(module.main(),2)
                        self.assertEqual(emitted[0][1]['reason'],
                                         'HOLD_BROWSER_QA_RECEIPT_INCOMPLETE')
                proof['multiturn_native_post_count']=2
                install_fresh_receipt_stage(proof)
                emitted.clear()
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(module.main(),0)
                self.assertIn('NOX_MAINT_REPAIR_COMPLETE=true',output.getvalue())
                self.assertEqual(emitted[-1][1]['failed'],[])

    def test_inventory_mode_cannot_masquerade_as_browser_acceptance(self):
        spec=importlib.util.spec_from_file_location('a3_inventory_acceptance', SOURCE)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        names=('owner_s03_recover_activate.py','owner_browser_qa_entry.py')
        raws=(
            b'BUNDLE=__NOX_BUNDLE_JSON__\ndef main():\n    BUNDLE["executed_s03"]=True\n    return 0\n',
            b'BUNDLE=__NOX_BUNDLE_JSON__\ndef main():\n    BUNDLE["executed_browser"]=True\n    return None\n',
        )
        module.STAGES=tuple((n,hashlib.sha256(raw).hexdigest()) for n,raw in zip(names,raws))
        module.BUNDLE={n:base64.b64encode(raw).decode() for n,raw in zip(names,raws)}
        emitted=[]
        module.emit=lambda kind,data:emitted.append((kind,data))
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ,{'NOX_BROWSER_QA_MODE':'inventory'}), patch.object(module,'Path',lambda _:pathlib.Path(t)):
            result=module.main()
        self.assertEqual(result,2)
        self.assertNotIn('executed_s03',module.BUNDLE)
        self.assertNotIn('executed_browser',module.BUNDLE)
        failure={'component':names[-1],'reason':'HOLD_BROWSER_QA_INVENTORY_MODE'}
        self.assertEqual(emitted,[
            ('memory_chat_component_hold',failure),
            ('memory_chat_batch',{'failed':[failure],'training_started':False,'private_content_exported':False}),
        ])


    def test_receipt_ambiguous_json_evidence_is_rejected(self):
        """Duplicate booleans and nonstandard numbers cannot certify S03."""
        spec=importlib.util.spec_from_file_location('a3_strict_receipt', SOURCE)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        request, source='701', 'e'*40
        proof={'schema':'NOX_OWNER_NATIVE_BROWSER_QA_V1',
               'request':request,'source_sha':source,'state':'PASSED',
               'functional_acceptance_verified':True,
               'actual_native_model_stream_verified':True,
               's03_readback_verified':True,'screenshot_capture_verified':True,
               'actual_native_backend':True,'nonloopback_auth':True,
               'empty_dialog_history_verified':True,
               'synthetic_number_sequence_pass':True,
               'progressive_stream_render_verified':True,
               'stop_visible_during_generation':True,
               'synthetic_backend_used':False,
               'private_text_or_credentials_exported':False}
        original=json.dumps(proof, separators=(',', ':'))
        exact='"s03_readback_verified":true'
        self.assertIn(exact, original)
        duplicates=original.replace(exact,
            '"s03_readback_verified":false,"s03_readback_verified":true',1)
        nonfinite=original[:-1]+',"unexpected_evidence":NaN}'
        with tempfile.TemporaryDirectory() as t:
            receipt=pathlib.Path(t)/'state/owner_browser_qa'/request/'receipt.json'
            receipt.parent.mkdir(parents=True)
            with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':request,
                                       'NOX_OWNER_SOURCE_SHA':source}), patch.object(module,'Path',lambda _:pathlib.Path(t)):
                for label, body in (('duplicate-key',duplicates),('nonfinite',nonfinite)):
                    with self.subTest(label=label):
                        receipt.write_text(body, encoding='utf-8')
                        with self.assertRaisesRegex(RuntimeError, r'^HOLD_BROWSER_QA_RECEIPT_FORMAT$'):
                            module.verify_browser_receipt(0)


    def test_browser_receipt_fifo_never_blocks_acceptance(self):
        """The native receipt path must be a regular file, never a FIFO/device."""
        import time
        spec=importlib.util.spec_from_file_location('a3_fifo_receipt', SOURCE)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        request, source='701', 'e'*40
        with tempfile.TemporaryDirectory() as t:
            fifo=pathlib.Path(t)/'state/owner_browser_qa'/request/'receipt.json'
            fifo.parent.mkdir(parents=True)
            os.mkfifo(fifo)
            with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':request,
                                       'NOX_OWNER_SOURCE_SHA':source}), patch.object(module,'Path',lambda _:pathlib.Path(t)):
                started=time.monotonic()
                with self.assertRaisesRegex(RuntimeError, r'^HOLD_BROWSER_QA_RECEIPT_TYPE$'):
                    module.verify_browser_receipt(0)
                self.assertLess(time.monotonic()-started,1.0)


if __name__=='__main__':unittest.main()
