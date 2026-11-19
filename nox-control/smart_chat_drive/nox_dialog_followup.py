"""Identify terse conversational follow-ups in the current authenticated dialog."""

import re
import unicodedata


MAX_HISTORY_MESSAGES = 12
MAX_USER_TURNS = 4
MAX_TOPIC_CHARS = 600
MAX_FOLLOWUP_CHARS = 64
FOCUS_HINT = (
    'Короткий вопрос может продолжать текущий диалог. Определи, о чём он, по ближайшим '
    'сообщениям пользователя. Если возможны разные ссылки, задай один короткий вопрос. '
    'Предыдущие ответы не подтверждают состояние или выполненные действия сейчас.'
)

_FOLD = str.maketrans('ёáéíóú', 'еaeiou')
_TERSE = re.compile(
    r'(?:(?:ну|а|так|значит) )?'
    r'(?:(?:он|она|оно|они|оба|обе|все|это|доступ|связь) (?:же )?)?'
    r'(?:есть|работает|работают|подключен[аоы]?|доступен|доступна|доступно|доступны|'
    r'точно|возможно|можно|нельзя|правда|сработает|получилось|готов[аоы]?)'
    r'(?: (?:же|да|или нет))?'
    r'|(?:(?:ну|а|так) )?(?:и|и что|а он|а она|а оно|а они|где|когда|почему|сколько|как именно|зачем)'
    r'|(?:is it|are they) (?:there|connected|available)(?: (?:right|though))?'
    r'|(?:does it work|do they work|you have it|you have them|are you sure|what about it)(?: right)?'
    r'|(?:where|when|why|how many)'
    r'|(?:esta|estan) (?:disponible[s]?|conectad[oa]s?)(?: verdad)?'
    r'|(?:lo tienes|los tienes|funciona|funcionan|es cierto|seguro)(?: verdad)?'
    r'|(?:donde|cuando|por que|cuantos)'
)
_PLURAL = re.compile(r'\b(?:они|оба|обе|все|работают|подключены|доступны|'
                     r'they|them|estan|los|funcionan)\b')
_RESET = re.compile(r'(?:новая тема|другая тема|забудь (?:это|предыдущее)|new topic|otro tema)')


def _normalize(text):
    value = unicodedata.normalize('NFKC', text).casefold().translate(_FOLD)
    return ' '.join(value.strip(' ¿¡?!.,').replace(',', ' ').split())


def _terse_followup(text):
    if not isinstance(text, str) or len(text) > MAX_FOLLOWUP_CHARS:
        return None
    normalized = _normalize(text)
    return normalized if _TERSE.fullmatch(normalized) else None


def resolve_followup(question, authoritative_history):
    """Return a contextual reference or an unresolved terse follow-up.

    The history is authenticated, prior-only dialog data. A caller may use the
    reference to preserve existing turns in the model budget. It must keep the
    user's literal latest text and use the existing dialog messages once.
    """
    normalized = _terse_followup(question)
    if normalized is None:
        return None
    plural = bool(_PLURAL.search(normalized))
    unresolved = {'state': 'UNRESOLVED', 'plural_reference': plural}
    if not isinstance(authoritative_history, (list, tuple)):
        return unresolved

    user_turns = 0
    oldest = max(0, len(authoritative_history) - MAX_HISTORY_MESSAGES)
    for index in range(len(authoritative_history) - 1, oldest - 1, -1):
        message = authoritative_history[index]
        if not isinstance(message, dict) or message.get('role') not in ('user', 'assistant'):
            break
        if message['role'] == 'assistant':
            continue
        user_turns += 1
        if user_turns > MAX_USER_TURNS:
            break
        content = message.get('content')
        if not isinstance(content, str) or not content.strip() or len(content) > MAX_TOPIC_CHARS:
            break
        if _RESET.fullmatch(_normalize(content)):
            break
        if _terse_followup(content) is not None:
            continue
        return {'state': 'CONTEXTUAL', 'prior_user_index': index, 'prior_user_text': content,
                'plural_reference': plural}
    return unresolved
