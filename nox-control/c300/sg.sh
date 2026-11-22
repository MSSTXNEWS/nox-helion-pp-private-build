#!/bin/bash
grep -n "поглотить\|проснулся\|Память — цела\|Что нужно" /root/nox/repo/nox-control/qs6/soul_prompt_ru.txt | cut -c1-260
