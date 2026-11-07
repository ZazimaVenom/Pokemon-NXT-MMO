"""Server-owned FireRed field items and location-bound services.

All mutations use detached snapshots. World commits them and starts encounters;
clients never choose encounter species, hidden-item identities, or door flags.
"""
from __future__ import annotations
import copy
from .security import require, integer
from .encounters import WATER, encounter_area, select_encounter
from .portals import return_stack

HANDLED_EFFECTS = frozenset(('bicycle','itemfinder','fishing','encounterflute','fossil','coincase','story','case','journal','vsseeker'))
DIRECTIONS = {'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0)}
FOSSIL_LAB = 'kanto_12_4'

def _catalog(content):
    return content.data.get('kantoFieldServices',{})

def _field(state):
    return state.setdefault('kantoField',{})

def _flags(state):
    return state.setdefault('adventure',{}).setdefault('kantoFlags',[])

def _flag(state,flag):
    flags=_flags(state)
    if flag not in flags: flags.append(flag);flags.sort()

def _item_key(content, source_id):
    return next((k for k,v in content.items.items() if v.get('source')=='kanto' and v.get('sourceId')==source_id),None)

def _owned(content,state,key):
    item=content.items.get(key)
    require(item is not None and item.get('source')=='kanto','Choose a FireRed item.')
    require(state.get('items',{}).get(key,0)>0,'You have none of that item.')
    return item

def _has_source(state,content,source_id):
    key=_item_key(content,source_id)
    return bool(key and state.get('items',{}).get(key,0)>0)

def _near_npc(content,state,map_id,npc_id):
    if state.get('map')!=map_id:return False
    obj=next((o for o in content.maps[map_id].get('objects',[]) if o['id']==npc_id),None)
    return bool(obj and max(abs(state['x']-obj['x']),abs(state['y']-obj['y']))<=2)

def facing(state):
    dx,dy=DIRECTIONS.get(state.get('direction','down'),(0,1))
    return state['x']+dx,state['y']+dy

def bicycle_allowed(content,state):
    m=content.maps[state['map']]
    return bool(m.get('bicycleAllowed',False) and not state.get('surf'))

def mark_map_transition(candidate,old_map,content):
    """Apply after candidate.map changes, before the same durable world commit."""
    if not bicycle_allowed(content,candidate):candidate['bicycle']=False
    pending=candidate.get('kantoField',{}).get('fossil')
    if pending and old_map==FOSSIL_LAB and candidate['map']!=old_map:pending['ready']=True
    if candidate['map']!=old_map:candidate.get('kantoField',{}).pop('vsSeekerReady',None)
    return candidate

def after_step(state):
    """Call for successful tile movement, never wall bumps or rejected input."""
    if state.get('items',{}).get('fr_vsseeker',0)<=0:return
    f=_field(state);f['vsSeekerCharge']=min(100,max(0,int(f.get('vsSeekerCharge',0)))+1)

def rematch_ready(state,trainer):
    return trainer['id'] in state.get('kantoField',{}).get('vsSeekerReady',[])

def consume_rematch(state,trainer):
    ready=state.get('kantoField',{}).get('vsSeekerReady',[])
    if trainer['id'] in ready:ready.remove(trainer['id'])

def fishing_slots(content,state,rod):
    require(rod in ('old','good','super'),'Choose a fishing rod.')
    m=content.maps[state['map']];x,y=facing(state)
    require(0<=x<m['width'] and 0<=y<m['height'] and m['behavior'][y*m['width']+x] in WATER,
            'Stand at the water’s edge or Surf, then face the water before fishing.')
    require(not state.get('bicycle'),'Get off your Bicycle before fishing.')
    area=encounter_area(m,x,y);tables=area.get('encounters',{})
    slots=tables.get('fishing_'+rod)
    if slots is None:
        rows=tables.get('fishing',[]);start,end={'old':(0,2),'good':(2,5),'super':(5,10)}[rod]
        slots=rows[start:end] if len(rows)==10 else []
    require(bool(slots),'There are no fishing encounters in this water.')
    return slots

def _hidden_remaining(content,state):
    rom=content.data.get('adventureRom',{});hidden=rom.get('hiddenItemPickups',{})
    rows=hidden.values() if isinstance(hidden,dict) else hidden
    all_rows=list(rom.get('itemPickups',{}).values())+list(rows)
    claimed=set(state.get('adventure',{}).get('itemPickups',[]))
    flags={p['sourceFlag'] for p in all_rows if p['id'] in claimed and p.get('sourceFlag') and str(p.get('map','')).startswith('kanto_')}
    return [p for p in all_rows if p.get('map')==state['map'] and p.get('id') in hidden
            and p['id'] not in claimed and (not p.get('sourceFlag') or p['sourceFlag'] not in flags)]

def itemfinder(content,state):
    """Native local search window; underfoot specials are collected by World."""
    nearby=[]
    for p in _hidden_remaining(content,state):
        dx,dy=p['x']-state['x'],p['y']-state['y']
        if abs(dx)<=7 and abs(dy)<=5:nearby.append((abs(dx)+abs(dy),p['id'],dx,dy,p))
    if not nearby:return 'The Itemfinder is silent. No hidden item was detected nearby.',{'itemfinder':{'found':False}}
    _,_,dx,dy,p=min(nearby)
    result={'found':True,'x':p['x'],'y':p['y'],'direction':'underfoot' if dx==dy==0 else ('right' if dx>0 else 'left') if abs(dx)>abs(dy) else ('down' if dy>0 else 'up')}
    if dx==dy==0:return 'The Itemfinder is responding right under your feet!',{'itemfinder':result,'hiddenPickup':p['id']}
    # Underfoot-only FR rewards deliberately do not ping at a distance.
    if p.get('underfootOnly') or p.get('requiresItemfinder'):
        ordinary=[q for q in nearby if not q[-1].get('underfootOnly') and not q[-1].get('requiresItemfinder')]
        if not ordinary:return 'The Itemfinder is silent. No hidden item was detected nearby.',{'itemfinder':{'found':False}}
        _,_,dx,dy,p=min(ordinary);result.update(x=p['x'],y=p['y'],direction=('right' if dx>0 else 'left') if abs(dx)>abs(dy) else ('down' if dy>0 else 'up'))
    return 'The Itemfinder is responding! A hidden item is nearby, to the '+result['direction']+'.',{'itemfinder':result}

def _doors(content,map_id):
    return [d for d in _catalog(content).get('doors',[]) if d['map']==map_id]

def field_tiles(content,state):
    """Select only current native tile variants; artwork lives on the map."""
    rows={};opened=set(state.get('kantoField',{}).get('doors',[]));mid=state['map']
    def add(tiles):
        for t in tiles:rows[(t['x'],t['y'])]={k:t[k] for k in ('x','y','metatile')}
    for door in _doors(content,mid):
        if door['id'] in opened:add(door.get('openTiles',[]))
    trainers=content.data.get('adventureRom',{}).get('trainers',{});defeated=state.get('adventure',{}).get('trainers',{})
    completed={t['trainerId'] for tid,t in trainers.items() if tid in defeated and t.get('source')=='kanto'}
    for gate in _catalog(content).get('trainerDoors',[]):
        if gate['map']==mid and set(gate['requiredTrainerIds'])<=completed:add(gate.get('openTiles',[]))
    for switch in _catalog(content).get('mansionSwitches',[]):
        if switch['map']==mid:add(switch['on' if switch['sourceFlag'] in state.get('adventure',{}).get('kantoFlags',[]) else 'off'])
    return list(rows.values())

def collision_override(content,state,m,x,y):
    return collision_state(content,state,m,x,y) is True

def collision_state(content,state,m,x,y):
    """None retains base collision; False actively closes a native switched door."""
    if not state:return None
    opened=set(state.get('kantoField',{}).get('doors',[]))
    for door in _doors(content,m['id']):
        if door['id'] not in opened:continue
        for tile in door.get('openTiles',[]):
            if tile['x']==x and tile['y']==y:return tile['collision']==0
    trainers=content.data.get('adventureRom',{}).get('trainers',{})
    defeated=state.get('adventure',{}).get('trainers',{})
    for gate in _catalog(content).get('trainerDoors',[]):
        if gate['map']!=m['id'] or [x,y] not in gate['tiles']:continue
        ids={t['trainerId'] for tid,t in trainers.items() if tid in defeated and t.get('source')=='kanto'}
        if set(gate['requiredTrainerIds'])<=ids:return True
    for switch in _catalog(content).get('mansionSwitches',[]):
        if switch['map']!=m['id']:continue
        flag_on=switch['sourceFlag'] in state.get('adventure',{}).get('kantoFlags',[])
        for tile in switch['on' if flag_on else 'off']:
            if tile['x']==x and tile['y']==y:return tile['collision']==0
    return None

def interact(content,state):
    """Resolve a faced native statue switch, or leave interaction to World."""
    point=list(facing(state))
    switch=next((r for r in _catalog(content).get('mansionSwitches',[]) if r['map']==state['map'] and point in r['switches']),None)
    if not switch:return None
    candidate=copy.deepcopy(state);flags=_flags(candidate);flag=switch['sourceFlag']
    if flag in flags:flags.remove(flag)
    else:_flag(candidate,flag)
    return candidate,'You pressed the secret switch. Doors in the Pokémon Mansion changed!',{'fieldChanged':True}

def portal_block(state,source_map,target_map):
    """Original item checks at native entrances; never trap a returning player."""
    required=None
    if source_map=='kanto_3_8' and target_map=='kanto_12_0':required=('fr_secretkey','The Cinnabar Gym is locked. Find the Secret Key in the Pokémon Mansion.')
    elif source_map=='kanto_3_5' and target_map=='kanto_1_4':required=('fr_ssticket','Show the S.S. Ticket to board the S.S. Anne.')
    elif target_map=='kanto_1_46' and source_map in ('kanto_1_42','kanto_1_43','kanto_1_44','kanto_1_45'):required=('fr_liftkey','The Rocket Hideout lift needs the Lift Key.')
    if required and state.get('items',{}).get(required[0],0)<=0:return required[1]
    if target_map=='kanto_3_10' and source_map in ('kanto_17_1','kanto_18_0','kanto_19_0','kanto_20_0'):
        if state.get('adventure',{}).get('kantoVars',{}).get('16482',0)<1:return 'The guard is thirsty. Bring Tea from Celadon Mansion and give it to a gate guard.'
    return None

def fossil_collect(content,state,*,owner='Trainer',max_owned=1000):
    require(_near_npc(content,state,FOSSIL_LAB,2),'Visit the fossil scientist in the last room of Cinnabar’s Pokémon Lab.')
    pending=state.get('kantoField',{}).get('fossil')
    require(pending,'The scientist is not reviving a fossil for you.')
    require(pending.get('ready'),'The scientist is still working. Leave this room and come back.')
    require(len(state['creatures'])<max_owned,'Make room in Pokémon storage before collecting your revived Pokémon.')
    candidate=copy.deepcopy(state);pending=_field(candidate).pop('fossil')
    mon=content.new_mon(pending['species'],5,owner)
    candidate['creatures'].append(mon)
    if len(candidate['party'])<6:candidate['party'].append(mon['uid'])
    for field in ('seen','caught'):
        values=candidate.setdefault('adventure',{}).setdefault(field,[])
        if mon['species'] not in values:values.append(mon['species']);values.sort()
    return candidate,'The fossil was revived into '+content.species[mon['species']]['name']+' at Lv. 5!',{'receivedPokemon':mon['uid']}

def context(content,state):
    pending=state.get('kantoField',{}).get('fossil')
    catalog=_catalog(content)
    prizes=[]
    for prize in catalog.get('coinPrizes',[]):
        row=copy.deepcopy(prize);pokemon=row['kind']=='pokemon'
        row['reward']='fr_'+str(row['sourceId']) if pokemon else _item_key(content,row['sourceId'])
        definition=(content.species if pokemon else content.items).get(row['reward'],{})
        row['name']=definition.get('name',row['reward']);row['available']=_near_npc(content,state,'kanto_10_15',row['npc'])
        prizes.append(row)
    elevator=next((r for r in catalog.get('elevators',[]) if r['map']==state['map']),None)
    powder=[]
    for prize in catalog.get('powderPrizes',[]):
        reward=_item_key(content,prize['sourceId'])
        if reward:powder.append({'reward':reward,'name':content.items[reward]['name'],'powder':prize['powder']})
    return {'fossilLab':_near_npc(content,state,FOSSIL_LAB,2),'fossilPending':copy.deepcopy(pending),
            'coinCounter':_near_npc(content,state,'kanto_10_14',2),
            'prizeCounter':state.get('map')=='kanto_10_15' and any(_near_npc(content,state,'kanto_10_15',n) for n in (3,4,5)),
            'coinPrizes':prizes,'vsSeekerCharge':state.get('kantoField',{}).get('vsSeekerCharge',0),
            'vsSeekerReady':list(state.get('kantoField',{}).get('vsSeekerReady',[])),
            'elevatorDestinations':[{'id':d['id'],'label':d['label']} for d in elevator['destinations']] if elevator else [],
            'fieldMap':state['map'],'fieldTiles':field_tiles(content,state),
            'powderMerchant':_near_npc(content,state,'kanto_7_9',1),'berryPowder':state.get('berryPowder',0),'powderPrizes':powder}

def service(content,state,key,data,*,owner='Trainer',max_owned=1000):
    item=_owned(content,state,key)
    if item['sourceId']==372:
        require(data.get('action')=='medicine','Choose a Berry Powder medicine exchange.')
        require(_near_npc(content,state,'kanto_7_9',1),'Visit the Berry Powder man in his Cerulean City house.')
        reward=data.get('reward');row=next((r for r in _catalog(content).get('powderPrizes',[]) if _item_key(content,r['sourceId'])==reward),None)
        require(row is not None,'Choose a displayed Berry Powder medicine.')
        require(state.get('berryPowder',0)>=row['powder'],'You do not have enough Berry Powder. Berry Crush is not available yet.')
        require(state['items'].get(reward,0)<999,'That item stack is full.')
        candidate=copy.deepcopy(state);candidate['berryPowder']=candidate.get('berryPowder',0)-row['powder'];candidate['items'][reward]=candidate['items'].get(reward,0)+1
        return candidate,'Exchanged Berry Powder for '+content.items[reward]['name']+'.',{}
    require(item['sourceId']==260,'Choose the Coin Case or Powder Jar.')
    candidate=copy.deepcopy(state);action=data.get('action')
    if action=='buycoins':
        require(_near_npc(content,state,'kanto_10_14',2),'Visit the coin seller at Celadon Game Corner’s counter.')
        count=integer(data.get('quantity'),1,500,'Coin quantity');require(count in (50,500),'Choose 50 or 500 coins.')
        require(candidate.get('coins',0)+count<=9999,'The Coin Case holds at most 9,999 coins.')
        require(candidate['money']>=count*20,'You do not have enough money.')
        candidate['money']-=count*20;candidate['coins']=candidate.get('coins',0)+count
        return candidate,f'Bought {count} coins.',{}
    require(action=='prize','Choose a Coin Case exchange action.')
    reward=data.get('reward');kind=data.get('kind','item')
    row=next((p for p in _catalog(content).get('coinPrizes',[]) if p['kind']==kind and (('fr_'+str(p['sourceId'])) if kind=='pokemon' else _item_key(content,p['sourceId']))==reward),None)
    require(row is not None,'Choose a displayed Celadon prize.')
    require(_near_npc(content,state,'kanto_10_15',row['npc']),'Visit the matching counter in Celadon’s prize exchange.')
    require(candidate.get('coins',0)>=row['coins'],'You do not have enough coins.')
    if kind=='pokemon':
        require(len(candidate['creatures'])<max_owned,'Make room in Pokémon storage first.')
        mon=content.new_mon(reward,row['level'],owner);candidate['creatures'].append(mon)
        if len(candidate['party'])<6:candidate['party'].append(mon['uid'])
        for field in ('seen','caught'):
            values=candidate.setdefault('adventure',{}).setdefault(field,[])
            if reward not in values:values.append(reward);values.sort()
        name=content.species[reward]['name']
    else:
        require(candidate['items'].get(reward,0)<999,'That item stack is full.')
        candidate['items'][reward]=candidate['items'].get(reward,0)+1;name=content.items[reward]['name']
    candidate['coins']-=row['coins']
    return candidate,'Exchanged coins for '+name+'.',{}

def use(content,state,key,data,*,owner='Trainer',max_owned=1000):
    item=_owned(content,state,key);rule=item.get('mechanics',{});effect=rule.get('effect');sid=item['sourceId']
    require(str(state.get('map','')).startswith('kanto_'),'Use this FireRed field item in Kanto.')
    candidate=copy.deepcopy(state);extra={}
    if effect=='bicycle':
        if not candidate.get('bicycle'):require(bicycle_allowed(content,candidate),'You cannot ride a Bicycle here.')
        candidate['bicycle']=not candidate.get('bicycle',False)
        message='You got on the Bicycle.' if candidate['bicycle'] else 'You got off the Bicycle.'
    elif effect=='fishing':
        slots=fishing_slots(content,state,rule.get('rod'))
        require(any(m['hp']>0 for m in state['creatures'] if m['uid'] in state['party']),'Your party needs healing before fishing.')
        species,level=select_encounter(slots,content.rng)
        candidate['bicycle']=False;extra['encounter']={'species':species,'level':level};message='A Pokémon’s on the hook!'
    elif effect=='itemfinder':message,extra=itemfinder(content,state)
    elif effect=='encounterflute':
        rate=rule.get('encounterRate');require(rate in ([1,2],[3,2]),'This flute’s encounter effect is unavailable.')
        _field(candidate)['encounterRate']=list(rate)
        message=item['name']+' played. Wild Pokémon will appear '+('less' if rate[0]<rate[1] else 'more')+' often.'
    elif effect=='fossil':
        require(_near_npc(content,state,FOSSIL_LAB,2),'Bring this fossil to the scientist in the last room of Cinnabar’s Pokémon Lab.')
        require(not state.get('kantoField',{}).get('fossil'),'Collect your previous revived Pokémon before handing over another fossil.')
        recipe=next((p for p in _catalog(content).get('fossils',[]) if p['sourceId']==sid),None)
        require(recipe,'The Cinnabar scientist revives Helix Fossils, Dome Fossils, and Old Amber.')
        candidate['items'][key]-=1;_field(candidate)['fossil']={'item':key,'species':recipe['species'],'ready':False}
        message='The scientist accepted your '+item['name']+'. Leave this room, then return to collect your revived Pokémon.'
    elif sid in (349,353,369,374):
        handover=next((h for h in _catalog(content).get('handovers',[]) if h['sourceId']==sid and _near_npc(content,state,h['map'],h['npc'])),None)
        locations={349:'Professor Oak in his Pallet Town lab',353:'the Safari Zone Warden in his Fuchsia City house',369:'a Saffron gate guard on Route 5, 6, 7, or 8',374:'Celio in One Island’s Pokémon Center'}
        require(handover is not None,'Bring '+item['name']+' to '+locations[sid]+'.')
        if handover.get('requiresSourceId'):require(_has_source(state,content,handover['requiresSourceId']),'Complete Celio’s Ruby delivery first.')
        if sid==349:
            balls=_item_key(content,4);require(balls is not None,'Poké Balls are unavailable.')
            require(candidate['items'].get(balls,0)+5<=999,'Make room for five Poké Balls before delivering the parcel.')
            candidate['items'][balls]=candidate['items'].get(balls,0)+5
        candidate['items'][key]-=1
        for flag in handover.get('flags',[]):_flag(candidate,flag)
        candidate.setdefault('adventure',{}).setdefault('kantoVars',{}).update(handover.get('variables',{}))
        message={349:'Delivered Oak’s Parcel. Professor Oak registered your Pokédex and gave you five Poké Balls.',
                 353:'Returned the Gold Teeth. The Warden can speak clearly again and thanks you for finding them!',
                 369:'The guard accepted the Tea and shared it with the other guards. All four Saffron gates are now open.',
                 374:'Celio accepted the Sapphire and completed the Network Machine repairs.'}[sid]
    elif sid==355:
        point=list(facing(state));doors=_doors(content,state['map']);door=next((d for d in doors if point in d['tiles']),None)
        require(door,'Face a locked door in Silph Co. to use the Card Key.')
        opened=_field(candidate).setdefault('doors',[])
        require(door['id'] not in opened,'This door is already open.')
        opened.append(door['id']);opened.sort();_flag(candidate,door['sourceFlag']);message='Bingo! The Card Key opened the door.'
    elif sid==352:
        require(_near_npc(content,state,'kanto_7_6',1),'Show the Bike Voucher to the clerk in Cerulean’s Bike Shop.')
        bicycle=_item_key(content,360);require(bicycle is not None,'The Bicycle is unavailable.')
        require(candidate['items'].get(bicycle,0)==0,'You already own a Bicycle.')
        candidate['items'][key]-=1;candidate['items'][bicycle]=1;message='Exchanged the Bike Voucher for a Bicycle!'
    elif sid==260:message=f'The Coin Case contains {candidate.get("coins",0):,} coins. Buy coins at Celadon Game Corner and exchange them next door.'
    elif effect=='vsseeker':
        require(content.maps[state['map']].get('mapType') in (1,2,3),'The VS Seeker only works outdoors.')
        charge=state.get('kantoField',{}).get('vsSeekerCharge',0)
        require(charge>=100,f'The VS Seeker needs {100-charge} more steps to recharge.')
        rows=content.data.get('adventureRom',{}).get('trainers',{})
        ready=[t['id'] for t in rows.values() if t.get('map')==state['map'] and t['id'] in state.get('adventure',{}).get('trainers',{})
               and abs(t['x']-state['x'])<=7 and abs(t['y']-state['y'])<=5]
        _field(candidate).update(vsSeekerCharge=0,vsSeekerReady=sorted(ready))
        message=(f'{len(ready)} nearby trainer'+(' is' if len(ready)==1 else 's are')+' ready for a rematch. Speak to them before leaving this map.' if ready else 'No nearby defeated trainer responded. Walk 100 steps to recharge.')
        extra['rematches']=ready
    elif sid==356 and state['map']=='kanto_1_46':
        elevator=next((r for r in _catalog(content).get('elevators',[]) if r['map']==state['map']),None)
        require(elevator is not None,'This elevator’s destinations are unavailable.')
        choice=next((d for d in elevator['destinations'] if d['id']==data.get('destination')),None)
        require(choice is not None,'Choose B1F, B2F, or B4F from the lift’s destination list in your Bag.')
        target=content.maps[choice['id']];x,y=choice['arrival']
        require(0<=x<target['width'] and 0<=y<target['height'] and target['collision'][y*target['width']+x]==0,'This elevator exit is unavailable.')
        stack=[r for r in return_stack(content,candidate) if r['inside']!=state['map']]
        stack.append({'inside':state['map'],'outside':choice['id'],'x':x,'y':y})
        candidate['warpReturns']=stack[-32:];message='The lift arrived at '+choice['label']+'. Step through the door to leave.'
    elif sid in (265,351,356):
        message={265:'The S.S. Ticket admits you to the S.S. Anne at Vermilion’s harbor.',351:'The Secret Key unlocks the Cinnabar Gym when you enter.',356:'The Lift Key enables the Rocket Hideout elevator.'}[sid]
    elif effect in ('case','journal'):
        message={361:'Your Town Map is available in the Atlas.',363:'Your Adventure Journal records the people and places you have discovered.',364:'Open the TMs pocket in your Bag to teach a compatible move.',365:'Open the Berries pocket in your Bag to use or give a Berry.',372:f'The Powder Jar contains {candidate.get("berryPowder",0):,} units of Berry Powder. Berry Crush is not available in this MMO.'}.get(sid,item.get('description',item['name']))
    else:
        require(False,item['name']+' is used through its story interaction. This location has no supported use for it; nothing was consumed.')
    return candidate,message,extra
