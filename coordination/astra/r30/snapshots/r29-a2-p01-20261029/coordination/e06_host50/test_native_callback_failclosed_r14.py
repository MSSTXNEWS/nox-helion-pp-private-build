"""E06 R14: native callback exceptions must fail closed before any dispatch."""
import secrets
import unittest
from admission import (APPROVED_ROUTE_POLICY, BASE_COMMIT, BASE_TREE,
                       Capability, Hold, Host50Admission, NativeFileSelection)

class NativeCallbackErrors(unittest.TestCase):
    def setUp(self):
        bound={'system.pc_control', 'chat.voice', 'chat.attach'}
        actions=[dict(taskId=f'NIP01-{i:02}',routeId=r,owner=o,risk=risk,settings=[])
                 for i,(r,o,risk) in enumerate(APPROVED_ROUTE_POLICY,1)]
        bindings=[dict(taskId=a['taskId'],routeId=a['routeId'],owner=a['owner'],
                       sourceBinding='host:'+a['routeId'] if a['routeId'] in bound else None)
                  for a in actions]
        caps={a['routeId']:Capability(a['routeId'],a['owner'],'host:'+a['routeId'],
              'a'*64,BASE_TREE,True,True) for a in actions if a['routeId'] in bound}
        self.host=Host50Admission({'version':'NOX-INTEGRATION-PACK-01','actions':actions},
              {'sourceBaseCommit':BASE_COMMIT,'routes':bindings},
              signing_key=secrets.token_bytes(32),allowed_origins={'https://nox.invalid'},
              active_tree=BASE_TREE,capabilities=caps)
        self.session=self.host.issue_session(tenant='t',principal='p',chat='c',
              origin='https://nox.invalid',scopes=tuple(sorted(bound)),
              sensitive=tuple(sorted(bound)))
        self.tasks={a['routeId']:a['taskId'] for a in actions}

    def request(self,route):
        return dict(intent='nox.feature.request',routeId=route,
                    taskId=self.tasks[route],settings={})

    @staticmethod
    def failed_native(*_):
        raise RuntimeError('private native callback diagnostic')

    def test_three_native_callback_errors_become_hold_without_pending(self):
        cases=[('system.pc_control','native_consent','NATIVE_CONSENT_CALLBACK_FAILED'),
               ('chat.voice','native_device_permission','NATIVE_DEVICE_PERMISSION_CALLBACK_FAILED'),
               ('chat.attach','native_file_picker','NATIVE_FILE_PICKER_CALLBACK_FAILED')]
        for route,callback,code in cases:
            with self.subTest(route=route),self.assertRaisesRegex(Hold,code):
                self.host.admit(session=self.session,actual_origin=self.session.origin,
                                request=self.request(route),**{callback:self.failed_native})
            self.assertFalse(self.host.pending)
            self.assertFalse(self.host.pending_deadlines)

    def test_valid_picker_only_admits_not_executes(self):
        selected=NativeFileSelection(ticket='native-opaque-ticket-12345',sha256='b'*64,
                                     size_bytes=12,tenant='t',principal='p',chat='c')
        out=self.host.admit(session=self.session,actual_origin=self.session.origin,
                            request=self.request('chat.attach'),
                            native_file_picker=lambda *_: selected)
        self.assertEqual(out['state'],'ADMITTED_NOT_EXECUTED')
        self.assertEqual(out['nativeAck'],'PENDING')

if __name__=='__main__':
    unittest.main()
