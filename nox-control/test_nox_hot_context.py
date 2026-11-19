import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location("nox_hot_context",Path(__file__).with_name("nox_hot_context.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def tokens(rows):return sum((len(x["content"])+3)//4+1 for x in rows)

def call(**kwargs):
    default={"persona":"I am NOX with persistent owner-scoped identity.",
             "system":"Respect existing chat and verified memory.",
             "conversation":[{"id":f"m{i}","role":"assistant" if i%2 else "user",
                              "content":("long previous turn "+str(i)+" ")*180} for i in range(9)],
             "verified_s03":[{"id":"S03-M1-1","source_sha256":"a"*64,"text":"Verified owner memory"}],
             "current_user":"Respond to this user question",
             "token_counter":tokens,"token_budget":512,"recent_turns":8}
    default.update(kwargs);return m.plan_prompt(**default)

class HotContextTests(unittest.TestCase):
    def test_retains_persona_current_s03_and_retrieval_refs(self):
        out=call()
        text="\n".join(x["content"] for x in out["messages"])
        self.assertIn("owner-scoped identity",text)
        self.assertIn("Respond to this user question",text)
        self.assertIn("Verified owner memory",text)
        self.assertTrue(out["requires_existing_history_retriever"])
        self.assertEqual(len(out["omitted_turns"]),9)
        self.assertTrue(all(len(x["sha256"])==64 for x in out["omitted_turns"]))
        self.assertLessEqual(out["token_count"],512)
        self.assertFalse(out["native_installed"])

    def test_too_large_protected_context_holds_not_truncates_persona(self):
        with self.assertRaisesRegex(m.ContextHold,"CORE_TOO_LARGE"):
            call(persona="identity"*10000)

    def test_real_tokenizer_required(self):
        with self.assertRaisesRegex(m.ContextHold,"TOKENIZER_REQUIRED"):
            call(token_counter=None)

if __name__=="__main__": unittest.main()
