"""Direct generic transformations of current daily matching regression cases."""
import pytest
from alchemy_task.core.store import TaskStore
from test_discovery_conversion import custom_joined

@pytest.mark.parametrize('stored,basis,expected',[
 ('slack:T1:C1:171.1',None,'new'),
 ('slack:T1:C1:171.1','related_only','semantic'),
 ('slack:T1:C1:171.1','exact','exact'),
 ('slack:T1:C1:171.1:171.2',None,'exact'),
 ('slack:T1:C1:171.1:171.3',None,'new'),
])
def test_source_decomposed_message_direction_and_nomination(settings,data_dir,tmp_path,stored,basis,expected):
 tasks=TaskStore(settings,data_dir)
 task=tasks.create(title='Unrelated title does not decide matching',area='work',undated=True,research=False,notes=stored)
 nominations=[{'path':tasks.rel(task.path),'match_basis':basis}] if basis else []
 rt,store,run,wid,conversion=custom_joined(settings,data_dir,tmp_path,nominations)
 outcome=conversion.match(run,wid)
 assert outcome['kind']==expected
 if expected=='exact':assert outcome['targets'][0]['task_id']==task.task_id
