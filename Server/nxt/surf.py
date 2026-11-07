"""Badge-licensed shoreline travel with an owned Water-type party partner.

An NXT field licence replaces HM ownership and move teaching. All requirements
are derived from the current map, earned badges and the owner's actual party.
Fainted Water partners remain eligible; battle fitness is a separate concern.
"""
from __future__ import annotations
import collections,copy
from .encounters import WATER
from .field_moves import SURF_REQUIREMENTS,tree_cleared
from . import kanto_obstacles
from .story_events import cleared as story_cleared
from .varieties import variety_key
from .security import require

DIRECTIONS={'up':(0,-1),'right':(1,0),'down':(0,1),'left':(-1,0)}
LEDGES={56,57,58,59}


def region(map_id):return str(map_id).split('_',1)[0].lower()


def badge_allowed(state,map_id=None):
 rule=SURF_REQUIREMENTS.get(region(map_id or state.get('map')))
 return bool(rule and rule['badge'] in state.get('adventure',{}).get('badges',[]))


def partner(content,state):
 owned={m['uid']:m for m in state.get('creatures',[])}
 eligible=[owned[uid] for uid in state.get('party',[]) if uid in owned and 11 in content.species.get(owned[uid]['species'],{}).get('types',[])]
 saved=state.get('surfPokemon',{})
 preferred=saved.get('uid') if isinstance(saved,dict) and state.get('surf') else None
 return next((m for m in eligible if m['uid']==preferred),eligible[0] if eligible else None)


def partner_view(content,mon):
 return {'uid':mon['uid'],'species':mon['species'],'variety':variety_key(mon),'name':content.species[mon['species']]['name']} if mon else None


def public_partner(state):
 value=state.get('surfPokemon')
 if not state.get('surf') or not isinstance(value,dict):return None
 return {key:value[key] for key in ('species','variety','name') if key in value}


def tile(content,state):
 m=content.maps.get(state.get('map'));x,y=state.get('x'),state.get('y')
 if not m or type(x) is not int or type(y) is not int or not 0<=x<m['width'] or not 0<=y<m['height']:return None
 return m['behavior'][y*m['width']+x]


def on_water(content,state):return tile(content,state) in WATER


def object_present(state,map_id,obj):
 if kanto_obstacles.is_cleared(state,map_id,obj) or tree_cleared(state,map_id,obj):return False
 if obj.get('storyEvent') and story_cleared(state,obj['storyEvent']):return False
 if obj.get('itemPickup') in state.get('adventure',{}).get('itemPickups',[]):return False
 return True


def shorelines(content,state,walkable):
 m=content.maps.get(state.get('map'));source=tile(content,state)
 if not m or source is None or source in WATER or source in LEDGES:return []
 x,y=state['x'],state['y'];elevation=m['elevation'][y*m['width']+x]
 # Native Surf boards from the normal land plane into lower water, never
 # from an elevated bridge or cliff (IsPlayerFacingSurfableFishableWater).
 if elevation!=3:return []
 if not walkable(m,x,y,False,state=state):return []
 results=[]
 for direction,(dx,dy) in DIRECTIONS.items():
  tx,ty=x+dx,y+dy
  if not 0<=tx<m['width'] or not 0<=ty<m['height'] or m['behavior'][ty*m['width']+tx] not in WATER or m['elevation'][ty*m['width']+tx]!=1:continue
  if any(w['x']==tx and w['y']==ty for w in m.get('warps',[])):continue
  if walkable(m,tx,ty,True,from_elevation=elevation,state=state,from_behavior=source):results.append({'x':tx,'y':ty,'direction':direction})
 facing=state.get('direction','down')
 return sorted(results,key=lambda point:point['direction']!=facing)


def context(content,state,walkable):
 reg=region(state.get('map'));rule=SURF_REQUIREMENTS.get(reg,{})
 mon=partner(content,state);licensed=badge_allowed(state);water=on_water(content,state)
 active=bool(state.get('surf') and water and licensed and mon)
 points=shorelines(content,state,walkable) if not active and licensed and mon else []
 if active:reason=f"Surfing with {content.species[mon['species']]['name']}. Step onto land to dismount."
 elif not licensed:reason=f"Earn the {rule.get('badgeName','regional Surf badge')} from {rule.get('leader','the Gym Leader')} to Surf here."
 elif mon is None:reason='Add a Water-type Pokémon to your party to Surf.'
 elif not points:reason='Stand beside an open water tile to Surf.'
 else:reason=f"Surf with {content.species[mon['species']]['name']}."
 return {'map':state.get('map'),'active':active,'available':bool(not active and licensed and mon and points),
         'reason':reason,'region':reg,'badge':rule.get('badge'),'badgeName':rule.get('badgeName'),
         'badgeEarned':licensed,'partner':partner_view(content,mon),'shoreline':points[0] if points else None,
         'origin':{'x':state.get('x'),'y':state.get('y'),'direction':state.get('direction','down')}}


def clear(state):
 state['surf']=False
 state.pop('surfPokemon',None);state.pop('surfAnchor',None)


def launch(content,state,walkable):
 require(not state.get('surf'),'You are already Surfing. Step onto land to dismount.')
 ctx=context(content,state,walkable)
 require(ctx['available'],ctx['reason'])
 result=copy.deepcopy(state);point=ctx['shoreline']
 result['surfAnchor']={'map':state['map'],'x':state['x'],'y':state['y'],'direction':state.get('direction','down')}
 result.update(surf=True,bicycle=False,surfPokemon=ctx['partner'],x=point['x'],y=point['y'],direction=point['direction'])
 return result


def _safe_land(content,state,walkable,point):
 if not isinstance(point,dict):return False
 m=content.maps.get(point.get('map'));x,y=point.get('x'),point.get('y')
 if not m or type(x) is not int or type(y) is not int or not 0<=x<m['width'] or not 0<=y<m['height']:return False
 trial={**state,'map':m['id'],'x':x,'y':y,'surf':False}
 return m['behavior'][y*m['width']+x] not in WATER|LEDGES and walkable(m,x,y,False,state=trial)


def _rescue(content,state,walkable):
 # The last shore is an authoritative saved launch location, validated again
 # because map collision or owner-specific obstacles may have changed.
 anchor=state.get('surfAnchor')
 if _safe_land(content,state,walkable,anchor):return dict(anchor)
 m=content.maps[state['map']];start=(state['x'],state['y']);pending=collections.deque([start]);seen={start}
 while pending:
  x,y=pending.popleft();index=y*m['width']+x
  for dx,dy in DIRECTIONS.values():
   tx,ty=x+dx,y+dy
   if (tx,ty) in seen or not 0<=tx<m['width'] or not 0<=ty<m['height']:continue
   seen.add((tx,ty));behavior=m['behavior'][ty*m['width']+tx]
   if behavior in LEDGES:continue
   if not walkable(m,tx,ty,True,from_elevation=m['elevation'][index],state=state,from_behavior=m['behavior'][index]):continue
   if behavior not in WATER:return {'map':m['id'],'x':tx,'y':ty,'direction':'down'}
   pending.append((tx,ty))
 # A corrupt or legacy save can be marooned in an enclosed water component.
 # Falling back to a valid home tile is preferable to granting a licence.
 home=content.maps[content.data['homes'][state['home']]];sx,sy=home['spawn']
 candidates=sorted(((abs(x-sx)+abs(y-sy),x,y) for y in range(home['height']) for x in range(home['width'])))
 for _,x,y in candidates:
  point={'map':home['id'],'x':x,'y':y,'direction':'down'}
  if _safe_land(content,state,walkable,point):return point
 require(False,'Your character needs a safe shoreline recovery; contact the administrator.')


def reconcile(content,state,walkable,*,recover=False):
 """Normalize a detached save or refuse unsafe live party/progression changes."""
 if not on_water(content,state):clear(state);return
 mon=partner(content,state)
 if state.get('surf') and badge_allowed(state) and mon and walkable(content.maps[state['map']],state['x'],state['y'],True,state=state):
  state['surfPokemon']=partner_view(content,mon);state['bicycle']=False;return
 if not recover:
  require(badge_allowed(state),'Earn this region’s Surf badge before entering its water.')
  require(mon is not None,'Keep a Water-type Pokémon in your party while Surfing. Step onto land first.')
  require(False,'Enter the water from a safe shoreline using Surf.')
 point=_rescue(content,state,walkable);clear(state);state.update(point);state['bicycle']=False
 if point['map']!=content.data.get('homes',{}).get(state.get('home')):return
 state['warpReturns']=[]
