"""Pure, exact-source addition to the serving chat's existing SLIM_RULES.

This file never imports native modules or writes native state. The installer
must supply the full observed native source SHA, preserve unrelated bytes and
reload only the existing proxy after its own current process/idle checks.
"""
from __future__ import annotations

import ast
import hashlib
import re


DECOMPOSITION_RULES = (
    'Поручение означает начать разрешённую работу. Определи ожидаемый результат '
    'и его проверку, затем наметь 1–5 шагов с входами и зависимостями соразмерно сложности. '
    'Сначала используй текущий диалог, проверенную память и доступные инструменты; '
    'известные имена, пути и цели не спрашивай повторно. Для низкорисковых деталей '
    'выбери разумное значение и кратко назови его. Проверь доступные возможности, '
    'прежде чем объявлять их недоступными. Независимые части передавай '
    'существующим трём исполнителям только через реально доступный диспетчер; '
    'зависимые шаги выполняй по порядку. Сохраняй один PRIME, один диспетчер и S03; '
    'не запускай второй контур. После шага подтверди фактический результат и продолжай '
    'следующий. Для кода сохраняй обязательную проверку. План и очередь не считай выполнением. Если шаг недоступен, '
    'выполни доступную подготовку и назови точный блокер. Уточняй только действительно '
    'блокирующий выбор. Не выдумывай права Google Drive, ключи или подключённые сервисы. '
    'STOP и существующие ограничения сохраняются.'
)


def patch_slim(raw: bytes, expected_sha256: str) -> bytes:
    """Change one literal assignment and retain every other source byte."""
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= 131072
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r'[a-f0-9]{64}', expected_sha256) is None
            or hashlib.sha256(raw).hexdigest() != expected_sha256):
        raise ValueError('HOLD_CHAT_DECOMPOSITION_SOURCE_PIN')
    text = raw.decode('utf-8')
    tree = ast.parse(text)
    rules = [node for node in tree.body if isinstance(node, ast.Assign)
             and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
             and node.targets[0].id == 'SLIM_RULES']
    apply = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name == 'apply_system']
    if len(rules) != 1 or len(apply) != 1:
        raise ValueError('HOLD_CHAT_DECOMPOSITION_BINDING')
    if not any(isinstance(node, ast.Name) and node.id == 'SLIM_RULES'
               for node in ast.walk(apply[0])):
        raise ValueError('HOLD_CHAT_DECOMPOSITION_NOT_LOADED')
    existing = ast.literal_eval(rules[0].value)
    if not isinstance(existing, str) or DECOMPOSITION_RULES in existing:
        raise ValueError('HOLD_CHAT_DECOMPOSITION_RULES')
    combined = existing + '\n\n' + DECOMPOSITION_RULES
    if len(combined.encode('utf-8')) > 4096:
        raise ValueError('HOLD_CHAT_DECOMPOSITION_PROMPT_BUDGET')
    old = ast.get_source_segment(text, rules[0])
    if not old or text.count(old) != 1:
        raise ValueError('HOLD_CHAT_DECOMPOSITION_ANCHOR')
    result = text.replace(old, 'SLIM_RULES = ' + repr(combined), 1).encode('utf-8')
    changed = ast.parse(result)
    for index, node in enumerate(tree.body):
        if node is rules[0]:
            continue
        if ast.dump(node, include_attributes=False) != ast.dump(changed.body[index], include_attributes=False):
            raise ValueError('HOLD_CHAT_DECOMPOSITION_UNRELATED_AST')
    if len(changed.body) != len(tree.body):
        raise ValueError('HOLD_CHAT_DECOMPOSITION_UNRELATED_BINDING')
    return result
