"""3A03: a host revision callback must never block scoped cache revocation."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading
import unittest

from nox_runpod.teacher_mesh.v38.durable_runtime import WarmS03Cache, Session


SESSION = Session('nox', 'owner', 'chat')


class FinalRevisionTests(unittest.TestCase):
    def row(self):
        return {'id':'memory-1','verified':True,'superseded':False,
                'tenant':'nox','principal':'owner','chat_id':'chat',
                'segment':'M2','content':'verified memory'}

    def test_final_revision_callback_does_not_hold_invalidation_lock(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def revision(session):
            calls.append(session)
            if len(calls) == 2:
                entered.set()
                if not release.wait(3): raise RuntimeError('fixture deadline')
            return 'revision-1'
        cache = WarmS03Cache(lambda *args:[self.row()], revision)
        with ThreadPoolExecutor(max_workers=2) as workers:
            reading = workers.submit(cache, SESSION, 'question', 4)
            self.assertTrue(entered.wait(2))
            invalidating = workers.submit(cache.invalidate, SESSION)
            try:
                try: invalidating.result(timeout=.5)
                except TimeoutError: self.fail('native revision callback blocked owner revocation')
            finally:
                release.set()
            with self.assertRaisesRegex(RuntimeError, 'HOLD_S03_CACHE_INVALIDATED_DURING_READ'):
                reading.result(2)
        self.assertEqual(len(cache.entries), 0)
        self.assertEqual(cache._reads, {})

    def test_unchanged_revision_still_caches_and_returns_copies(self):
        calls=[]
        def recall(*args): calls.append(1);return [self.row()]
        cache=WarmS03Cache(recall,lambda session:'revision-1')
        first=cache(SESSION,'question',4)
        first[0]['content']='caller changed result'
        self.assertEqual(cache(SESSION,'question',4)[0]['content'],'verified memory')
        self.assertEqual(len(calls),1)

    def test_changed_final_revision_does_not_cache_old_rows(self):
        revisions=iter(('before','after','after','after'))
        calls=[]
        def recall(*args): calls.append(1);return [self.row()]
        cache=WarmS03Cache(recall,lambda session:next(revisions))
        cache(SESSION,'question',4)
        self.assertEqual(len(cache.entries),0)
        cache(SESSION,'question',4)
        self.assertEqual(len(calls),2)


if __name__ == '__main__': unittest.main()
