def _live_slot_ctx(default=2816) -> int:
    try:
        p = Path("/root/nox/state/chat_launch.json")
        if p.exists():
            default = int((json.loads(p.read_text()).get("ctx_per_slot") or default))
    except Exception:
        pass
    try:
        _b = load_backend()  # t141u: real backend (8098), not the retired 8081
        r = httpx.get(f"http://{_b['host']}:{_b['port']}/slots", timeout=1.0)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data and data[0].get("n_ctx"):
                return int(data[0]["n_ctx"])
    except Exception:
        pass
    return int(default or 2816)


def _count_msg_tokens(msgs) -> int:
    """Tokenize via 8098 apply-template; does not occupy a generation slot."""
    try:
        _b = load_backend()
        r = httpx.post(
            f"http://{_b['host']}:{_b['port']}/apply-template",
            json={"messages": msgs},
            timeout=2.0,
        )
        if r.status_code != 200:
            raise RuntimeError("apply-template")
        prompt = (r.json() or {}).get("prompt") or ""
        r2 = httpx.post(
            f"http://{_b['host']}:{_b['port']}/tokenize",
            json={"content": prompt},
            timeout=2.0,
        )
        if r2.status_code != 200:
            raise RuntimeError("tokenize")
        toks = (r2.json() or {}).get("tokens") or []
        return len(toks)
    except Exception:
        chars = sum(len(str(m.get("content") or "")) for m in (msgs or []))
        return max(1, chars // 2)


def _shrink_last_user(content: str, max_chars: int) -> str:
    content = str(content or "")
    if max_chars < 1:
        return content[:1]
    if len(content) <= max_chars:
        return content
    sep = "\n\n---\n"
    if sep in content:
        q, _, rest = content.partition(sep)
        q = (q or "").strip() or content[:80]
        room = max_chars - len(q) - len(sep) - 24
        if room < 0:
            return q[:max_chars]
        return q + sep + rest[:room] + "\n[...trimmed to fit slot...]"
    return content[: max(0, max_chars - 24)] + "\n[...trimmed to fit slot...]"


def _trim_ctx(msgs, budget=None):
    """Fit system+turns into the live slot, leaving room for tools + generation.

    t171u: the last user turn (S03/textbook/memory inject) was never truncated,
    so "кто ты" + owner TOOLS reached 5076 tokens in a 4096-token slot and
    8098 aborted. Also reserve ~1300 tok for TOOLS (measured ~1067).
    """
    try:
        n_ctx = int(_live_slot_ctx())
        gen_reserve = 512
        tools_reserve = 1300
        token_budget = max(1024, n_ctx - gen_reserve - tools_reserve)
        if budget is None:
            budget = token_budget * 2  # conservative chars/token; was *3 and last turn skipped
        sys_m = [dict(m) for m in msgs if m.get("role") == "system"]
        rest = [dict(m) for m in msgs if m.get("role") != "system"]

        def _chars(ms):
            return sum(len(str(m.get("content") or "")) for m in ms)

        # Drop oldest history first; always keep the latest user turn, then shrink it.
        used = _chars(sys_m)
        keep = []
        for m in reversed(rest):
            c = str(m.get("content") or "")
            if keep and used + len(c) > budget:
                break
            keep.append(m)
            used += len(c)
        keep.reverse()
        while keep and keep[0].get("role") == "assistant":
            keep.pop(0)

        # Shrink last user inject (keep the question before ---) to the char budget.
        if keep and _chars(sys_m + keep) > budget:
            others = _chars(sys_m + keep[:-1])
            cap = max(80, budget - others)
            if keep[-1].get("role") == "user":
                keep[-1]["content"] = _shrink_last_user(str(keep[-1].get("content") or ""), cap)

        # If system is still too large, drop only the variable tail after the contract
        # so the cached prefix stays intact.
        if sys_m and _chars(sys_m + keep) > budget:
            content = str(sys_m[0].get("content") or "")
            mark = "NOX VERIFIED SELF-MODEL CONTRACT:"
            idx = content.find(mark)
            if idx >= 0:
                end = content.find("\n\n", idx + len(mark))
                if end < 0:
                    end = min(len(content), idx + 1800)
                prefix = content[:end]
                room = budget - _chars(keep) - 24
                if room > 0 and len(prefix) > room:
                    prefix = prefix[:room] + "\n[...trimmed to fit slot...]"
                sys_m[0]["content"] = prefix
            else:
                max_sys = max(400, budget - _chars(keep) - 24)
                if len(content) > max_sys:
                    sys_m[0]["content"] = content[:max_sys] + "\n[...trimmed to fit slot...]"

        out = sys_m + keep
        # Tighten with real token counts when 8098 tokenize is available.
        try:
            ntok = _count_msg_tokens(out)
            for _ in range(6):
                if ntok <= token_budget:
                    break
                # Prefer shrinking the last user inject, then history, then system tail.
                if out and out[-1].get("role") == "user":
                    cur = str(out[-1].get("content") or "")
                    if len(cur) > 80:
                        out[-1]["content"] = _shrink_last_user(cur, max(80, int(len(cur) * 0.65)))
                        ntok = _count_msg_tokens(out)
                        continue
                if len(out) > 2:
                    # drop oldest non-system turn
                    out = [out[0]] + out[2:] if out[0].get("role") == "system" else out[1:]
                    while len(out) > 1 and out[1].get("role") == "assistant" and out[0].get("role") == "system":
                        out = [out[0]] + out[2:]
                    ntok = _count_msg_tokens(out)
                    continue
                break
        except Exception:
            pass
        return out
    except Exception:
        return msgs

