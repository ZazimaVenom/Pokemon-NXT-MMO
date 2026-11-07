"""Real-map regressions for owner-scoped Strength/Rock Smash field licences."""
import asyncio,copy,dataclasses,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
from nxt.content import Content
from nxt.world import World
from nxt import kanto_obstacles as obstacles
from nxt.security import RequestError
from nxt.config import Settings
from nxt.store import Store

class KantoObstacleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=Content(ROOT/'Server/data/world.json');cls.w=World.__new__(World);cls.w.c=cls.c
 def state(self,map_id='kanto_1_39',x=17,y=3):
  return dict(map=map_id,x=x,y=y,surf=False,items={},adventure={'badges':['kanto_4','kanto_6'],'kantoObstacles':{}})
 def obj(self,map_id,npc):return next(o for o in self.c.maps[map_id]['objects'] if o['id']==npc)
 def act(self,state,npc,action):return obstacles.act(self.c,state,self.obj(state['map'],npc),action,self.w.walkable)
 def test_native_victory_road_boulder_pushes_twice_without_hm_items(self):
  state=self.state();original=copy.deepcopy(state);native=self.obj(state['map'],7);map_before=copy.deepcopy(native)
  first=self.act(state,7,'push');second=self.act(first,7,'push')
  self.assertEqual((first['x'],first['y']),(16,3));self.assertEqual((second['x'],second['y']),(15,3))
  self.assertEqual(obstacles.object_position(second,state['map'],native)['x'],14)
  self.assertEqual(second['items'],{});self.assertEqual(state,original);self.assertEqual(native,map_before)
 def test_badge_cannot_be_replaced_by_client_unlock_or_hm(self):
  state=self.state();state['adventure']['badges']=['johto_4'];state['adventure']['unlocks']=['strength_kanto'];state['items']['fr_hm04']=1
  with self.assertRaisesRegex(RequestError,'Rainbow Badge'):self.act(state,7,'push')
  state=self.state('kanto_3_15',5,12);state['adventure']['badges']=['kanto_4']
  with self.assertRaisesRegex(RequestError,'Marsh Badge'):self.act(state,7,'smash')
 def test_cardinal_adjacency_and_correct_graphics_are_authoritative(self):
  with self.assertRaisesRegex(RequestError,'directly beside'):self.act(self.state(x=17,y=4),7,'push')
  with self.assertRaisesRegex(RequestError,'does not support'):self.act(self.state(),7,'smash')
  with self.assertRaisesRegex(RequestError,'does not support'):self.act(self.state(x=15,y=1),4,'push')
 def test_real_wall_and_inventory_pickup_block_push(self):
  with self.assertRaises(RequestError):self.act(self.state(x=16,y=4),7,'push')
  state=self.state('kanto_3_61',40,32);first=self.act(state,12,'push');before=copy.deepcopy(first)
  self.assertEqual(obstacles.object_position(first,state['map'],self.obj(state['map'],12))['x'],42)
  with self.assertRaisesRegex(RequestError,'Another object'):self.act(first,12,'push')
  self.assertEqual(first,before)
 def test_four_island_rock_clear_is_owner_only_and_replay_rejected(self):
  state=self.state('kanto_3_15',5,12);peer=copy.deepcopy(state);obj=self.obj(state['map'],7);out=self.act(state,7,'smash')
  self.assertTrue(obstacles.is_cleared(out,state['map'],obj));self.assertFalse(obstacles.is_cleared(peer,state['map'],obj));self.assertEqual((out['x'],out['y']),(5,12))
  with self.assertRaisesRegex(RequestError,'already'):self.act(out,7,'smash')
 def test_surfing_and_false_walkability_never_move_boulder(self):
  state=self.state();state['surf']=True
  with self.assertRaisesRegex(RequestError,'dry land'):self.act(state,7,'push')
  state=self.state();calls=[]
  def blocked(*args,**kwargs):calls.append(kwargs);return False
  with self.assertRaisesRegex(RequestError,'not enough room'):obstacles.act(self.c,state,self.obj(state['map'],7),'push',blocked)
  self.assertEqual(calls[0]['from_elevation'],3);self.assertEqual(state['adventure']['kantoObstacles'],{})
 def test_map_leave_resets_boulders_and_preserves_owner_rock_progress(self):
  state=self.state('kanto_1_97',33,14);out=self.act(state,12,'smash');out.update(x=35,y=15);out=self.act(out,14,'push')
  obstacles.reset_on_leave(out,state['map']);self.assertTrue(obstacles.is_cleared(out,state['map'],self.obj(state['map'],12)))
  self.assertEqual(obstacles.object_position(out,state['map'],self.obj(state['map'],14))['y'],14)
 def test_invalid_saved_records_cannot_clear_other_graphics_or_invent_positions(self):
  state=self.state();state['adventure']['kantoObstacles']={'kanto_1_39':{'4':{'graphics':96,'cleared':True},'7':{'graphics':97,'x':True,'y':3},'5':{'graphics':97,'x':999,'y':3}},'johto_0_0':{'7':{'graphics':96,'cleared':True}}}
  obstacles.migrate(state,self.c.maps);self.assertEqual(state['adventure']['kantoObstacles'],{})
 def test_saved_position_is_resolved_instead_of_trusting_passed_coordinates(self):
  state=self.act(self.state(),7,'push');supplied=copy.deepcopy(self.obj(state['map'],7));supplied.update(x=50,y=50)
  out=obstacles.act(self.c,state,supplied,'push',self.w.walkable)
  self.assertEqual((out['x'],out['y']),(15,3));self.assertEqual(obstacles.object_position(out,state['map'],supplied)['x'],14)


class DurableKantoObstacleTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();cfg=Path(self.tmp.name)/'config.ini';cfg.write_bytes((ROOT/'Build/config_templates/Server/config.ini').read_bytes());settings=Settings.load(cfg);settings.config.set('database','backend','sqlite');self.settings=dataclasses.replace(settings,encounter_chance=0)
  self.c=Content(ROOT/'Server/data/world.json');self.db=Store(self.settings);self.db.acquire_lease();self.w=World(self.c,self.db,self.settings)
  self.owner=await self.add('ObstacleOwner');self.peer=await self.add('ObstaclePeer')
 async def add(self,name):
  state=self.w.initial(name,'Kanto','fr_4',0);state.update(map='kanto_1_39',x=17,y=3);state['adventure']['badges']=['kanto_4','kanto_6'];uid=self.db.create(name,'unused',state)
  return await self.w.join(uid,name,state,asyncio.Queue(maxsize=4096))
 async def asyncTearDown(self):self.w.players.clear();self.db.close();self.tmp.cleanup()
 async def test_push_persists_and_changes_only_owners_collision(self):
  peer_before=copy.deepcopy(self.peer.state);await self.w.dispatch(self.owner,{'op':'npc','npc':7,'action':'push_boulder','map':'kanto_1_39'})
  saved=self.db.load(self.owner.id);self.assertEqual(saved['adventure']['kantoObstacles']['kanto_1_39']['7'],{'graphics':97,'x':15,'y':3});self.assertEqual((saved['x'],saved['y']),(16,3));self.assertEqual(self.peer.state,peer_before)
  m=self.c.maps['kanto_1_39'];self.assertTrue(self.w.walkable(m,16,3,state=self.owner.state));self.assertFalse(self.w.walkable(m,16,3,state=self.peer.state));self.assertFalse(self.w.walkable(m,15,3,state=self.owner.state))
  old=self.owner;self.w.players.pop(old.id);self.owner=await self.w.join(old.id,old.username,saved,asyncio.Queue(maxsize=4096));self.assertEqual(self.owner.state['adventure']['kantoObstacles'],saved['adventure']['kantoObstacles'])
 async def test_smash_persists_and_peer_rock_remains(self):
  state=self.w.relocation_state(self.owner,'kanto_3_15',5,12);await self.w.commit(self.owner,state);peer_before=copy.deepcopy(self.peer.state)
  await self.w.dispatch(self.owner,{'op':'npc','npc':7,'action':'smash_rock','map':'kanto_3_15'})
  saved=self.db.load(self.owner.id);obj=next(o for o in self.c.maps['kanto_3_15']['objects'] if o['id']==7);self.assertTrue(obstacles.is_cleared(saved,'kanto_3_15',obj));self.assertEqual(self.peer.state,peer_before)
  m=self.c.maps['kanto_3_15'];self.assertTrue(self.w.walkable(m,5,11,state=self.owner.state));self.assertFalse(self.w.walkable(m,5,11,state=self.peer.state))
 async def test_failed_obstacle_commit_never_publishes_position(self):
  before=copy.deepcopy(self.owner.state)
  with patch.object(self.db,'save_many',side_effect=OSError('injected failure')):
   with self.assertLogs('nxt.world',level='ERROR'):
    with self.assertRaises(RequestError):await self.w.dispatch(self.owner,{'op':'npc','npc':7,'action':'push_boulder','map':'kanto_1_39'})
  self.assertEqual(self.owner.state,before);self.assertEqual(self.db.load(self.owner.id),before)
 async def test_real_map_transition_resets_native_boulder_position(self):
  await self.w.dispatch(self.owner,{'op':'npc','npc':7,'action':'push_boulder','map':'kanto_1_39'})
  candidate=self.w.relocation_state(self.owner,'kanto_3_0');self.assertNotIn('kanto_1_39',candidate['adventure']['kantoObstacles']);self.assertIn('kanto_1_39',self.owner.state['adventure']['kantoObstacles'])

if __name__=='__main__':unittest.main()
