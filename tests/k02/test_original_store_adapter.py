import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from helion.storage import Store
from helion.personas import PERSONAS
from nox_selfbuilder.onehost_store import OneHostStoreActor, StoreActorHold
from nox_selfbuilder.original_store_adapter import OriginalStoreChatAdapter

REPO=Path(__file__).resolve().parents[2]
SEED=REPO/'assets/NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip'
if not SEED.is_file():
    SEED=REPO.parent/'donors/r4/assets'/SEED.name

class OriginalStoreIntegration(unittest.TestCase):
    def test_restart_persona_isolation_and_seed_model_change(self):
        before=hashlib.sha256(SEED.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/'helion.sqlite3'
            with Store(db) as original:
                tid=original.add_task('existing approved work')
                original.set_status(tid,'ACCEPTED')
                original.approve_example(tid,'Existing evidence','owner-original',owner_confirmed=True)
                version=original.conn.execute('PRAGMA user_version').fetchone()[0]
            with OneHostStoreActor(lambda: Store(db)) as actor:
                chat=OriginalStoreChatAdapter(actor,seed_archive=SEED)
                for index,p in enumerate(PERSONAS):
                    scope=chat.resolve_chat_id('core.core',p.persona_id)
                    with chat.model_context('qwen2.5-coder:7b'):
                        self.assertEqual(chat.history('local','alice',scope),[])
                        chat.add_exchange('local','alice',scope,f'prompt {index}',f'answer {index}',authorize=lambda:None)
                chat.assert_model_switch_safe()
                self.assertEqual(actor.call(lambda s:s.conn.execute('PRAGMA user_version').fetchone()[0]),version)
                self.assertEqual(actor.call(lambda s:s.recall('Existing'))[0]['source'],'owner-original')
            with OneHostStoreActor(lambda: Store(db)) as actor:
                chat=OriginalStoreChatAdapter(actor,seed_archive=SEED)
                for index,p in enumerate(PERSONAS):
                    scope=chat.resolve_chat_id('core.core',p.persona_id)
                    self.assertEqual(chat.history('local','alice',scope)[-1]['content'],f'answer {index}')
                    self.assertEqual(chat.history('local','bob',scope),[])
                    self.assertEqual(chat.history('local','alice',chat.resolve_chat_id('core.atlas',p.persona_id)),[])
                with chat.model_context('other-installed-model:latest'):
                    self.assertEqual(len(chat.history('local','alice',chat.resolve_chat_id('core.core',PERSONAS[0].persona_id))),2)
                self.assertEqual(actor.call(lambda s:s.conn.execute('SELECT COUNT(*) FROM core_chat_turns').fetchone()[0]),5)
        self.assertEqual(hashlib.sha256(SEED.read_bytes()).hexdigest(),before)

    def test_revoke_before_commit_rolls_back_both_messages(self):
        with tempfile.TemporaryDirectory() as d:
            with OneHostStoreActor(lambda:Store(Path(d)/'helion.sqlite3')) as actor:
                chat=OriginalStoreChatAdapter(actor)
                with chat.model_context('model:latest'):
                    chat.history('local','owner','default')
                    calls=[]
                    def authorize():
                        calls.append(1)
                        if len(calls)==3:raise PermissionError('STOP')
                    with self.assertRaises(PermissionError):
                        chat.add_exchange('local','owner','default','prompt','answer',authorize=authorize)
                self.assertEqual(chat.history('local','owner','default'),[])
                with self.assertRaises(StoreActorHold):chat.assert_model_switch_safe()
                with self.assertRaises(PermissionError):chat.history('local','owner','arbitrary')

    def test_revoked_history_epoch_cannot_commit_late_reply(self):
        with tempfile.TemporaryDirectory() as d:
            with OneHostStoreActor(lambda:Store(Path(d)/'helion.sqlite3')) as actor:
                chat=OriginalStoreChatAdapter(actor)
                with chat.model_context('model:latest'):
                    chat.history('local','owner','default')
                    scope=chat._scope('local','owner','default')
                    def revoke(s):
                        with s.conn:
                            s.conn.execute('INSERT INTO core_history_epochs(project_id,core_id,chat_id,epoch) VALUES(?,?,?,1)',scope)
                    actor.call(revoke)
                    with self.assertRaisesRegex(PermissionError,'REVOKED'):
                        chat.add_exchange('local','owner','default','prompt','answer',authorize=lambda:None)
                self.assertEqual(chat.history('local','owner','default'),[])

if __name__=='__main__':unittest.main()
