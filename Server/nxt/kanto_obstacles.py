"""Owner-scoped Kanto boulder and breakable-rock field licences.

This is the same NXT licence adaptation as Cut: earned native regional badges
replace HM ownership/teaching. No HM item is awarded. Boulders move one square
away from the trainer and reset when the trainer leaves the map. Smashed rocks
remain cleared for that owner, matching NXT's persistent field progress.

Native badge order: pret/pokefirered src/party_menu.c CursorCb_FieldMove and
include/constants/party_menu.h FIELD_MOVE_STRENGTH / FIELD_MOVE_ROCK_SMASH.
"""
from __future__ import annotations
import copy
from .security import require
from .encounters import WATER
from .field_moves import tree_cleared

BOULDER=97
SMASH_ROCK=96
REQUIREMENTS={
 'push':{'graphics':BOULDER,'badge':'kanto_4','badgeName':'Rainbow Badge','move':'Strength'},
 'smash':{'graphics':SMASH_ROCK,'badge':'kanto_6','badgeName':'Marsh Badge','move':'Rock Smash'},
}


def _entry(state,map_id,obj):
 if not state or not str(map_id).startswith('kanto_'):return {}
 maps=state.get('adventure',{}).get('kantoObstacles',{})
 if not isinstance(maps,dict):return {}
 rows=maps.get(map_id,{})
 if not isinstance(rows,dict):return {}
 row=rows.get(str(obj.get('id')),{} )
 return row if isinstance(row,dict) and row.get('graphics')==obj.get('graphics') else {}


def object_position(state,map_id,obj):
 """Return an effective object without ever changing shared map data."""
 result=dict(obj)
 if obj.get('graphics')==BOULDER:
  value=_entry(state,map_id,obj)
  if type(value.get('x')) is int and type(value.get('y')) is int:
   result.update(x=value['x'],y=value['y'])
 return result


def is_cleared(state,map_id,obj):
 return obj.get('graphics')==SMASH_ROCK and _entry(state,map_id,obj).get('cleared') is True


def allowed(state,action):
 rule=REQUIREMENTS.get(action)
 return bool(rule and str(state.get('map','')).startswith('kanto_') and rule['badge'] in state.get('adventure',{}).get('badges',[]))


def reset_on_leave(state,map_id):
 """Mutate a detached transition state; persistent rock clearing survives."""
 maps=state.get('adventure',{}).get('kantoObstacles',{})
 if not isinstance(maps,dict):return
 rows=maps.get(map_id)
 if not isinstance(rows,dict):return
 kept={key:value for key,value in rows.items() if isinstance(value,dict) and value.get('graphics')==SMASH_ROCK and value.get('cleared') is True}
 if kept:maps[map_id]=kept
 else:maps.pop(map_id,None)


def migrate(state,maps):
 """Discard invalid saved obstacle entries; never reinterpret another object."""
 raw=state.setdefault('adventure',{}).get('kantoObstacles',{});clean={}
 if isinstance(raw,dict):
  for map_id,rows in raw.items():
   m=maps.get(map_id)
   if not m or not map_id.startswith('kanto_') or not isinstance(rows,dict):continue
   for obj in m.get('objects',[]):
    row=rows.get(str(obj['id']))
    if not isinstance(row,dict) or row.get('graphics')!=obj.get('graphics'):continue
    value=None
    if obj.get('graphics')==SMASH_ROCK and row.get('cleared') is True:value={'graphics':SMASH_ROCK,'cleared':True}
    elif obj.get('graphics')==BOULDER:
     x,y=row.get('x'),row.get('y')
     if type(x) is int and type(y) is int and 0<=x<m['width'] and 0<=y<m['height']:
      i=y*m['width']+x
      if m['collision'][i]==0 and m['behavior'][i] not in WATER:value={'graphics':BOULDER,'x':x,'y':y}
    if value:clean.setdefault(map_id,{})[str(obj['id'])]=value
 state['adventure']['kantoObstacles']=clean


def _present(state,m,obj):
 if is_cleared(state,m['id'],obj) or tree_cleared(state,m['id'],obj):return False
 if obj.get('itemPickup') in state.get('adventure',{}).get('itemPickups',[]):return False
 if obj.get('storyEvent') in state.get('adventure',{}).get('storyEvents',[]):return False
 return True


def act(content,state,obj,action,walkable):
 """Validate and calculate one push/smash on a detached character snapshot.

    ``walkable`` has the World.walkable signature. World owns locking,
    persistence, publication, multiplayer occupancy and action receipts.
 """
 map_id=state.get('map');m=content.maps.get(map_id)
 require(m is not None and str(map_id).startswith('kanto_'),'These field licences apply in Kanto.')
 rule=REQUIREMENTS.get(action);require(rule is not None,'Choose Push or Rock Smash.')
 original=next((o for o in m.get('objects',[]) if o.get('id')==obj.get('id')),None)
 require(original is not None and original.get('graphics')==rule['graphics'],'That object does not support this field action.')
 require(allowed(state,action),f"Earn the {rule['badgeName']} to use the {rule['move']} field licence.")
 require(not is_cleared(state,map_id,original),'That rock has already been cleared.')
 current=object_position(state,map_id,original);x,y=current['x'],current['y'];px,py=state['x'],state['y']
 require(abs(px-x)+abs(py-y)==1,'Stand directly beside the obstacle.')
 require(not state.get('surf',False),'Step onto dry land before using this field action.')
 candidate=copy.deepcopy(state)
 records=candidate.setdefault('adventure',{}).setdefault('kantoObstacles',{}).setdefault(map_id,{})
 if action=='smash':
  records[str(original['id'])]={'graphics':SMASH_ROCK,'cleared':True}
  return candidate
 dx,dy=x-px,y-py;tx,ty=x+dx,y+dy
 require(0<=tx<m['width'] and 0<=ty<m['height'],'The boulder cannot be pushed beyond the map.')
 index=y*m['width']+x;dest=ty*m['width']+tx
 require(m['behavior'][dest] not in WATER and m['behavior'][dest] not in (56,57,58,59),'The boulder needs solid, level ground.')
 require(not any(w.get('x')==tx and w.get('y')==ty for w in m.get('warps',[])),'A boulder cannot be pushed into a doorway or ladder.')
 for other in m.get('objects',[]):
  if other['id']==original['id'] or not _present(candidate,m,other):continue
  point=object_position(candidate,map_id,other)
  require((point['x'],point['y'])!=(tx,ty),'Another object blocks the boulder.')
 require(walkable(m,tx,ty,False,from_elevation=m['elevation'][index],state=candidate,from_behavior=m['behavior'][index]),'There is not enough room to push the boulder that way.')
 records[str(original['id'])]={'graphics':BOULDER,'x':tx,'y':ty}
 candidate.update(x=x,y=y,direction='right' if dx>0 else 'left' if dx<0 else 'down' if dy>0 else 'up')
 return candidate
