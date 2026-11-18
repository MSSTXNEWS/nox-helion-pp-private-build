"""One targeted fresh-scope/actual-anchor test, entirely offline."""
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import model_reference_changed_path_qa as qa
from p0_witness_protocol import Hold, read_v24

HERE = Path(__file__).resolve().parent


class DistinctWordingScopeTest(unittest.TestCase):
    def test_actual_prior_pair_four_to_six_and_fresh_journal_current_generation(self):
        actual_path = HERE.parent/'acceleration_20261118/MODEL_REFERENCE_CONTINUATION_RESULT_44207277921.raw.json'
        actual_raw = actual_path.read_bytes()
        self.assertEqual(hashlib.sha256(actual_raw).hexdigest(), '92908c7255e8d6ffa60b4e9736f575e900537d3876d92850b26f513af063b8a1')
        actual = json.loads(actual_raw)['data']; previous_q='Какая модель в твоей основе сейчас?'
        previous_a=actual['own_synthetic_answer']['text']
        self.assertEqual(qa.PREVIOUS_EXCHANGE,actual['history_and_s03']['new_exchange_id'])
        self.assertEqual(qa.PREVIOUS_RECORD_SHA,actual['history_and_s03']['new_record_sha256'])
        self.assertEqual(qa.PREVIOUS_QUESTION_SHA,qa.digest(previous_q.encode()))
        self.assertEqual(qa.PREVIOUS_ANSWER_SHA,qa.digest(previous_a.encode()))
        self.assertNotEqual(qa.QUESTION,previous_q)
        self.assertEqual(qa.RELEASE['runtime_identity']['pid'],3703386)
        self.assertEqual(qa.RELEASE['runtime_identity']['start_ticks'],175609570)
        wrong={'process':dict(qa.RELEASE['runtime_identity'],pid=3648425,start_ticks=175058217)}
        with patch.object(qa.native,'stable_read',side_effect=AssertionError('must reject old process before IO')):
            with self.assertRaisesRegex(Hold,'HOLD_ACTUAL_PROXY_GENERATION'):qa.installed_release(wrong)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state';state.mkdir(mode=0o700)
            old_journal=state/'owner_model_reference_acceptance_20261118';old_journal.mkdir(mode=0o700)
            old_child=old_journal/'continuation_6964382138';old_child.mkdir(mode=0o700)
            marker=old_child/'outcome.json';marker.write_bytes(b'{"completed":true,"fixture":"do not touch"}\n');marker.chmod(0o600)
            untouched=(marker.read_bytes(),marker.stat().st_ino)
            db_path=root/'knowledge.sqlite'
            old_q,old_a='Synthetic private first question','Synthetic first answer'
            first_frame=qa.native.full_turn_episode(old_q,old_a)
            first_sha=qa.digest(('M1|'+first_frame).encode())
            previous_frame=qa.native.full_turn_episode(previous_q,previous_a)
            self.assertEqual(qa.digest(('M1|'+previous_frame).encode()),qa.PREVIOUS_RECORD_SHA)
            rows=[(10,qa.DIALOG,qa.OLD_EXCHANGE,'user',old_q,'old'),
                  (11,qa.DIALOG,qa.OLD_EXCHANGE,'assistant',old_a,'old'),
                  (12,qa.DIALOG,qa.PREVIOUS_EXCHANGE,'user',previous_q,'previous'),
                  (13,qa.DIALOG,qa.PREVIOUS_EXCHANGE,'assistant',previous_a,'previous')]
            with sqlite3.connect(db_path) as db:
                db.executescript('''CREATE TABLE nox_v29_dialogs(dialog_id TEXT,owner TEXT,title TEXT,
                    archived INTEGER,revision INTEGER,created_at TEXT,updated_at TEXT);
                    CREATE TABLE nox_v29_dialog_messages(row_id INTEGER PRIMARY KEY,dialog_id TEXT,
                    exchange_id TEXT,role TEXT,content TEXT,ts TEXT);
                    CREATE TABLE s03_items(id TEXT,segment TEXT,provenance TEXT,sha256 TEXT,text TEXT);''')
                db.execute('INSERT INTO nox_v29_dialogs VALUES(?,?,?,?,?,?,?)',
                           (qa.DIALOG,'nox-single-owner','Synthetic QA',0,3,'old','old'))
                db.executemany('INSERT INTO nox_v29_dialog_messages VALUES(?,?,?,?,?,?)',rows)
                db.executemany('INSERT INTO s03_items VALUES(?,?,?,?,?)',
                    [(qa.OLD_EXCHANGE,'M1','chat_turn',first_sha,first_frame),
                     (qa.PREVIOUS_EXCHANGE,'M1','chat_turn',qa.PREVIOUS_RECORD_SHA,previous_frame)])
            binding={'dev':db_path.stat().st_dev,'ino':db_path.stat().st_ino}
            with patch.object(qa.native,'STATE',state), patch.object(qa,'DB',db_path), patch.object(qa,'OLD_RECORD_SHA',first_sha):
                before=qa.own_database_snapshot(binding)
                prefix=qa.digest(qa.canonical(before['rows'][:2]))
                with patch.object(qa,'PRIOR_PREFIX_SHA',prefix):
                    checked=qa.verify_old_prefix(before,binding)
                    self.assertEqual(checked['messages'],4)
                    tampered=copy.deepcopy(before);bad=list(tampered['rows'][3]);bad[2]+='changed';tampered['rows'][3]=tuple(bad)
                    with self.assertRaisesRegex(Hold,'HOLD_PREVIOUS_QA_CONTENT_CHANGED'):
                        qa.verify_old_prefix(tampered,binding)
                answer='Сейчас мой движок запущен с '+qa.MODEL_REFERENCE+'.'
                exchange='S03-distinct-wording-fixture'
                frame=qa.native.full_turn_episode(qa.QUESTION,answer)
                record_sha=qa.digest(('M1|'+frame).encode())
                journal=qa.Journal('9003','e'*40,'b'*32)
                self.assertNotEqual(journal.path,old_journal)
                fixture=self
                class Response(io.BytesIO):
                    status=200
                    headers={'Content-Type':'text/event-stream'}
                class Opener:
                    calls=0
                    def open(self,request,**kwargs):
                        self.calls+=1
                        value=json.loads(request.data)
                        fixture.assertEqual(value['message'],qa.QUESTION)
                        fixture.assertEqual(value['request_id'],'model-wording-'+'b'*32)
                        fixture.assertTrue((journal.path/'model_post_intent.json').is_file())
                        with sqlite3.connect(db_path) as db:
                            db.executemany('INSERT INTO nox_v29_dialog_messages VALUES(?,?,?,?,?,?)',
                                [(14,qa.DIALOG,exchange,'user',qa.QUESTION,'new'),
                                 (15,qa.DIALOG,exchange,'assistant',answer,'new')])
                            db.execute('UPDATE nox_v29_dialogs SET revision=4')
                            db.execute('INSERT INTO s03_items VALUES(?,?,?,?,?)',(exchange,'M1','chat_turn',record_sha,frame))
                        frames=[{'type':'context'},{'type':'meta','dialog_id':qa.DIALOG},{'type':'token','t':answer},
                            {'type':'done','status':'done','saved':True,'s03_integrated':True,'exchange_id':exchange,
                             's03_readback':'FULL_QUESTION_AND_ANSWER_SUBSTRINGS',
                             's03_proof':'M1_LENGTH_FRAMED_V2_SHA256','s03_record_sha256':record_sha}]
                        return Response(b''.join(b'data: '+qa.canonical(f)+b'\n\n' for f in frames))
                client=qa.Client();client.opener=Opener()
                with journal:
                    with journal.send(client) as response:turn=read_v24(response,qa.DIALOG,time.monotonic())
                    after=qa.own_database_snapshot(binding)
                    proof=qa.verify_appended_pair(before,after,turn,binding)
                    self.assertEqual(proof['total_own_messages'],6)
                    self.assertTrue(proof['prior_history_preserved'])
                    self.assertEqual(proof['prior_prefix_sha256'],checked['prefix_sha256'])
                    with self.assertRaisesRegex(Hold,'HOLD_QA_POST_REPLAY'):journal.send(client)
                self.assertEqual(client.opener.calls,1)
                self.assertEqual(client.counts['model_post'],1)
                self.assertEqual((marker.read_bytes(),marker.stat().st_ino),untouched)
                again=qa.Journal('9004','f'*40,'c'*32)
                with self.assertRaisesRegex(Hold,'HOLD_QA_ALREADY_RESERVED_NO_RETRY'):again.__enter__()


if __name__=='__main__':
    unittest.main()
