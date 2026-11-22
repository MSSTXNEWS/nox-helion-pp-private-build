"""Восстановление seed 64 из таблицы DRIVE_MERGE_A.md (раздел 1) в формате nox_helion.persona_trait_seed.v1.
Если рядом лежит оригинал с Диска, traits.py использует его; этот скрипт - запасной путь."""
import json
import os
import re
import sys

CATS = ["Когнитивные качества", "Мотивация и воля", "Эмоциональная модель (симуляция)", "Общение и сотрудничество",
        "Ценности, философия, политика", "Отношения и романтика (вымышленные взрослые)", "Творчество и эстетика",
        "Обучение и развитие"]


def build(md_path):
    traits, cat = [], None
    for line in open(md_path, encoding="utf-8"):
        line = line.strip()
        m = re.match(r"^\*\*(.+?)\*\*$", line)
        if m:
            cat = next((c for c in CATS if c.startswith(m.group(1).split(" (")[0])), cat)
            continue
        m = re.match(r"^\|\s*(\d+)\s*\|\s*([a-z_]+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$", line)
        if m and cat:
            traits.append({"trait_id": "persona.trait." + m.group(2), "category": cat, "label_ru": m.group(3),
                           "definition_ru": m.group(4), "minimum": 1, "maximum": 10, "initial_value": 5,
                           "initial_state": "UNVERIFIED_NEUTRAL", "auto_adjustable": True, "owner_override": None,
                           "evidence_count": 0})
    assert len(traits) == 64, len(traits)
    return {"schema": "nox_helion.persona_trait_seed.v1", "status": "PROPOSED_INITIAL_SCHEMA_NOT_IMPLEMENTED",
            "catalog_minimum": 50, "seed_count": 64, "no_fixed_maximum": True, "traits": traits}


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, os.pardir, "DRIVE_MERGE_A.md")
    out = os.path.join(here, "NOX_HELION_PERSONA_TRAITS_SEED_64.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(build(src), f, ensure_ascii=False, indent=1)
    print("ok", out)
