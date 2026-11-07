"""Persisted FireRed Safari Game admission and step/ball budget.

World owns admission proximity, transactions, and native Safari battles.
Session resources cannot leave the reserve or be traded as permanent items.
"""
from __future__ import annotations
import copy
from .security import require

MAPS=frozenset(f'kanto_1_{n}' for n in range(63,72))
GATE='kanto_11_0'
BALL='fr_safariball'

def active(state):
    value=state.get('safari')
    return isinstance(value,dict) and value.get('steps',0)>0 and state.get('items',{}).get(BALL,0)>0

def admit(state):
    require(state.get('map')==GATE,'Visit the Safari Zone reception in Fuchsia City.')
    require(not active(state),'Your Safari Game is already running.')
    require(state.get('money',0)>=500,'The Safari Game admission fee is ₽500.')
    candidate=copy.deepcopy(state);candidate['money']-=500
    candidate['items'][BALL]=30;candidate['safari']={'steps':600}
    candidate.update(map='kanto_1_63',x=26,y=29,surf=False,bicycle=False,warpReturns=[])
    return candidate

def finish(state):
    state.pop('safari',None);state.get('items',{}).pop(BALL,None)
    state.update(map=GATE,x=4,y=4,surf=False,bicycle=False,warpReturns=[])
    return state

def transition(state):
    if state.get('map') not in MAPS:
        state.pop('safari',None);state.get('items',{}).pop(BALL,None)
    return state

def public(state):
    if not state.get('safari'):return None
    return {'steps':max(0,state['safari'].get('steps',0)),'balls':max(0,state.get('items',{}).get(BALL,0))}
