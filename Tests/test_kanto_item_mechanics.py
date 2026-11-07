"""FireRed mechanics regressions against the published native item tables."""
import copy,random,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
from nxt.content import Content
from nxt.combat import Battle
from nxt.items import replace_held
from nxt.security import RequestError

class KantoItemMechanics(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=Content(ROOT/'Server/data/world.json');cls.i=cls.c.item_system
 def setUp(self):
  old=self.c.rng;self.c.rng=random.Random(62944);self.addCleanup(setattr,self.c,'rng',old)
 def mon(self,species='fr_4',level=40):
  m=self.c.new_mon(species,level);replace_held(m,{'heldItemId':0});m['moves']=[{'id':33,'pp':2,'ppUps':0}];return m
 def state(self,m=None):
  m=m or self.mon();return {'creatures':[m],'party':[m['uid']],'items':{k:5 for k in self.c.items},'money':20000,'repelSteps':0,'heldReserve':{}}
 def held(self,m,key):
  value=self.c.items[key];replace_held(m,{'heldItemId':value['sourceId'],'heldItemSource':value['source'],'heldItemKey':key});return m
 def battle(self,m=None,foe=None,kind='wild',terrain='plain'):
  return Battle(self.c,kind,[1,None],['Trainer','Wild'],[[m or self.mon()],[foe or self.mon('fr_7')]], [{k:5 for k in self.c.items},{}],terrain=terrain)
 def test_native_namespace_preserves_sigma_stacks_and_effects(self):
  self.assertNotEqual(self.c.items['fr_potion']['sourceId'],self.c.items['upgrade']['sourceId'])
  native=self.held(self.mon(),'fr_berryjuice');sigma=self.held(self.mon(),'upgrade')
  self.assertEqual(self.i.held_code(native),44);self.assertEqual(self.i.held_code(sigma),0)
  state=self.state(native);back=self.i.equip(state,{'uid':native['uid']},take=True)
  self.assertEqual(back['items']['fr_berryjuice'],6);self.assertEqual(back['items']['upgrade'],5)
 def test_native_all_medicines_apply_exact_heal_or_cure_and_do_not_mutate_inputs(self):
  for key,item in self.c.items.items():
   r=item.get('mechanics',{})
   if item.get('source')!='kanto' or r.get('effect')!='medicine':continue
   with self.subTest(item=key):
    m=self.mon();m['hp']=1;m['status']='poison';vol={}
    cures=r.get('cure',[])
    if cures:m['status']='poison' if cures[0]=='all' else cures[0]
    if 'confusion' in cures:m['status']='';vol['confusionTurns']=4
    if 'infatuation' in cures:m['status']='';vol['attractSource']='foe'
    before=copy.deepcopy(m);out,newvol=self.i.apply_mon(key,m,{},battle=True,volatile=vol)
    self.assertEqual(m,before)
    if r.get('heal'):self.assertEqual(out['hp'],min(self.c.stats(m)[0],1+r['heal']))
    if cures:self.assertEqual(out['status'],'');self.assertFalse(newvol)
 def test_native_reusable_flutes_clear_volatile_condition_only(self):
  for key,field in [('fr_redflute','attractSource'),('fr_yellowflute','confusionTurns')]:
   b=self.battle();b.vol(b.mon(0))[field]=3
   self.i.battle_action(b,0,key,{});self.assertNotIn(field,b.vol(b.mon(0)));self.assertEqual(b.items[0][key],5)
   with self.assertRaises(RequestError):self.i.battle_action(b,0,key,{})
 def test_native_no_effect_and_stored_targets_never_spend(self):
  state=self.state();m=state['creatures'][0];before=copy.deepcopy(state)
  with self.assertRaises(RequestError):self.i.field_use(state,'fr_potion',{'uid':m['uid']})
  self.assertEqual(state,before);stored=self.mon();stored['hp']=1;state['creatures'].append(stored)
  with self.assertRaisesRegex(RequestError,'party'):self.i.field_use(state,'fr_potion',{'uid':stored['uid']})
 def test_native_tm01_uses_focus_punch_and_consumes_only_compatible_success(self):
  self.assertEqual(self.i.rule('fr_tm01')['move'],264);self.assertNotEqual(self.i.rule('tm01')['move'],264)
  key=next(k for k,s in self.c.species.items() if 'fr_tm01' in s['machines'])
  state=self.state(self.mon(key));uid=state['party'][0];out=self.i.field_use(state,'fr_tm01',{'uid':uid,'slot':0,'expectedMove':33})
  self.assertEqual(out['creatures'][0]['moves'][0]['id'],264);self.assertEqual(out['items']['fr_tm01'],4);self.assertEqual(out['items']['tm01'],5)
  with self.assertRaises(RequestError):self.i.field_use(out,'fr_tm01',{'uid':uid,'slot':0})
 def test_native_tm_preserves_hm_move_and_stale_choice(self):
  key=next(k for k,s in self.c.species.items() if 'fr_tm01' in s['machines']);state=self.state(self.mon(key));m=state['creatures'][0];m['moves'][0]={'id':15,'pp':20}
  with self.assertRaisesRegex(RequestError,'HM move'):self.i.field_use(state,'fr_tm01',{'uid':m['uid'],'slot':0})
  m['moves'][0]={'id':33,'pp':35}
  with self.assertRaisesRegex(RequestError,'changed'):self.i.field_use(state,'fr_tm01',{'uid':m['uid'],'slot':0,'expectedMove':45})
 def test_native_stone_evolutions_do_not_gain_sigma_edges(self):
  state=self.state(self.mon('fr_133'));uid=state['party'][0]
  with self.assertRaises(RequestError):self.i.field_use(state,'fr_leafstone',{'uid':uid,'target':'sg_523'})
  out=self.i.field_use(state,'fr_waterstone',{'uid':uid,'target':'fr_134'})
  self.assertEqual(out['creatures'][0]['species'],'fr_134');self.assertEqual(out['items']['fr_waterstone'],4);self.assertEqual(out['items']['waterstone'],5)
 def test_native_held_trade_evolution_requires_trade_and_consumes_item(self):
  state=self.state(self.held(self.mon('fr_61'),'fr_kingsrock'));m=state['creatures'][0]
  self.assertFalse(any(o['target']=='fr_186' and o['method']=='tradeItem' for o in self.c.growth.options(m)))
  self.c.growth.mark_trade(m);out=self.c.growth.evolve(state,m['uid'],'fr_186')
  self.assertEqual(out['creatures'][0]['heldItemId'],0);self.assertEqual(out['creatures'][0]['species'],'fr_186')
  self.assertEqual(state['creatures'][0]['heldItemKey'],'fr_kingsrock')
 def test_everstone_prevents_level_and_trade_evolution(self):
  m=self.held(self.mon('fr_4',16),'fr_everstone');self.assertFalse(any(o['method']=='level' for o in self.c.growth.options(m)))
  m=self.held(self.mon('fr_64'),'fr_everstone');self.c.growth.mark_trade(m);self.assertFalse(m['pendingEvolution'])
 def test_native_flavored_berries_heal_at_half_hp_and_apply_disliked_flavor(self):
  names=['figy','wiki','mago','aguav','iapapa'];drops=[0,3,2,4,1]
  for name,drop in zip(names,drops):
   with self.subTest(berry=name):
    b=self.battle();m=b.mon(0);self.held(m,'fr_'+name+'berry');m['nature']=(1 if drop==0 else 0)*5+drop;m['hp']=self.c.stats(m)[0]//2;before=m['hp']
    b._consume_item_if_needed(0);self.assertEqual(m['heldItemId'],0);self.assertEqual(m['hp'],before+max(1,self.c.stats(m)[0]//8));self.assertGreater(b.vol(m).get('confusionTurns',0),0)
 def test_pinch_berries_do_not_consume_when_effect_capped(self):
  b=self.battle();m=b.mon(0);m['hp']=1;self.held(m,'fr_liechiberry');b.tiers(m)[1]=6;b._consume_item_if_needed(0);self.assertEqual(m['heldItemKey'],'fr_liechiberry')
  b.tiers(m)[1]=5;b._consume_item_if_needed(0);self.assertEqual(m['heldItemId'],0);self.assertEqual(b.tiers(m)[1],6)
 def test_lansat_does_not_boost_crit_before_activation(self):
  b=self.battle();self.held(b.mon(0),'fr_lansatberry');move=self.c.moves['33']
  with patch.object(self.c.rng,'randrange',return_value=1) as rng:b._critical(0,move,move['effect']);self.assertEqual(rng.call_args.args,(16,))
  b.mon(0)['hp']=1;b._consume_item_if_needed(0)
  with patch.object(self.c.rng,'randrange',return_value=1) as rng:b._critical(0,move,move['effect']);self.assertEqual(rng.call_args.args,(4,))
 def test_exp_share_divides_pool_and_participant_holder_receives_both_shares(self):
  active=self.mon();holder=self.held(self.mon(),'fr_expshare');fainted=self.held(self.mon(),'fr_expshare');fainted['hp']=0
  out={m['uid']:n for m,n in self.i.experience_recipients([active,holder,fainted],[active['uid']],100)}
  self.assertEqual(out,{active['uid']:50,holder['uid']:50})
  out={m['uid']:n for m,n in self.i.experience_recipients([active,holder],[holder['uid']],100)};self.assertEqual(out,{holder['uid']:100})
 def test_amulet_coin_is_remembered_after_holder_switches(self):
  m=self.held(self.mon(),'fr_amuletcoin');b=self.battle(m);self.assertEqual(b.prize_multipliers[0],2)
  replace_held(b.mon(0),{'heldItemId':0});b._record_participant();self.assertEqual(b.prize_multipliers[0],2)
 def test_native_luxury_ball_friendship_bonus_is_not_lost_by_namespacing(self):
  ordinary=self.mon();luxury=copy.deepcopy(ordinary);luxury['captureBall']='fr_luxuryball';self.i.positive_friendship(ordinary);self.i.positive_friendship(luxury);self.assertEqual(luxury['friendship'],ordinary['friendship']+1)
 def test_soothe_bell_rounds_before_adding_luxury_ball_bonus(self):
  m=self.held(self.mon(),'fr_soothebell');m['friendship']=70;m['captureBall']='fr_luxuryball';self.i.positive_friendship(m);self.assertEqual(m['friendship'],78)
 def test_native_escape_doll_ends_wild_battle_but_never_trainer_battle(self):
  b=self.battle();b.vol(b.mon(0))['trappedBy']=b.mon(1)['uid'];self.i.battle_action(b,0,'fr_pokedoll',{});self.assertTrue(b.ended);self.assertIsNone(b.winner);self.assertEqual(b.items[0]['fr_pokedoll'],4)
  b=self.battle(kind='trainer')
  with self.assertRaises(RequestError):b.choose(0,{'action':'item','item':'fr_pokedoll'})
  self.assertEqual(b.items[0]['fr_pokedoll'],5)
 def test_native_mail_survives_give_take_give_and_rejects_control_characters(self):
  state=self.state();uid=state['party'][0];out=self.i.equip(state,{'uid':uid,'item':'fr_orangemail','message':'Meet me in Pallet Town!'});self.assertEqual(out['creatures'][0]['heldMail'],'Meet me in Pallet Town!')
  out=self.i.equip(out,{'uid':uid},take=True);self.assertEqual(out['mailMessages']['fr_orangemail'],['Meet me in Pallet Town!']);out=self.i.equip(out,{'uid':uid,'item':'fr_orangemail'});self.assertEqual(out['creatures'][0]['heldMail'],'Meet me in Pallet Town!')
  with self.assertRaises(RequestError):self.i.equip(state,{'uid':uid,'item':'fr_orangemail','message':'bad\x00mail'})
  self.assertEqual(state['items']['fr_orangemail'],5)
 def test_safari_ball_is_restricted_to_safari_context(self):
  with self.assertRaisesRegex(RequestError,'Safari'):self.battle().choose(0,{'action':'capture','item':'fr_safariball'})
  b=self.battle(terrain='safari');b.choose(0,{'action':'capture','item':'fr_safariball'});self.assertEqual(b.choice[0]['item'],'fr_safariball')

 def test_safari_preserves_party_and_forbids_normal_battle_actions(self):
  m=self.held(self.mon(),'fr_oranberry');m['hp']=1;b=self.battle(m,terrain='safari');before=copy.deepcopy(b.rosters[0])
  for action in ({'action':'attack','slot':0},{'action':'item','item':'fr_potion'},{'action':'capture','item':'fr_masterball'}):
   with self.assertRaises(RequestError):b.choose(0,action)
  with patch.object(self.c.rng,'randrange',return_value=99):b.choose(0,{'action':'bait'})
  with patch.object(self.c.rng,'randrange',return_value=0):b.resolve()
  self.assertEqual(b.rosters[0],before);self.assertEqual(b.experience_events,[])
 def test_safari_bait_catch_floor_and_native_expiration_behavior(self):
  b=self.battle(foe=self.mon('fr_113'),terrain='safari');self.assertEqual(b.safari_catch,2);self.assertEqual(b.safari_escape,9)
  with patch.object(self.c.rng,'randrange',return_value=99):b.choose(0,{'action':'bait'})
  with patch.object(self.c.rng,'randrange',return_value=0):b.resolve()
  self.assertEqual(b.safari_catch,3);self.assertEqual(b.safari_bait,1)
  b.choice={0:{'action':'capture','item':'fr_safariball'},1:{'action':'safari_watch'}}
  with patch.object(self.c.rng,'randrange',return_value=65535):b.resolve()
  self.assertEqual(b.safari_bait,0);self.assertEqual(b.safari_catch,3);self.assertEqual(b.items[0]['fr_safariball'],4)
 def test_safari_rock_expires_back_to_unmodified_species_rate(self):
  b=self.battle(foe=self.mon('fr_113'),terrain='safari')
  with patch.object(self.c.rng,'randrange',return_value=99):b.choose(0,{'action':'rock'})
  with patch.object(self.c.rng,'randrange',return_value=0):b.resolve()
  self.assertEqual(b.safari_catch,4);self.assertEqual(b.safari_rock,1)
  b.choice={0:{'action':'capture','item':'fr_safariball'},1:{'action':'safari_watch'}}
  with patch.object(self.c.rng,'randrange',return_value=65535):b.resolve()
  self.assertEqual(b.safari_catch,2);self.assertEqual(b.safari_rock,0)
 def test_safari_flee_threshold_is_selected_before_throwing_bait(self):
  b=self.battle(foe=self.mon('fr_113'),terrain='safari')
  with patch.object(self.c.rng,'randrange',return_value=44):b.choose(0,{'action':'bait'})
  self.assertEqual(b.choice[1]['action'],'safari_flee')
  with patch.object(self.c.rng,'randrange',return_value=0):b.resolve()
  self.assertTrue(b.ended);self.assertIsNone(b.winner);self.assertTrue(any('fled' in row for row in b.logs))
 def test_pokeflute_wakes_benches_but_respects_soundproof(self):
  b=self.battle();bench=self.mon();bench['status']='sleep';bench['sleep']=3;b.rosters[0].append(bench)
  foe=b.mon(1);foe['status']='sleep';foe['sleep']=3
  with patch.object(b,'ability',side_effect=lambda mon:43 if mon['uid']==foe['uid'] else 0):self.i.battle_action(b,0,'fr_pokeflute',{})
  self.assertEqual(bench['status'],'');self.assertEqual(foe['status'],'sleep');self.assertEqual(b.items[0]['fr_pokeflute'],5)
 def test_everstone_also_blocks_native_stone_use(self):
  state=self.state(self.held(self.mon('fr_25'),'fr_everstone'))
  with self.assertRaises(RequestError):self.i.field_use(state,'fr_thunderstone',{'uid':state['party'][0],'target':'fr_26'})

 def test_native_wild_equal_held_slots_guarantee_item(self):
  key=next(k for k,s in self.c.species.items() if s.get('source')=='kanto' and s.get('heldItems',[0,0])[0]>0 and len(set(s['heldItems']))==1)
  expected=self.c.species[key]['heldItems'][0]
  for roll in (0,44,45,94,95,99):
   with patch.object(self.c.rng,'randrange',side_effect=lambda upper:roll if upper==100 else 0):m=self.c.new_mon(key,30)
   self.assertEqual(m['heldItemId'],expected);self.assertEqual(m['heldItemSource'],'kanto')
 def test_native_wild_held_probability_thresholds_include_empty_slots(self):
  key=next(k for k,s in self.c.species.items() if s.get('source')=='kanto' and s.get('heldItems',[0,0])[0]>0 and s['heldItems'][0]!=s['heldItems'][1])
  common,rare=self.c.species[key]['heldItems']
  for roll,expected in [(0,0),(44,0),(45,common),(94,common),(95,rare),(99,rare)]:
   with patch.object(self.c.rng,'randrange',side_effect=lambda upper:roll if upper==100 else 0):m=self.c.new_mon(key,30)
   self.assertEqual(m['heldItemId'],expected)

if __name__=='__main__':unittest.main()
