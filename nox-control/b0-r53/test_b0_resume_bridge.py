import hashlib
import json
import unittest
from b0_resume_bridge import bind_existing_resume, owner_prefix_sha
from b5_r55_pinned import digest, multiturn_transcript_sha256

DIALOG = "a" * 32
SESSION = "fixture-owner"
def wire(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()

def rows(n):
    pairs = [("Привет", "¡Hola! 🪐"), ("¿Recuerdas?", "Помню."),
             ("¿Y después?", "Sí, recuerdo.")]
    return [dict(role=role, content=text, message_id=f"row-{i}",
                 dialog_id=DIALOG, session_id=SESSION)
            for i, (role,text) in enumerate(
                [(role,text) for pair in pairs[:n] for role,text in
                 zip(("user","assistant"),pair)], 1)]
def witnesses(items):
    seq = len(items)//2
    common = dict(source="canonical_s03", event_id=f"evt-{seq}",
                  turn_id=f"turn-{seq}", sequence=seq, dialog_id=DIALOG,
                  session_id=SESSION,
                  full_transcript_sha256=multiturn_transcript_sha256(
                      items, expected_sequence=seq, _prefix_only=seq == 1),
                  message_ids_sha256=digest(wire([r["message_id"] for r in items])))
    w = wire(dict(common, verified=True, durable=True))
    r = wire(dict(common, independent=True, messages=items,
                  full_answer_sha256=digest(items[-1]["content"].encode())))
    return w,r,digest(w),digest(r)

def fixture(n):
    old = rows(n)
    owner = [dict(r, owner_metadata="unchanged") for r in old]
    pin = owner_prefix_sha(DIALOG,owner)
    preflight = dict(scope="EXISTING_OWNER_DIALOG_PREFIX_ONLY_NOT_INDEPENDENT_S03",
                     prefix_rows=len(owner), prefix_sha256=pin,
                     dialog_id_sha256=hashlib.sha256(DIALOG.encode()).hexdigest(),
                     prefix_pin_matched=True, model_post_issued=False,
                     dialog_created=False, browser_multiturn_accepted=False,
                     native_s03_independently_verified=False, production_accepted=False)
    return dict(preflight=preflight, expected_owner_sha=pin, dialog_id=DIALOG,
                session_id=SESSION, owner_rows=owner, canonical_rows=old,
                prior_witnesses=witnesses(old), browser_calls=7, admitted_calls=7)
class B0ResumeBridgeTests(unittest.TestCase):
    def test_existing_second_and_third_turns(self):
        for n in (1,2):
            with self.subTest(n=n):
                f=fixture(n)
                self.assertNotEqual(f["expected_owner_sha"],
                    multiturn_transcript_sha256(f["canonical_rows"],expected_sequence=n,
                                               _prefix_only=n==1))
                bridge=bind_existing_resume(**f)
                new=rows(n+1)
                args=dict(browser_rows=new,canonical_rows=new,witnesses=witnesses(new),
                          browser_calls=8,admitted_calls=8,prompt=new[-2]["content"],
                          stream_answer=new[-1]["content"],terminal_saved=True,dom_matches=True)
                self.assertEqual(bridge.finish(**args),"RESUME_EVIDENCE_MATCHED")
                self.assertEqual(bridge.finish(**args),"HOLD_RESUME_ALREADY_CONSUMED")
    def test_owner_metadata_drift(self):
        f=fixture(1)
        f["owner_rows"][0]["owner_metadata"]="changed"
        with self.assertRaisesRegex(ValueError,"HOLD_B0_RESUME_OWNER_PIN"):
            bind_existing_resume(**f)
    def test_wrong_pin_and_false_claims(self):
        for k,v in (("prefix_rows",True),("production_accepted",True),
                    ("model_post_issued",True),("native_s03_independently_verified",True),
                    ("prefix_sha256","0"*64),("dialog_id_sha256","0"*64)):
            f=fixture(1)
            f["preflight"][k]=v
            with self.subTest(k=k),self.assertRaisesRegex(ValueError,"HOLD_B0_RESUME_PREFLIGHT"):
                bind_existing_resume(**f)
    def test_independent_s03_mismatch(self):
        f=fixture(1)
        f["prior_witnesses"]=witnesses(rows(2))
        with self.assertRaisesRegex(ValueError,"HOLD_RESUME_PREFIX"):
            bind_existing_resume(**f)
    def test_distinct_owner_and_canonical_rows(self):
        f=fixture(1)
        f["canonical_rows"][1]["message_id"]="other"
        f["prior_witnesses"]=witnesses(f["canonical_rows"])
        with self.assertRaisesRegex(ValueError,"HOLD_RESUME_BROWSER_PREFIX"):
            bind_existing_resume(**f)
    def test_counter_mismatch(self):
        f=fixture(1)
        f["admitted_calls"]=6
        with self.assertRaisesRegex(ValueError,"HOLD_RESUME_PREFIX"):
            bind_existing_resume(**f)

    def test_single_authenticated_get_snapshot_bridge(self):
        from unittest.mock import patch
        import owner_chat_probe as probe
        from b0_resume_bridge import prepare_existing_resume_from_owner_get
        for n in (1, 2):
            f = fixture(n)
            kwargs = {k: v for k, v in f.items() if k not in ('preflight', 'owner_rows')}
            kwargs.update(client='fixture-client', row_count=2*n,
                          observed_browser_rows=rows(n), observed_browser_calls=7)
            history = dict(dialog_id=DIALOG, messages=f['owner_rows'])
            with self.subTest(n=n), patch.object(probe, 'require_preturn_owner_binding') as before, \
                    patch.object(probe, 'owner_readback_json', return_value=history) as get, \
                    patch.object(probe, 'require_postturn_owner_binding') as after:
                # Mutating the source object after hashing must not alter the exact snapshot.
                after.side_effect = lambda _: history['messages'][0].update(owner_metadata='late')
                bridge = prepare_existing_resume_from_owner_get(**kwargs)
                before.assert_called_once_with('fixture-client')
                after.assert_called_once_with('fixture-client')
                get.assert_called_once_with('fixture-client', '/api/ui/memory/dialogs/history?dialog_id='+DIALOG+'&limit=8')
                new = rows(n+1)
                self.assertEqual(bridge.finish(browser_rows=[dict(r) for r in new], canonical_rows=new,
                    witnesses=witnesses(new), browser_calls=8, admitted_calls=8,
                    prompt=new[-2]['content'], stream_answer=new[-1]['content'],
                    terminal_saved=True, dom_matches=True), 'RESUME_EVIDENCE_MATCHED')

    def test_single_get_bridge_fails_closed_on_owner_drift(self):
        from unittest.mock import patch
        import owner_chat_probe as probe
        from b0_resume_bridge import prepare_existing_resume_from_owner_get
        f = fixture(1)
        kwargs = {k: v for k, v in f.items() if k not in ('preflight', 'owner_rows')}
        kwargs.update(client='fixture-client', row_count=2,
                      observed_browser_rows=rows(1), observed_browser_calls=7)
        with patch.object(probe, 'require_preturn_owner_binding'), \
                patch.object(probe, 'owner_readback_json', return_value=dict(dialog_id=DIALOG, messages=f['owner_rows'])) as get, \
                patch.object(probe, 'require_postturn_owner_binding', side_effect=RuntimeError('HOLD_OWNER')):
            with self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER'):
                prepare_existing_resume_from_owner_get(**kwargs)
            get.assert_called_once()

    def test_single_get_requires_separate_browser_prefix(self):
        from unittest.mock import patch
        import owner_chat_probe as probe
        from b0_resume_bridge import prepare_existing_resume_from_owner_get
        for n in (1, 2):
            f = fixture(n)
            kwargs = {k: v for k, v in f.items() if k not in ('preflight', 'owner_rows')}
            kwargs.update(client='fixture-client', row_count=2*n)
            wrong = rows(n)
            wrong[-1]['content'] = 'stale browser'
            wrong_id = rows(n)
            wrong_id[-1]['message_id'] = 'wrong-id'
            cases = ((None, 7), (f['canonical_rows'], 7), (rows(n), 6),
                     (rows(n), True), (rows(n), 8), (wrong, 7), (wrong_id, 7))
            for observed, count in cases:
                with self.subTest(n=n, count=count), \
                        patch.object(probe, 'require_preturn_owner_binding'), \
                        patch.object(probe, 'owner_readback_json', return_value=dict(
                            dialog_id=DIALOG, messages=f['owner_rows'])) as get, \
                        patch.object(probe, 'require_postturn_owner_binding'):
                    with self.assertRaisesRegex(ValueError, 'HOLD_(ACTUAL_BROWSER_PREFIX|RESUME_BROWSER_PREFIX)'):
                        prepare_existing_resume_from_owner_get(**kwargs,
                            observed_browser_rows=observed, observed_browser_calls=count)
                    get.assert_called_once()

    def test_single_get_rejects_mutated_dom_and_shallow_canonical_alias(self):
        from unittest.mock import patch
        import owner_chat_probe as probe
        from b0_resume_bridge import prepare_existing_resume_from_owner_get
        for n in (1, 2):
            for mode in ("shallow_alias", "stale_replaced", "changed_after_get"):
                f = fixture(n)
                observed = list(f["canonical_rows"]) if mode == "shallow_alias" else rows(n)
                if mode == "stale_replaced":
                    observed[-1]["content"] = "stale before GET"
                kwargs = {k: v for k, v in f.items() if k not in ("preflight", "owner_rows")}
                kwargs.update(client="fixture-client", row_count=2*n,
                              observed_browser_rows=observed, observed_browser_calls=7)
                def mutate(_):
                    if mode == "stale_replaced":
                        observed[-1]["content"] = f["canonical_rows"][-1]["content"]
                    elif mode == "changed_after_get":
                        observed[-1]["content"] = "changed during GET"
                with self.subTest(n=n, mode=mode), patch.object(probe, "require_preturn_owner_binding"), \
                        patch.object(probe, "owner_readback_json", return_value=dict(
                            dialog_id=DIALOG, messages=f["owner_rows"])) as get, \
                        patch.object(probe, "require_postturn_owner_binding", side_effect=mutate):
                    with self.assertRaisesRegex(ValueError, "HOLD_ACTUAL_BROWSER_PREFIX"):
                        prepare_existing_resume_from_owner_get(**kwargs)
                    get.assert_called_once()

    def test_single_get_terminal_dom_must_be_independent_and_one_shot(self):
        from unittest.mock import patch
        import owner_chat_probe as probe
        from b0_resume_bridge import prepare_existing_resume_from_owner_get
        for n in (1, 2):
            for mode in ("same_list", "shallow_alias", "mixed_alias", "independent"):
                f = fixture(n)
                kwargs = {k: v for k, v in f.items() if k not in ("preflight", "owner_rows")}
                kwargs.update(client="fixture-client", row_count=2*n,
                              observed_browser_rows=rows(n), observed_browser_calls=7)
                with self.subTest(turn=n+1, mode=mode), \
                     patch.object(probe, "require_preturn_owner_binding"), \
                     patch.object(probe, "owner_readback_json", return_value=dict(
                         dialog_id=DIALOG, messages=f["owner_rows"])) as get, \
                     patch.object(probe, "require_postturn_owner_binding"):
                    bridge = prepare_existing_resume_from_owner_get(**kwargs)
                    get.assert_called_once()
                    new = rows(n+1)
                    independent = [dict(r) for r in new]
                    browser = {"same_list": new, "shallow_alias": list(new),
                               "mixed_alias": independent[:-1]+[new[-1]],
                               "independent": independent}[mode]
                    args = dict(browser_rows=browser, canonical_rows=new,
                                witnesses=witnesses(new), browser_calls=8, admitted_calls=8,
                                prompt=new[-2]["content"], stream_answer=new[-1]["content"],
                                terminal_saved=True, dom_matches=True)
                    self.assertEqual(bridge.finish(**args),
                        "RESUME_EVIDENCE_MATCHED" if mode == "independent"
                        else "HOLD_ACTUAL_BROWSER_POSTTURN")
                    args["browser_rows"] = independent
                    self.assertEqual(bridge.finish(**args), "HOLD_RESUME_ALREADY_CONSUMED")
