"""Short digest fields (stdlib only).

Research writes authored 1 to 2 sentence digest fields (digest_current_state,
digest_next_action, digest_addition). Older bundles lack them; for those the
digest shows the first whole sentence of the long field. Nothing is cut
mid-sentence. ui/src/lib/digestText.js implements the same rule.
"""
from __future__ import annotations

import re

DIGEST_FIELDS = {
    'digest_current_state': 'current_understanding',
    'digest_next_action': 'substantive_next_action',
    'digest_addition': 'new_information',
}
DIGEST_FIELD_MAX = 300
# A sentence ends at . ! or ? followed by whitespace and a capital, digit or
# opening quote. URLs hold no whitespace, so a split never lands inside one.
_SENTENCE_END = re.compile(r'(?<=[.!?])["\')\]]*(?=\s+["\'(\[]?[A-Z0-9])')


def first_sentence(text):
    """The first whole sentence of text, whitespace flattened."""
    flat = ' '.join(str(text or '').split())
    match = _SENTENCE_END.search(flat)
    return flat[:match.end()] if match else flat


def digest_field(item, key):
    """Authored digest_* text, else the first sentence of its long field."""
    authored = ' '.join(str(item.get(key) or '').split())
    if authored:
        return authored
    long = item.get(DIGEST_FIELDS[key])
    if isinstance(long, list):
        long = next((str(x) for x in long if str(x).strip()), '')
    return first_sentence(long)
