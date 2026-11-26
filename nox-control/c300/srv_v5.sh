#!/bin/bash
F=/workspace/nox/judges/judge_service.py
grep -n -E "def judge|/judge|\"only\"|'only'|subset|fast|priority|X-NOX|body.get|req\.|class .*BaseModel|:\s*(str|int|float|list|bool)" $F | cut -c1-190 | head -40
