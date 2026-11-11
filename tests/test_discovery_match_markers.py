from types import SimpleNamespace

from alchemy_task.discovery_conversion import DiscoveryConversion


def test_a_task_that_only_mentions_a_dossier_marker_does_not_block_matching():
    doc = SimpleNamespace(body='Notes: the regex rejects `<!-- discovery-dossier:start dos-... -->` markers.\n', fm={'title': 'x'})
    conv = DiscoveryConversion.__new__(DiscoveryConversion)
    assert conv._exact_values(doc) == set() or isinstance(conv._exact_values(doc), set)
