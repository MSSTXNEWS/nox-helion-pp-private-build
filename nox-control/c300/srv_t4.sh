#!/bin/bash
C=/workspace/nox/distill_v2/code/distill_v2.py
grep -n "ckpt_every\|ckpt-every" $C | cut -c1-210 | head -14
grep -n "holdout\b.*every\|hold_every\|eval_every" $C | head -5 | cut -c1-200
