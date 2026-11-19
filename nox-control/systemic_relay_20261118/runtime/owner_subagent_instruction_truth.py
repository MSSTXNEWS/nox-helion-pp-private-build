#!/usr/bin/env python3
"""Remove two unsupported identity sentences from the pinned reviewer prompt.

The source179e callback, its observations/configuration and all execution
permissions remain unchanged. The wrapper performs no I/O for any model turn.
"""
import hashlib
from pathlib import Path

CALLBACK_SHA = '0193c511168489637b6df041bee2daf79bd42bd338c4ff5f9a6b129652dc4a13'
CALLBACK_PATH = Path('/root/nox/scripts/owner_subagent_dispatcher.py')
OLD = ('Новая главная модель — DeepSeek; Qwen3.5-9B — отдельный помощник. '
       'Старые35B шаги не являются обучением новых весов. ')
NEW = ('Названия и роли действующих моделей, обновления весов и состояние обучения '
       'указывай только по проверенным текущим данным. Старые наблюдения об обучении '
       'считай историческими и не используй как доказательство состояния текущих весов. ')
BOUND = None


def replace_instruction(text):
    if not isinstance(text, str) or text.count(OLD) != 1:
        raise RuntimeError('HOLD_SUBAGENT_TRUTH_PROMPT_PREIMAGE')
    return text.replace(OLD, NEW, 1)


def bind(callback, source_reader):
    global BOUND
    if (BOUND is not None or Path(callback.__file__) != CALLBACK_PATH
            or hashlib.sha256(source_reader(callback.__file__)).hexdigest() != CALLBACK_SHA):
        raise RuntimeError('HOLD_SUBAGENT_TRUTH_SOURCE_PIN')
    original = callback.model_instruction
    if (not callable(original) or original.__globals__ is not callback.__dict__
            or original.__name__ != 'model_instruction'):
        raise RuntimeError('HOLD_SUBAGENT_TRUTH_FUNCTION')
    # Exercise all original role branches before replacing the function. This
    # public fixture introduces neither a model request nor a policy read.
    fixture = '1C: runtime\n2B: memory\n2D: weights\n'
    for role in ('runtime', 'memory', 'weights'):
        replace_instruction(original(fixture, role))
    def truthful(policy, role):
        return replace_instruction(original(policy, role))
    callback.model_instruction = truthful
    BOUND = {'callback': callback, 'original': original, 'replacement': truthful}


def spawn_prompt_probe(connection):
    """Public-only probe after multiprocessing's actual main-path reimport."""
    from owner_subagent_dispatcher import model_instruction
    fixture = '1C: runtime\n2B: memory\n2D: weights\n'
    rows = [model_instruction(fixture, role) for role in ('runtime', 'memory', 'weights')]
    connection.send({'bound_in_spawned_child': BOUND is not None,
                     'all_roles_truthful': all(OLD not in row and NEW in row for row in rows)})
    connection.close()
