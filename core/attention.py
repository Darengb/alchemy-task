"""Sort a run's unfinished items into what needs the user and what does not.

Shared by the chat digest and the dashboard so both show the same thing.

- ``attention``: something is lost unless the user acts (nothing will retry it).
- ``moved``: the next run researches it again; nothing for the user to do.
- ``not_proposed``: researched, but covered by another item, owned by someone else with no part
  for the user, or left out on purpose.

Every group carries plain text for the user: no ids, field names or review wording.
"""
from __future__ import annotations

import re

from .digest_text import first_sentence

ATTENTION, MOVED, NOT_PROPOSED = 'attention', 'moved', 'not_proposed'

TIME_BOX = "not finished within this run's research time"
NOT_REVIEWED = 'not reviewed in this run'
MATCH_FAILED = 'could not be matched to your tasks'
# A unit whose research says another person owns the action and the user has no part in it.
NOT_YOURS = 'not_yours'

_LIFECYCLE = re.compile(r'\s*lifecycle terminal ([A-Za-z_]+)\s*')
# Review wording that says the item repeats another one.
_DUPLICATE = re.compile(r'\b(?:represent(?:s|ed)?|duplicat\w*|redundant|repeats?\b|already[- ]accepted|same (?:action|ask|alignment))',
                        re.I)
# Text written for the agent, not the user: field names, ids, paths, stack traces, repair instructions.
_INTERNAL = re.compile(r'\b[a-z]+_[a-z_]+\b|\b[cw]_[0-9a-f]{20}\b|\b(?:Repair|payload|bundle|workstream|schema|disposition)\b|'
                       r'Error:|Exception:|Traceback|fatal:|(?:^|\s)/[^\s]+|[a-f0-9]{8}-[a-f0-9-]{27,}')


def _user_text(reason, title):
    reason = re.sub(r'^\s*(?:Needs attention:\s*)?' + (re.escape(title) + r'\s*:\s*' if title else ''), '', reason, flags=re.I) or reason
    text = first_sentence(reason)
    if len(text) > 160:
        text = text[:160].rsplit(' ', 1)[0].rstrip(' ,;:') + '...'
    return text


def user_has_no_part(research):
    """True only when research explicitly set user_role 'none'. Older research without the field never hides."""
    return isinstance(research, dict) and research.get('user_role') == 'none'


def not_yours_text(research):
    """Plain reason naming the owner, for example 'Owned by Doug; you have no part in it.'"""
    owners = research.get('owner_and_collaborators') if isinstance(research, dict) else None
    name = next((' '.join(str(o.get('name') or '').split()) for o in owners or []
                 if isinstance(o, dict) and o.get('role') == 'owner' and str(o.get('name') or '').strip()), '')
    name = re.sub(r'\s*\(.*$', '', name)[:80].rstrip(' ,;:')
    return f'Owned by {name}; you have no part in it.' if name else 'Owned by someone else; you have no part in it.'


def classify(failure):
    """{'group', 'text'} for one failure record.

    ``retry_pending`` on the record (set by the plugin from the source backlog) says whether a later run
    researches the item again; absent means unknown, which is treated as no retry so nothing is hidden.
    """
    reason = str(failure.get('reason') or '').strip()
    title = str(failure.get('title') or '')
    retry = failure.get('retry_pending') is True
    if failure.get('kind') == NOT_YOURS:
        return {'group': NOT_PROPOSED, 'text': reason or 'Owned by someone else; you have no part in it.'}
    if failure.get('kind') == 'covered':
        return {'group': NOT_PROPOSED, 'text': 'Covered by another item.'}
    if _DUPLICATE.search(reason):
        return {'group': NOT_PROPOSED, 'text': 'Covered by another item.'}
    if reason.startswith(TIME_BOX):
        return {'group': MOVED, 'text': 'Research ran out of time. It continues in the next run.'}
    if reason.startswith(NOT_REVIEWED):
        return {'group': NOT_PROPOSED, 'text': 'Researched, but not proposed in this run.'}
    if reason.startswith(MATCH_FAILED):
        return {'group': ATTENTION, 'text': "Couldn't be matched to your tasks. Ask Hermes to look at it."}
    if retry:
        return {'group': MOVED, 'text': 'Research needs another pass. It continues in the next run.'}
    if _LIFECYCLE.fullmatch(reason) or not reason or _INTERNAL.search(reason):
        return {'group': ATTENTION, 'text': "Couldn't be researched. Open the source to check it."}
    return {'group': ATTENTION, 'text': _user_text(reason, title)}


def sort_failures(failures):
    """(attention, moved, not_proposed): each a list of the failure records plus 'group' and 'text'."""
    out = {ATTENTION: [], MOVED: [], NOT_PROPOSED: []}
    for f in failures or []:
        c = classify(f)
        out[c['group']].append({**f, **c})
    return out[ATTENTION], out[MOVED], out[NOT_PROPOSED]
