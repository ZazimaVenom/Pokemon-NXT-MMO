"""Pure Surf rule tests: authoritative ownership, region, terrain and recovery."""
import copy,sys,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
from nxt import surf
from nxt.world import World
from nxt.security import RequestError

class SurfRules(unittest.TestCase):
 def setUp(self):
  self.land=dict(id='kanto_0_0',width=5,height=5,collision=[0]*25,behavior=[0]*25,elevation=[3]*25,objects=[],warps=[])
  self.johto=copy.deepcopy(self.land);self.johto['id']='johto_0_0'
  for m in (self.land,self.johto):
   for x,y in ((2,3),(3,2),(3,3)):
    i=y*5+x;m['behavior'][i]=21;m['elevation'][i]=1
  self.c=SimpleNamespace(maps={self.land['id']:self.land,self.johto['id']:self.johto},species={'fire':{'types':[10],'name':'Fire'},'water':{'types':[11],'name':'Water'},'dual':{'types':[2,11],'name':'Dual Water'}},data={'homes':{'Kanto':'kanto_0_0','Johto':'johto_0_0'},'kantoItems':{}})
  for m in (self.land,self.johto):m['spawn']=[1,1]
  self.w=World.__new__(World);self.w.c=self.c
  self.state=dict(map='kanto_0_0',home='Kanto',x=2,y=2,direction='down',surf=False,party=['fire','water'],creatures=[{'uid':'fire','species':'fire','hp':10},{'uid':'water','species':'water','hp':0,'variety':'shiny'}],adventure={'badges':['kanto_5'],'unlocks':[]})
 def context(self,state=None):return surf.context(self.c,state or self.state,self.w.walkable)
 def test_regional_badge_and_actual_party_are_required_independently_of_home(self):
  self.assertTrue(self.context()['available']);self.state['home']='Johto';self.assertTrue(self.context()['available'])
  self.state['map']='johto_0_0';self.assertFalse(self.context()['available']);self.state['adventure']['badges'].append('johto_4');self.assertTrue(self.context()['available'])
  self.state['party']=['fire'];self.assertFalse(self.context()['available'])
 def test_fainted_dual_type_partner_is_eligible_and_lead_stays_unchanged(self):
  self.state['creatures'][1]['species']='dual';out=surf.launch(self.c,self.state,self.w.walkable)
  self.assertEqual(out['surfPokemon']['uid'],'water');self.assertEqual(out['surfPokemon']['variety'],'shiny');self.assertEqual(out['party'],['fire','water']);self.assertEqual(self.state['surf'],False)
 def test_forged_unlock_and_storage_water_do_not_grant_licence(self):
  self.state['adventure']={'badges':[],'unlocks':['surf_kanto']};self.assertFalse(self.context()['available'])
  self.state['adventure']['badges']=['kanto_5'];self.state['party']=['fire'];self.assertFalse(self.context()['available'])
 def test_facing_water_first_and_deterministic_cardinal_fallback(self):
  self.assertEqual(self.context()['shoreline'],{'x':2,'y':3,'direction':'down'})
  self.state['direction']='left';self.assertEqual(self.context()['shoreline'],{'x':3,'y':2,'direction':'right'})
 def test_launch_moves_exactly_one_step_records_shore_and_disables_bike(self):
  self.state['bicycle']=True;before=copy.deepcopy(self.state);out=surf.launch(self.c,self.state,self.w.walkable)
  self.assertEqual((out['x'],out['y']),(2,3));self.assertTrue(out['surf']);self.assertFalse(out['bicycle']);self.assertEqual(out['surfAnchor']['x'],2);self.assertEqual(self.state,before)
  self.assertNotIn('uid',surf.public_partner(out));self.assertEqual(surf.public_partner(out)['species'],'water')
 def test_no_inland_activation_and_no_toggle_while_on_water(self):
  self.state.update(x=0,y=0)
  with self.assertRaises(RequestError):surf.launch(self.c,self.state,self.w.walkable)
  self.state.update(x=2,y=2);out=surf.launch(self.c,self.state,self.w.walkable)
  with self.assertRaisesRegex(RequestError,'already'):surf.launch(self.c,out,self.w.walkable)
 def test_walls_npcs_cliffs_and_waterfalls_do_not_offer_launch(self):
  for blocker in ('collision','object','elevation','waterfall'):
   with self.subTest(blocker=blocker):
    m=copy.deepcopy(self.land)
    if blocker=='collision':m['collision'][17]=m['collision'][13]=1
    elif blocker=='object':m['objects']=[{'id':1,'graphics':1,'x':2,'y':3},{'id':2,'graphics':1,'x':3,'y':2}]
    elif blocker=='elevation':m['elevation'][12]=4
    else:m['behavior'][17]=m['behavior'][13]=19
    self.c.maps['kanto_0_0']=m;self.assertFalse(self.context()['available'])
   self.c.maps['kanto_0_0']=self.land
 def test_reordering_retains_active_partner_and_replacement_requires_water(self):
  out=surf.launch(self.c,self.state,self.w.walkable);other={'uid':'second','species':'dual','hp':3};out['creatures'].append(other);out['party'].insert(0,'second');surf.reconcile(self.c,out,self.w.walkable);self.assertEqual(out['surfPokemon']['uid'],'water')
  out['party'].remove('water');surf.reconcile(self.c,out,self.w.walkable);self.assertEqual(out['surfPokemon']['uid'],'second')
  out['party']=['fire']
  with self.assertRaisesRegex(RequestError,'Keep a Water'):surf.reconcile(self.c,out,self.w.walkable)
 def test_land_reconcile_clears_surf_metadata_without_moving_player(self):
  out=surf.launch(self.c,self.state,self.w.walkable);out.update(x=2,y=2);surf.reconcile(self.c,out,self.w.walkable);self.assertFalse(out['surf']);self.assertNotIn('surfPokemon',out);self.assertNotIn('surfAnchor',out);self.assertEqual(out['x'],2)
 def test_legacy_unlicensed_water_state_recovers_to_valid_saved_shore(self):
  out=surf.launch(self.c,self.state,self.w.walkable);out['adventure']['badges']=[];surf.reconcile(self.c,out,self.w.walkable,recover=True);self.assertEqual((out['x'],out['y']),(2,2));self.assertFalse(out['surf'])
 def test_legacy_missing_anchor_uses_nearest_reachable_land(self):
  out=surf.launch(self.c,self.state,self.w.walkable);out.pop('surfAnchor');out['party']=['fire'];surf.reconcile(self.c,out,self.w.walkable,recover=True);self.assertFalse(surf.on_water(self.c,out));self.assertFalse(out['surf'])
 def test_valid_saved_surf_is_preserved_and_metadata_refreshed(self):
  out=surf.launch(self.c,self.state,self.w.walkable);out['surfPokemon'].update(name='spoofed',species='fire');surf.reconcile(self.c,out,self.w.walkable,recover=True);self.assertTrue(out['surf']);self.assertEqual(out['surfPokemon']['name'],'Water');self.assertEqual((out['x'],out['y']),(2,3))
 def test_water_movement_cannot_climb_to_another_water_elevation(self):
  self.land['elevation'][18]=3
  self.assertFalse(self.w.walkable(self.land,3,3,True,from_elevation=1,state=self.state,from_behavior=21))

if __name__=='__main__':unittest.main()
