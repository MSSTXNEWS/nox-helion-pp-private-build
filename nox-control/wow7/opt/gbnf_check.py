#!/usr/bin/env python3
"""OPT-19/20 gbnf_check.py - мини-интерпретатор подмножества GBNF llama.cpp: разбор, проверка
(root, неопределённые правила, левая рекурсия) и сопоставление строки; генератор грамматики с
перечислением id фактов (OPT-20 citation gate). stdlib. Подмножество: "строки" с \\n \\t \\\\ \\" \\xNN \\uNNNN,
[классы] и [^классы] с диапазонами, ( ), |, * + ?, {m} {m,n} {m,}, ссылки на правила, комментарии #."""
import re, sys

ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "]": "]", "[": "[", "-": "-", "^": "^", "/": "/",
       "b": "\b", "f": "\f"}


class GrammarError(Exception):
    pass


class _P:
    def __init__(self, s): self.s, self.i = s, 0
    def ws(self):
        while self.i < len(self.s) and (self.s[self.i] in " \t\r\n"):
            self.i += 1
    def peek(self): return self.s[self.i] if self.i < len(self.s) else ""
    def esc(self):
        c = self.s[self.i]; self.i += 1
        if c == "x":
            v = int(self.s[self.i:self.i + 2], 16); self.i += 2; return chr(v)
        if c == "u":
            v = int(self.s[self.i:self.i + 4], 16); self.i += 4; return chr(v)
        if c in ESC: return ESC[c]
        raise GrammarError(f"bad escape \\{c}")
    def lit(self):
        self.i += 1; out = []
        while self.peek() != '"':
            if not self.peek(): raise GrammarError("unterminated string")
            c = self.s[self.i]; self.i += 1
            out.append(self.esc() if c == "\\" else c)
        self.i += 1
        return ("lit", "".join(out))
    def cls(self):
        self.i += 1; neg = False
        if self.peek() == "^": neg = True; self.i += 1
        items = []
        def one():
            c = self.s[self.i]; self.i += 1
            return self.esc() if c == "\\" else c
        while self.peek() != "]":
            if not self.peek(): raise GrammarError("unterminated class")
            lo = one()
            if self.peek() == "-" and self.s[self.i + 1:self.i + 2] not in ("]", ""):
                self.i += 1; hi = one(); items.append((lo, hi))
            else:
                items.append((lo, lo))
        self.i += 1
        return ("cls", neg, items)
    def atom(self):
        c = self.peek()
        if c == '"': return self.lit()
        if c == "[": return self.cls()
        if c == "(":
            self.i += 1; a = self.alt(); self.ws()
            if self.peek() != ")": raise GrammarError("expected )")
            self.i += 1; return a
        m = re.compile(r"[A-Za-z][A-Za-z0-9-]*").match(self.s, self.i)
        if not m: raise GrammarError(f"unexpected {c!r} at {self.i}")
        self.i = m.end(); return ("ref", m.group())
    def item(self):
        a = self.atom()
        while True:
            c = self.peek()
            if c in ("*", "+", "?"):
                self.i += 1; a = ("rep", a, {"*": 0, "+": 1, "?": 0}[c], {"*": None, "+": None, "?": 1}[c])
            elif c == "{":
                m = re.compile(r"\{(\d+)(,(\d*))?\}").match(self.s, self.i)
                if not m: raise GrammarError("bad {m,n}")
                lo = int(m.group(1)); hi = (None if m.group(3) == "" else int(m.group(3))) if m.group(2) else lo
                self.i = m.end(); a = ("rep", a, lo, hi)
            else:
                return a
    def seq(self):
        items = []
        while True:
            self.ws()
            if self.peek() in ("", "|", ")"): return ("seq", items)
            items.append(self.item())
    def alt(self):
        alts = [self.seq()]
        while True:
            self.ws()
            if self.peek() == "|": self.i += 1; alts.append(self.seq())
            else: return ("alt", alts)


class Grammar:
    def __init__(self, text):
        text = re.sub(r"#[^\n]*", "", text)
        parts = re.split(r"(?m)^\s*([A-Za-z][A-Za-z0-9-]*)\s*::=", text)
        self.rules = {}
        for k in range(1, len(parts), 2):
            name, body = parts[k], parts[k + 1]
            p = _P(body); node = p.alt(); p.ws()
            if p.i != len(body): raise GrammarError(f"rule {name}: junk at {p.i}")
            if name in self.rules: raise GrammarError(f"duplicate rule {name}")
            self.rules[name] = node
        self.check()

    def check(self):
        if "root" not in self.rules: raise GrammarError("no root rule")
        def refs(n, out):
            if n[0] == "ref": out.add(n[1])
            elif n[0] in ("alt", "seq"):
                for x in n[1]: refs(x, out)
            elif n[0] == "rep": refs(n[1], out)
            return out
        for name, n in self.rules.items():
            for r in refs(n, set()):
                if r not in self.rules: raise GrammarError(f"undefined rule {r} in {name}")
        for name in self.rules:  # левая рекурсия
            if self._left(name, name, set()): raise GrammarError(f"left recursion in {name}")

    def _first_refs(self, n):
        k = n[0]
        if k == "ref": return {n[1]}
        if k == "alt": return set().union(*[self._first_refs(x) for x in n[1]]) if n[1] else set()
        if k == "seq": return self._first_refs(n[1][0]) if n[1] else set()
        if k == "rep": return self._first_refs(n[1])
        return set()

    def _left(self, start, cur, seen):
        for r in self._first_refs(self.rules[cur]):
            if r == start: return True
            if r not in seen:
                seen.add(r)
                if self._left(start, r, seen): return True
        return False

    def _m(self, n, s, i, memo):
        key = (id(n), i)
        if key in memo: return memo[key]
        k, out = n[0], set()
        if k == "lit":
            if s.startswith(n[1], i): out.add(i + len(n[1]))
        elif k == "cls":
            if i < len(s):
                inn = any(lo <= s[i] <= hi for lo, hi in n[2])
                if inn != n[1]: out.add(i + 1)
        elif k == "ref":
            out = self._m(self.rules[n[1]], s, i, memo)
        elif k == "alt":
            for a in n[1]: out |= self._m(a, s, i, memo)
        elif k == "seq":
            cur = {i}
            for it in n[1]:
                nxt = set()
                for p in cur: nxt |= self._m(it, s, p, memo)
                cur = nxt
                if not cur: break
            out = cur
        elif k == "rep":
            lo, hi = n[2], n[3]
            cur, count, acc = {i}, 0, set()
            if lo == 0: acc |= cur
            while cur and (hi is None or count < hi):
                nxt = set()
                for p in cur: nxt |= {e for e in self._m(n[1], s, p, memo) if e != p or lo > count}
                count += 1; cur = nxt
                if count >= lo: acc |= cur
                if count > len(s) + lo + 1: break
            out = acc
        memo[key] = out
        return out

    def matches(self, text, rule="root"):
        return len(text) in self._m(self.rules[rule], text, 0, {})


def load(path):
    with open(path, encoding="utf-8") as f: return Grammar(f.read())


def _q(s): return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fact_citation_grammar(ids, max_len=1500):
    """OPT-20: ответ = текст со ссылками вида [S03:<id>], где id ТОЛЬКО из выданных ретривером.
    Невозможно сослаться на несуществующую память. ids - непустой список строк [A-Za-z0-9_-]."""
    ids = list(dict.fromkeys(ids))
    if not ids or any(not re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids):
        raise GrammarError("ids must be non-empty [A-Za-z0-9_-]+")
    alts = " | ".join(_q(i) for i in ids)
    return ("root ::= ( plain | cite )+\n"
            f"plain ::= [^\\[]{{1,{max_len}}}\n"
            'cite ::= "[S03:" id "]"\n'
            f"id ::= {alts}\n")


def action_grammar(actions):
    """OPT-19: action.gbnf с перечнем инструментов из реестра."""
    with open(__file__.rsplit("/", 1)[0] + "/grammars/action.gbnf", encoding="utf-8") as f:
        base = f.read()
    alts = " | ".join(_q('"' + a + '"') for a in actions)
    return re.sub(r"(?m)^action ::=.*$", lambda m: f"action ::= {alts}", base)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        load(p); print("OK", p)
