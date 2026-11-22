import glob, json, os, unittest
import gbnf_check as g

D = os.path.dirname(os.path.abspath(__file__))


class T(unittest.TestCase):
    def test_all_shipped_grammars_load(self):
        files = glob.glob(D + "/grammars/*.gbnf")
        self.assertGreaterEqual(len(files), 5)
        for f in files: g.load(f)

    def test_action(self):
        G = g.load(D + "/grammars/action.gbnf")
        ok = '{"action":"search_memory","args":{"q":"RAID","k":5,"deep":true,"x":[1,2,{"a":null}]},"reason":"нужна память"}'
        self.assertTrue(G.matches(ok))
        self.assertTrue(G.matches('{ "action" : "none" , "args" : { } , "reason" : "" }'))
        for bad in ['{"action":"rm_rf","args":{},"reason":"x"}', '{"action":"say","args":{}}',
                    '{"action":"say","args":[],"reason":"x"}', 'текст до {"action":"say","args":{},"reason":"x"}',
                    '{"action":"say","args":{},"reason":"x"} хвост', '{"action":"say","args":{"a":},"reason":"x"}']:
            self.assertFalse(G.matches(bad), bad)

    def test_json_object(self):
        G = g.load(D + "/grammars/json_object.gbnf")
        for s in ['{}', '{"a":1}', '{"a":-1.5e3,"b":[true,false,null],"c":{"d":"\\u00e9 \\n"}}']:
            self.assertTrue(G.matches(s), s)
        for s in ['[]', '{"a":01}', "{'a':1}", '{"a":1,}', '{"a" 1}', '']:
            self.assertFalse(G.matches(s), s)

    def test_route_verdict_yesno(self):
        R = g.load(D + "/grammars/route_mode.gbnf")
        self.assertTrue(R.matches("глубоко 7")); self.assertFalse(R.matches("глубоко")); self.assertFalse(R.matches("медленно 3"))
        V = g.load(D + "/grammars/verdict.gbnf")
        self.assertTrue(V.matches("TIE 0")); self.assertTrue(V.matches("A 9")); self.assertFalse(V.matches("C 1"))
        Y = g.load(D + "/grammars/yesno.gbnf")
        self.assertTrue(Y.matches("неясно")); self.assertFalse(Y.matches("может быть"))

    def test_dynamic_action_registry(self):
        G = g.Grammar(g.action_grammar(["alpha", "beta"]))
        self.assertTrue(G.matches('{"action":"beta","args":{},"reason":"ok"}'))
        self.assertFalse(G.matches('{"action":"search_memory","args":{},"reason":"ok"}'))

    def test_fact_citation_gate(self):
        G = g.Grammar(g.fact_citation_grammar(["f101", "f202"]))
        self.assertTrue(G.matches("Ты любишь горы [S03:f101] и чай [S03:f202]."))
        self.assertTrue(G.matches("Без ссылок вообще"))
        self.assertFalse(G.matches("Выдуманное воспоминание [S03:f999]"))
        self.assertFalse(G.matches("Незакрытая ссылка [S03:f101"))
        with self.assertRaises(g.GrammarError): g.fact_citation_grammar([])
        with self.assertRaises(g.GrammarError): g.fact_citation_grammar(['a"b'])

    def test_checker_catches_broken_grammars(self):
        for bad in ['root ::= foo', 'a ::= "x"', 'root ::= root "x" | "y"', 'root ::= ( "x"', 'root ::= "x" \nroot ::= "y"']:
            with self.assertRaises(g.GrammarError, msg=bad): g.Grammar(bad)

    def test_repetition_bounds(self):
        G = g.Grammar('root ::= [a-c]{2,3} "!"')
        self.assertTrue(G.matches("ab!")); self.assertTrue(G.matches("abc!"))
        self.assertFalse(G.matches("a!")); self.assertFalse(G.matches("abcd!"))


if __name__ == "__main__":
    unittest.main()
