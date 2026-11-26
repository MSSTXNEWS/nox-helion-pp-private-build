#!/bin/bash
N=/workspace/nox/brain/BRAIN
ls $N | head -40
grep -n -E "\"race\"|'race'|RACE_|race_delay|HEDGE|hedge|\"stage\"" $N/*.py | cut -c1-200 | head -30
