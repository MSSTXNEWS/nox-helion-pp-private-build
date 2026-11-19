"""Source-only acceptance for independent post-V125 NOX chat and original S03."""
import ast
import unittest
from nox_runpod.teacher_mesh.v125 import postdeploy_owner_chat_e2e as qa
from nox_runpod.teacher_mesh.v114 import owner_v29_dialog_acceptance as original


class PostDeployQA(unittest.TestCase):
    def test_only_two_existing_sha_constants_change_in_memory(self):
        current=original.REMOTE
        self.assertEqual(current.count(qa.OLD_PX),1)
        self.assertEqual(current.count(qa.OLD_BR),1)
        new=current.replace(qa.OLD_PX,qa.NEW_PX,1).replace(qa.OLD_BR,qa.NEW_BR,1)
        self.assertEqual(len(new),len(current))
        text=new.split("<<'PYREMOTE'\n",1)[1].rsplit('\nPYREMOTE',1)[0]
        compile(text,'<native-v125-chat-e2e>','exec')
        self.assertIn('HOLD_OWNER_COOKIE',text)
        self.assertIn('HOLD_FULL_S03_DIALOG_STREAM_RECEIPT',text)
        self.assertIn('HOLD_OWNER_S03_DIALOG_READBACK',text)
        self.assertNotIn('torch.save(',text)
        self.assertNotIn('supervisorctl',text)
        self.assertNotEqual(new,current)
    def test_frozen_source_remains_original(self):
        self.assertIn(qa.OLD_BR,original.REMOTE)
        self.assertIn(qa.OLD_PX,original.REMOTE)
        self.assertNotIn(qa.NEW_BR,original.REMOTE)


if __name__=='__main__':
    unittest.main()
