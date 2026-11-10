"""NOX PRIME episodic recall tests with no external I/O or S03 writes."""
from tempfile import TemporaryDirectory
from pathlib import Path
import json
import unittest
import nox_prime_cognitive_memory_v1 as m

def add(root,role,content,persona=None,time="2026-11-07T10:00:00Z"):
    p=Path(root)/"brain"/"history"/"unified_chat_v1.jsonl"
    p.parent.mkdir(parents=True,exist_ok=True)
    obj={"role":role,"content":content,"time":time}
    if persona is not None:obj["persona_id"]=persona
    with p.open("a",encoding="utf-8") as f:f.write(json.dumps(obj,ensure_ascii=False)+"\n")

class RecallTests(unittest.TestCase):
    def test_recall_real_previous_event(self):
        with TemporaryDirectory() as root:
            add(root,"user","Почему остановилось обучение на видеокарте?")
            add(root,"assistant","Датчик Hot Spot пропал, контроллер сохранил checkpoint.")
            x=m.recall(root,"Почему обучение остановилось из-за датчика?")
        self.assertGreater(len(x),0)
        self.assertEqual(x[0]["source"],"NOX_LOCAL_TRANSCRIPT")
        self.assertFalse(x[0]["verified"])
        self.assertIn("Hot Spot",x[0]["assistant"])

    def test_no_persona_cross_leakage(self):
        with TemporaryDirectory() as root:
            add(root,"user","Секретный проект Альфа",persona="KV")
            add(root,"assistant","Очень секретные данные",persona="KV")
            self.assertEqual(m.recall(root,"Секретный проект Альфа"),[])

    def test_old_prime_scope_and_no_mutation(self):
        with TemporaryDirectory() as root:
            add(root,"user","Программа начинается с памяти.")
            add(root,"assistant","Сначала проверяем память.")
            path=m._path(root)
            before=path.read_bytes()
            self.assertTrue(m.recall(root,"Программа памяти"))
            self.assertEqual(before,path.read_bytes())

    def test_greeting_does_not_load_memory(self):
        with TemporaryDirectory() as root:
            add(root,"user","Привет мой проект нокс")
            add(root,"assistant","На связи")
            self.assertEqual(m.memory_context(root,"Привет"),[])

    def test_malformed_record_is_ignored(self):
        with TemporaryDirectory() as root:
            p=m._path(root)
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text('not json\n{"role":"evil","content":"test"}\n',encoding="utf-8")
            self.assertEqual(m.recall(root,"test"),[])

    def test_scope_does_not_read_another_store(self):
        with TemporaryDirectory() as root:
            p=Path(root)/"soul_gpu"/"soul.sqlite3"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"original")
            self.assertEqual(m.memory_context(root,"что с памятью нокс"),[])
            self.assertEqual(p.read_bytes(),b"original")

if __name__=="__main__":unittest.main()
