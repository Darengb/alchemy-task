"""Several actions in one email need action anchors; every refusal says how to fix it."""
import pytest
from alchemy_task.core import discovery_identity as di
from alchemy_task.core import discovery_research as dr
from alchemy_task.core.discovery_identity import UserError


def test_bad_locator_refusal_names_the_accepted_syntax():
    with pytest.raises(UserError) as err:
        di.freeze_actions('c_1', ['gmail:acct:t1:m1'], [{'locator': 'gmail:acct:t1:m1#quiz', 'outcome': 'Build the quiz'}])
    text = str(err.value)
    assert 'bullet:3' in text and 'section:' in text and 'message' in text
    ok = di.freeze_actions('c_1', ['gmail:acct:t1:m1'], [{'locator': 'section:all-products-quiz', 'outcome': 'Build the quiz'},
                                                         {'locator': 'bullet:2', 'outcome': 'Add multivitamin sections'}])
    assert len(ok) == 2


def test_shared_decisive_message_repair_offers_action_anchors_for_separate_actions():
    text = dr.DECISIVE_REPAIR
    assert 'action anchor' in text and 'discovery_actions' in text and 'SAME action' in text
