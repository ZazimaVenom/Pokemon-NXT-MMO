"""Native service regression: spatial checks, exact prizes and atomic effects."""
import copy,json,random,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
from nxt.content import Content
from nxt.security import RequestError
from nxt import kanto_field as field

class KantoFieldTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=Content(ROOT/'Server/data/world.json')
  # Sidecar itself is authoritative even when running during content publishing.
  cls.c.data['kantoFieldServices']=json.loads((ROOT/'Server/data/kanto_field_services.json').read_text())
 def setUp(self):
  previous=self.c.rng;self.c.rng=random.Random(92026);self.addCleanup(setattr,self.c,'rng',previous)
 def state(self,mid='kanto_3_0',x=10,y=10,direction='down'):
  mon=self.c.new_mon('fr_1',10,'Tester')
  return {'map':mid,'x':x,'y':y,'direction':direction,'items':{k:1 for k in self.c.items if k.startswith('fr_')},'creatures':[mon],'party':[mon['uid']],
          'money':100000,'coins':9999,'adventure':{'seen':[],'caught':[],'trainers':{},'itemPickups':[]}}
 def key(self,sid):
  return next(k for k,v in self.c.items.items() if v.get('source')=='kanto' and v.get('sourceId')==sid)
 def test_three_rods_use_native_slots_only_when_facing_water(self):
  m=self.c.maps['kanto_3_30'];state=self.state(m['id']);found=False
  for y in range(m['height']-1):
   for x in range(m['width']):
    if m['collision'][y*m['width']+x]==0 and m['behavior'][(y+1)*m['width']+x] in field.WATER:
     state.update(x=x,y=y);found=True;break
   if found:break
  self.assertTrue(found)
  for rod,start,end in [('old',0,2),('good',2,5),('super',5,10)]:
   self.assertEqual(field.fishing_slots(self.c,state,rod),m['encounters']['fishing'][start:end])
  bad=self.state()
  with self.assertRaises(RequestError):field.fishing_slots(self.c,bad,'old')
  bad=copy.deepcopy(state);bad['bicycle']=True
  with self.assertRaisesRegex(RequestError,'Bicycle'):field.fishing_slots(self.c,bad,'old')
 def test_card_key_opens_only_faced_native_door_for_owner(self):
  door=self.c.data['kantoFieldServices']['doors'][0];x,y=min(door['tiles']);s=self.state(door['map'],x,y-1);before=copy.deepcopy(s)
  out,_,_=field.use(self.c,s,self.key(355),{})
  self.assertEqual(s,before);self.assertIn(door['sourceFlag'],out['adventure']['kantoFlags'])
  for xx,yy in door['tiles']:
   self.assertTrue(field.collision_override(self.c,out,self.c.maps[s['map']],xx,yy))
   self.assertFalse(field.collision_override(self.c,s,self.c.maps[s['map']],xx,yy))
  self.assertEqual(out['items'][self.key(355)],1)
  with self.assertRaises(RequestError):field.use(self.c,out,self.key(355),{})
 def test_rocket_guard_door_requires_both_native_trainers(self):
  s=self.state('kanto_1_45');m=self.c.maps[s['map']]
  self.assertFalse(field.collision_override(self.c,s,m,17,12))
  s['adventure']['trainers']['kanto_1_45:5']=True
  self.assertFalse(field.collision_override(self.c,s,m,17,12))
  s['adventure']['trainers']['kanto_1_45:6']=True
  self.assertTrue(field.collision_override(self.c,s,m,17,12))
 def test_fossils_need_actual_lab_leave_return_and_capacity(self):
  key=self.key(357);s=self.state();before=copy.deepcopy(s)
  with self.assertRaises(RequestError):field.use(self.c,s,key,{})
  self.assertEqual(s,before)
  s.update(map=field.FOSSIL_LAB,x=12,y=4)
  out,_,_=field.use(self.c,s,key,{})
  self.assertEqual(out['items'][key],0);self.assertEqual(s['items'][key],1)
  with self.assertRaisesRegex(RequestError,'Leave'):field.fossil_collect(self.c,out)
  out['map']='kanto_12_1';field.mark_map_transition(out,field.FOSSIL_LAB,self.c)
  out['map']=field.FOSSIL_LAB
  with self.assertRaisesRegex(RequestError,'storage'):field.fossil_collect(self.c,out,max_owned=1)
  result,_,_=field.fossil_collect(self.c,out,owner='Tester',max_owned=2)
  mon=result['creatures'][-1];self.assertEqual((mon['species'],mon['level'],mon['originalTrainer']),('fr_138',5,'Tester'))
  self.assertIn(mon['uid'],result['party']);self.assertIn(mon['species'],result['adventure']['caught'])
  self.assertNotIn('fossil',result['kantoField'])
 def test_native_prize_identity_cost_and_level(self):
  rows=self.c.data['kantoFieldServices']['coinPrizes'];pokemon=[p for p in rows if p['kind']=='pokemon']
  self.assertEqual([(p['sourceId'],p['coins'],p['level']) for p in pokemon],[(63,180,9),(35,500,8),(147,2800,18),(123,5500,25),(137,9999,26)])
  s=self.state('kanto_10_15',4,4);key=self.key(260);before=copy.deepcopy(s)
  out,_,_=field.service(self.c,s,key,{'action':'prize','kind':'pokemon','reward':'fr_63'},owner='Tester',max_owned=2)
  self.assertEqual(out['coins'],9819);self.assertEqual(out['creatures'][-1]['level'],9);self.assertEqual(s,before)
  with self.assertRaises(RequestError):field.service(self.c,self.state(),key,{'action':'prize','reward':self.key(301)})
 def test_coin_purchase_exact_bundles_capacity_and_atomicity(self):
  s=self.state('kanto_10_14',6,4);s['coins']=0;key=self.key(260)
  out,_,_=field.service(self.c,s,key,{'action':'buycoins','quantity':50})
  self.assertEqual((out['coins'],out['money']),(50,99000));self.assertEqual(s['money'],100000)
  with self.assertRaises(RequestError):field.service(self.c,s,key,{'action':'buycoins','quantity':100})
  s['coins']=9990
  with self.assertRaises(RequestError):field.service(self.c,s,key,{'action':'buycoins','quantity':50})
 def test_key_entrances_are_not_return_traps(self):
  s=self.state();s['items']={}
  self.assertIn('Secret Key',field.portal_block(s,'kanto_3_8','kanto_12_0'))
  self.assertIsNone(field.portal_block(s,'kanto_12_0','kanto_3_8'))
  s['items']['fr_secretkey']=1
  self.assertIsNone(field.portal_block(s,'kanto_3_8','kanto_12_0'))
 def test_itemfinder_owner_flags_and_underfoot_specials(self):
  hidden=self.c.data['adventureRom']['hiddenItemPickups'];p=next(p for p in hidden.values() if p.get('requiresItemfinder'))
  s=self.state(p['map'],p['x'],p['y']);_,extra=field.itemfinder(self.c,s)
  self.assertEqual(extra.get('hiddenPickup'),p['id'])
  s['adventure']['itemPickups']=[p['id']];_,extra=field.itemfinder(self.c,s)
  self.assertNotEqual(extra.get('hiddenPickup'),p['id'])
 def test_mansion_switch_changes_exact_native_collision_and_art(self):
  spec=next(r for r in self.c.data['kantoFieldServices']['mansionSwitches'] if r['map']=='kanto_1_62')
  x,y=spec['switches'][0];s=self.state(spec['map'],x,y+1,'up');before=copy.deepcopy(s)
  switched,_,_=field.interact(self.c,s);self.assertEqual(s,before)
  self.assertIn(0x26c,switched['adventure']['kantoFlags'])
  for value,tiles in [(s,spec['off']),(switched,spec['on'])]:
   for tile in tiles:self.assertEqual(field.collision_state(self.c,value,self.c.maps[value['map']],tile['x'],tile['y']),tile['collision']==0)
   self.assertEqual(field.context(self.c,value)['fieldTiles'],[{k:t[k] for k in ('x','y','metatile')} for t in tiles])
  reset,_,_=field.interact(self.c,switched);self.assertNotIn(0x26c,reset['adventure']['kantoFlags'])
 def test_lift_destinations_preserve_account_exit_and_reject_outside(self):
  from nxt.portals import plan_warp
  key=self.key(356);s=self.state('kanto_1_46',2,4)
  for destination,arrival in [('kanto_1_42',(24,26)),('kanto_1_43',(28,17)),('kanto_1_45',(20,24))]:
   out,_,_=field.use(self.c,s,key,{'destination':destination})
   plan=plan_warp(self.c,out,self.c.maps[out['map']],2,5,'down')
   self.assertEqual((plan['map'],plan['x'],plan['y']),(destination,*arrival));self.assertEqual(out['items'][key],1)
   self.assertNotIn('warpReturns',s)
  with self.assertRaises(RequestError):field.use(self.c,s,key,{'destination':'kanto_1_44'})
 def test_story_handovers_consume_atomically_and_tea_opens_all_gates(self):
  s=self.state('kanto_4_3',6,4);key=self.key(349);balls=self.key(4);before=copy.deepcopy(s)
  out,_,_=field.use(self.c,s,key,{})
  self.assertEqual(s,before);self.assertEqual(out['items'][key],0);self.assertEqual(out['items'][balls],6);self.assertIn(0x829,out['adventure']['kantoFlags'])
  s=self.state('kanto_17_1',2,5);out,_,_=field.use(self.c,s,self.key(369),{})
  for source in ('kanto_17_1','kanto_18_0','kanto_19_0','kanto_20_0'):
   self.assertIsNotNone(field.portal_block(s,source,'kanto_3_10'));self.assertIsNone(field.portal_block(out,source,'kanto_3_10'))
 def test_vs_seeker_requires_successful_step_charge_and_nearby_defeated_trainer(self):
  trainer=next(t for t in self.c.data['adventureRom']['trainers'].values() if t['map'].startswith('kanto_3_') and self.c.maps[t['map']]['mapType'] in (1,2,3))
  s=self.state(trainer['map'],trainer['x'],trainer['y']);s['adventure']['trainers'][trainer['id']]=True;key=self.key(362)
  with self.assertRaises(RequestError):field.use(self.c,s,key,{})
  for _ in range(100):field.after_step(s)
  out,_,extra=field.use(self.c,s,key,{})
  self.assertEqual(out['kantoField']['vsSeekerCharge'],0);self.assertEqual(s['kantoField']['vsSeekerCharge'],100)
  self.assertIn(trainer['id'],extra['rematches']);self.assertTrue(field.rematch_ready(out,trainer))
  field.consume_rematch(out,trainer);self.assertFalse(field.rematch_ready(out,trainer));self.assertEqual(out['items'][key],1)
 def test_powder_medicine_native_price_and_no_fabricated_earnings(self):
  s=self.state('kanto_7_9',7,5);jar=self.key(372);energy=self.key(30)
  with self.assertRaises(RequestError):field.service(self.c,s,jar,{'action':'medicine','reward':energy})
  self.assertNotIn('berryPowder',s);s['berryPowder']=50
  out,_,_=field.service(self.c,s,jar,{'action':'medicine','reward':energy})
  self.assertEqual(out['berryPowder'],0);self.assertEqual(s['berryPowder'],50);self.assertEqual(out['items'][energy],2)
  self.assertEqual(len(self.c.data['kantoFieldServices']['powderPrizes']),11)

if __name__=='__main__':unittest.main()
