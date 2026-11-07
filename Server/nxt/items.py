"""Authoritative item mechanics on detached character/battle snapshots.

Inventory IDs remain the 0.6.9 persistence contract. Held items additionally
carry a source namespace: Sigma reuses FireRed IDs for unrelated objects.
World owns locking, request receipts, database commits, and publication. This
module has no network or database access and never accepts client-supplied HP,
item effects, prices, species compatibility, RNG results, or stat modifiers.
"""
from __future__ import annotations
import copy
from .security import require, integer

STATS = ('HP','Attack','Defense','Speed','Special Attack','Special Defense')
HELD_FIELDS = ('heldItemId','heldItemSource','heldItemKey','heldMail')
# Existing native FireRed holders remain correctly namespaced. These modifiers
# complement the original engine's berry/Focus Band/Choice Band handling.
KANTO_TYPE_ITEMS = {188:6,199:8,203:4,204:5,205:12,206:17,207:1,208:13,
                    209:11,210:2,211:3,212:15,213:7,214:14,215:10,216:16,217:0}
KANTO_NAMES = {44:'Berry Juice',133:'Cheri Berry',134:'Chesto Berry',135:'Pecha Berry',136:'Rawst Berry',137:'Aspear Berry',138:'Leppa Berry',139:'Oran Berry',140:'Persim Berry',141:'Lum Berry',142:'Sitrus Berry',179:'BrightPowder',180:'White Herb',181:'Macho Brace',182:'Exp. Share',183:'Quick Claw',184:'Soothe Bell',185:'Mental Herb',186:'Choice Band',187:'King’s Rock',188:'SilverPowder',189:'Amulet Coin',190:'Cleanse Tag',191:'Soul Dew',192:'DeepSeaTooth',193:'DeepSeaScale',194:'Smoke Ball',195:'Everstone',196:'Focus Band',197:'Lucky Egg',198:'Scope Lens',199:'Metal Coat',200:'Leftovers',201:'Dragon Scale',202:'Light Ball',203:'Soft Sand',204:'Hard Stone',205:'Miracle Seed',206:'BlackGlasses',207:'Black Belt',208:'Magnet',209:'Mystic Water',210:'Sharp Beak',211:'Poison Barb',212:'NeverMeltIce',213:'Spell Tag',214:'TwistedSpoon',215:'Charcoal',216:'Dragon Fang',217:'Silk Scarf',218:'Up-Grade',219:'Shell Bell',222:'Lucky Punch',223:'Metal Powder',224:'Thick Club',225:'Stick'}


def held_snapshot(mon):
    return {k:copy.deepcopy(mon[k]) for k in HELD_FIELDS if k in mon}


def replace_held(mon, value):
    for k in HELD_FIELDS:mon.pop(k,None)
    mon.update(copy.deepcopy(value));mon.setdefault('heldItemId',0)

def kanto_held_rule(source_id):
    """Gen III held effects use FireRed IDs, never the Sigma item namespace."""
    rule={'legacyCode':source_id}
    if source_id in KANTO_TYPE_ITEMS:rule.update(boostType=KANTO_TYPE_ITEMS[source_id],boost=[11,10])
    if source_id==181:rule.update(stats={'3':[1,2]},evMultiplier=2)
    if source_id==182:rule['expShare']=True
    if source_id==184:rule['friendship']=[3,2]
    if source_id==186:rule['choice']=True
    if source_id==189:rule['prizeMoney']=[2,1]
    if source_id==190:rule['encounterRate']=[2,3]
    if source_id==194:rule['alwaysRun']=True
    if source_id==195:rule['preventEvolution']=True
    if source_id==197:rule['exp']=[3,2]
    if source_id==220:rule.update(boostType=11,boost=[105,100])
    if source_id==221:rule['evasion']=[95,100]
    return rule


def kanto_item_rule(item, machine=None):
    """Authoritative FireRed item roles bound to extracted native records.

    The ROM publisher calls this function after verifying the source table.
    Numeric IDs are the native FireRed contract; prices, names, descriptions,
    machine moves and compatibility remain extracted, rather than guessed.
    """
    sid=int(item['sourceId']);native=item.get('native',{})
    key_item=bool(item.get('keyItem') or item.get('importance'))
    description=' '.join(str(item.get('description','')).split())
    rule=dict(effect='story' if key_item else 'valuable',description=description,
              field=False,battle=False,reusable=key_item,target='none',
              policy='firered-native',sellPrice=0 if key_item else int(item.get('sourcePrice',item.get('price',0)))//2)
    if not key_item:rule['held']=kanto_held_rule(sid)
    def action(effect,**kwargs):rule.update(effect=effect,**kwargs)
    def medicine(**kwargs):action('medicine',field=True,battle=True,target='pokemon',**kwargs)
    if 1<=sid<=12:
        balls={1:'masterball',2:'ultraball',3:'greatball',4:'pokeball',5:'safariball',6:'netball',7:'diveball',8:'nestball',9:'repeatball',10:'timerball',11:'luxuryball',12:'premierball'}
        action('capture',battle=True,ballRule=balls[sid],capture={2:2,3:1.5,5:1.5}.get(sid,1))
        if sid==5:rule.update(safariOnly=True,sellPrice=0);rule.pop('held',None)
    elif sid in (13,19,20,21,22,26,27,28,29,30,31,44):
        medicine(heal={13:20,19:65535,20:65535,21:200,22:50,26:50,27:60,28:80,29:100,30:50,31:200,44:20}[sid])
        if sid==19:rule['cure']=['all']
        if sid==30:rule['bitter']=[-5,-10]
        if sid==31:rule['bitter']=[-10,-15]
    elif sid in (14,15,16,17,18,23,32,38,39,40,41):
        medicine(cure={14:['poison','toxic'],15:['burn'],16:['freeze'],17:['sleep'],18:['paralysis'],23:['all'],32:['all'],38:['all'],39:['sleep'],40:['confusion'],41:['infatuation']}[sid])
        if sid==32:rule['bitter']=[-5,-10]
        if sid in (39,40,41):rule['reusable']=True
        if sid in (40,41):rule['field']=False
    elif sid in (24,25,33):
        action('revive',field=True,battle=True,target='pokemon',fraction=.5 if sid==24 else 1)
        if sid==33:rule['bitter']=[-15,-20]
    elif sid in (34,35,36,37):
        action('pp',field=True,battle=True,target='pokemon' if sid in (36,37) else 'move',allMoves=sid in (36,37),pp=10 if sid in (34,36) else 65535)
    elif sid in (42,43):action('encounterflute',field=True,reusable=True,encounterRate=[1,2] if sid==42 else [3,2])
    elif sid==45:action('sacredash',field=True,target='party')
    elif sid in (63,64,65,66,67,70):action('vitamin',field=True,target='pokemon',stat={63:0,64:1,65:2,66:3,67:4,70:5}[sid])
    elif sid==68:action('level',field=True,target='pokemon')
    elif sid in (69,71):action('ppboost',field=True,target='move',increments=1 if sid==69 else 3)
    elif sid==73:action('guardspec',battle=True,target='active')
    elif sid==74:action('direhit',battle=True,target='active')
    elif 75<=sid<=79:action('xstat',battle=True,target='active',stat={75:1,76:2,77:3,78:0,79:4}[sid])
    elif sid in (80,81):action('escape',battle=True,wildOnly=True)
    elif sid in (83,84,86):action('repel',field=True,steps={83:200,84:250,86:100}[sid])
    elif sid==85:action('escape',field=True)
    elif 93<=sid<=98:action('evolution',field=True,target='pokemon')
    elif 121<=sid<=132:action('mail',field=True,target='pokemon',reusable=True)
    elif 133<=sid<=142:
        if sid==138:action('pp',field=True,battle=True,target='move',allMoves=False,pp=10)
        elif sid in (139,142):medicine(heal=10 if sid==139 else 30)
        else:medicine(cure={133:['paralysis'],134:['sleep'],135:['poison','toxic'],136:['burn'],137:['freeze'],140:['confusion'],141:['all']}[sid])
        if sid==140:rule['field']=False
    elif 143<=sid<=175 or 179<=sid<=225 or 254<=sid<=258:action('held')
    elif machine is not None:
        action('machine',field=True,target='machine',move=int(machine['move']),machineIndex=int(machine['index']),reusable=False)
        rule['description']=f"Teaches {machine.get('moveName','the native move')} to a compatible Pokémon. One TM is used after successful teaching."
    # Field and story identities include the extended FireRed key-item table.
    import re,unicodedata
    name=re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',item['name']).encode('ascii','ignore').decode().lower())
    rule['nativeRole']=name
    if name in ('bicycle','machbike','acrobike'):action('bicycle',field=True,reusable=True)
    elif name in ('oldrod','goodrod','superrod'):action('fishing',field=True,reusable=True,rod=name[:-3])
    elif name=='itemfinder':action('itemfinder',field=True,reusable=True)
    elif name=='coincase':action('coincase',field=True,reusable=True)
    elif name=='pokeflute':action('pokeflute',field=True,battle=True,reusable=True,target='party')
    elif name in ('helixfossil','domefossil','oldamber','rootfossil','clawfossil'):action('fossil',field=True,reusable=False,target='none',species={'helixfossil':'fr_138','domefossil':'fr_140','oldamber':'fr_142','rootfossil':'fr_345','clawfossil':'fr_347'}[name])
    elif name in ('townmap','famechecker','teachytv'):action('journal',field=True,reusable=True)
    elif name in ('tmcase','berrypouch','powderjar'):action('case',field=True,reusable=True)
    elif name=='vsseeker':action('vsseeker',field=True,reusable=True)
    if key_item and rule['effect']=='story':rule['field']=True
    return rule


class ItemSystem:
    def __init__(self, content):
        self.c=content
        self.native_keys={}
        for key,item in content.items.items():
            sid=item.get('sourceId')
            if type(sid) is int:self.native_keys[(item.get('source','johto'),sid)]=key

    def definition(self,key):
        require(isinstance(key,str) and key in self.c.items,'Select a valid item.')
        return self.c.items[key]

    def rule(self,key):
        item=self.definition(key)
        # Compatibility with small test/extension content packs predating the
        # reviewed sidecar. The shipped pack never uses these fallbacks.
        if 'mechanics' in item:return item['mechanics']
        if 'heal' in item:return dict(effect='medicine',field=True,battle=True,target='pokemon',heal=item['heal'])
        if 'capture' in item:return dict(effect='capture',battle=True,ballRule=key,capture=item['capture'])
        if item.get('evolutionStone'):return dict(effect='evolution',field=True,target='pokemon')
        return dict(effect='unavailable')

    def ensure_mon(self,mon):
        mon.setdefault('evs',[0]*6)
        mon.setdefault('heldItemSource',self.c.species[mon['species']].get('source','kanto'))
        # Absent ppUps is canonically zero. Do not rewrite old chosen move
        # slots or trigger another login migration after normal move learning.
        return mon

    def migrate(self,state):
        candidate=copy.deepcopy(state)
        for mon in candidate['creatures']:self.ensure_mon(mon)
        candidate.setdefault('repelSteps',0)
        candidate.setdefault('coins',0)
        candidate.setdefault('pokeblocks',[])
        candidate.setdefault('heldReserve',{})
        candidate.setdefault('mailMessages',{})
        return candidate

    def held_source(self,mon):
        return mon.get('heldItemSource',self.c.species[mon['species']].get('source','kanto'))

    def held_key(self,mon):
        key=mon.get('heldItemKey');sid=mon.get('heldItemId',0);source=self.held_source(mon)
        if key in self.c.items and self.c.items[key].get('sourceId')==sid and self.c.items[key].get('source','johto')==source:return key
        return self.native_keys.get((source,sid))

    def held(self,mon):
        sid=mon.get('heldItemId',0)
        if not sid:return {}
        if self.held_source(mon)=='kanto':return kanto_held_rule(sid)
        key=self.held_key(mon)
        return copy.deepcopy(self.rule(key).get('held',{})) if key else {}

    def held_code(self,mon):return int(self.held(mon).get('legacyCode',0))

    def is_mail(self,mon):
        return self.held_source(mon)=='kanto' and 121<=int(mon.get('heldItemId',0))<=132

    def held_label(self,mon):
        sid=mon.get('heldItemId',0)
        if not sid:return None
        key=self.held_key(mon)
        if key:return self.c.items[key]['name']
        if self.held_source(mon)=='kanto' and sid in KANTO_NAMES:return KANTO_NAMES[sid]
        return f'{self.held_source(mon).title()} native item #{sid}'

    def public_mon(self,mon):
        ability_slot=self.ability_slot(mon);abilities=self.c.species[mon['species']].get('abilities',[0,0])
        return dict(evs=list(mon.get('evs',[0]*6)),friendship=int(mon.get('friendship',70)),
                    abilitySlot=ability_slot,abilityId=abilities[ability_slot] if ability_slot<len(abilities) else 0,
                    heldItemId=mon.get('heldItemId',0),heldItemKey=self.held_key(mon),heldItemName=self.held_label(mon),
                    heldItemSource=self.held_source(mon),captureBall=mon.get('captureBall'),
                    condition=copy.deepcopy(mon.get('condition',{})),heldMail=mon.get('heldMail'))

    def ability_slot(self,mon):
        abilities=self.c.species[mon['species']].get('abilities',[0,0])
        if len(abilities)<2 or not abilities[1]:return 0
        return mon.get('abilitySlot',int(mon.get('personality',0))&1)&1

    def multiplier(self,key,battle,side):
        rule=self.rule(key);kind=rule.get('ballRule',key);enemy=battle.mon(1-side)
        if kind=='timerball':return min(4,(10+max(0,battle.turn-1))/10)
        if kind=='netball':return 3 if set(battle.types(enemy)) & {6,11} else 1
        if kind=='diveball':return 3.5 if battle.terrain=='underwater' else 1
        if kind=='nestball':return max(1,(40-enemy['level'])/10)
        if kind=='repeatball':
            dex=self.c.species[enemy['species']].get('nationalDex',self.c.species[enemy['species']].get('dexNumber'))
            caught=battle.caught_species[side]
            return 3 if enemy['species'] in caught or (dex is not None and any(self.c.species.get(key,{}).get('nationalDex',self.c.species.get(key,{}).get('dexNumber'))==dex for key in caught)) else 1
        if kind=='fastball':return 4 if self.c.species[enemy['species']]['baseStats'][3]>=100 else 1
        return self.c.items[key].get('capture',rule.get('capture',1))

    def increase_friendship(self,mon,amount):
        ball=mon.get('captureBall');luxury=ball=='luxuryball' or (ball in self.c.items and self.rule(ball).get('ballRule')=='luxuryball')
        if amount>0 and self.held_code(mon)==184:amount=amount*3//2
        if amount>0 and luxury:amount+=1
        mon['friendship']=max(0,min(255,int(mon.get('friendship',70))+amount))

    def positive_friendship(self,mon):
        value=int(mon.get('friendship',70));self.increase_friendship(mon,5 if value<100 else 3 if value<200 else 2)

    def _bitter(self,mon,rule):
        values=rule.get('bitter')
        if values:self.increase_friendship(mon,values[1] if mon.get('friendship',70)>=200 else values[0])

    def _owned_item(self,inventory,key):
        self.definition(key);require(inventory.get(key,0)>0,'You have none of that item.')

    def _move_slot(self,mon,data):
        slot=integer(data.get('slot'),0,3,'Move slot');require(slot<len(mon['moves']),'Select an existing move.')
        if data.get('expectedMove') is not None:require(data['expectedMove']==mon['moves'][slot]['id'],'That move slot changed. Reopen the item menu.')
        return slot

    def apply_mon(self,key,original,data,*,battle=False,volatile=None):
        """Validate and calculate a single-target effect without changing inputs."""
        rule=self.rule(key);effect=rule['effect'];mon=copy.deepcopy(original);self.ensure_mon(mon)
        vol=copy.deepcopy(volatile or {});before=copy.deepcopy((mon,vol));maximum=self.c.stats(mon)[0]
        if effect=='medicine':
            require(mon['hp']>0,'That Pokémon has fainted. Use a revival item first.')
            if rule.get('heal'):mon['hp']=min(maximum,mon['hp']+rule['heal'])
            cure=rule.get('cure',[])
            if mon.get('status') and ('all' in cure or mon['status'] in cure):
                mon['status']='';mon['sleep']=0;vol.pop('toxicCounter',None);vol.pop('nightmare',None)
            if 'all' in cure or 'confusion' in cure:vol.pop('confusionTurns',None)
            if 'infatuation' in cure:vol.pop('attractSource',None)
        elif effect=='revive':
            require(mon['hp']==0,'Revival items require a fainted Pokémon.')
            mon['hp']=max(1,int(maximum*rule['fraction']));mon['status']='';mon['sleep']=0
        elif effect=='pp':
            slots=range(len(mon['moves'])) if rule.get('allMoves') else [self._move_slot(mon,data)]
            for slot in slots:
                move=mon['moves'][slot];move['pp']=min(self.c.pp_max(move),move['pp']+rule['pp'])
        elif effect=='ppboost':
            require(not battle,'PP upgrades are used outside battle.')
            slot=self._move_slot(mon,data);move=mon['moves'][slot];base=self.c.moves[str(move['id'])]['pp']
            require(move['id']!=166 and base>1,'That move cannot receive PP upgrades.')
            require(move.get('ppUps',0)<3,'That move already has maximum PP upgrades.')
            old=self.c.pp_max(move);move['ppUps']=min(3,move.get('ppUps',0)+rule['increments']);move['pp']+=self.c.pp_max(move)-old
        elif effect=='vitamin':
            require(not battle,'Vitamins are used outside battle.');index=rule['stat'];evs=mon['evs']
            gain=max(0,min(10,100-evs[index],510-sum(evs)))
            require(gain>0,'That vitamin cannot add EVs: its stat cap is 100 and the total cap is 510.')
            oldhp=maximum;evs[index]+=gain;mon['hp']=min(self.c.stats(mon)[0],mon['hp']+self.c.stats(mon)[0]-oldhp) if mon['hp']>0 else 0
            self.positive_friendship(mon)
        elif effect=='level':
            require(not battle,'Rare Candy is used outside battle.');require(mon['level']<100,'That Pokémon is already level 100.')
            oldhp=mon['hp'];growth=self.c.species[mon['species']]['growth']
            self.c.gain_xp(mon,self.c.xp(mon['level']+1,growth)-mon['exp'])
            if oldhp==0:mon['hp']=max(1,self.c.stats(mon)[0]-maximum);mon['status']='';mon['sleep']=0
            self.positive_friendship(mon)
        elif effect=='ability':
            require(not battle,'A Skill Capsule is used outside battle.')
            abilities=self.c.species[mon['species']].get('abilities',[0,0])
            require(len(abilities)>=2 and abilities[0] and abilities[1] and abilities[0]!=abilities[1],'This species does not have two different regular abilities.')
            target=1-self.ability_slot(mon)
            require(1 <= abilities[target] <= 77,'The destination ability is outside this battle engine’s supported native ability set. The capsule was not consumed.')
            mon['abilitySlot']=target
        else:require(False,'This item uses a different action. Choose its displayed Bag action.')
        require((mon,vol)!=before,'That item would have no effect. Nothing was used.')
        self._bitter(mon,rule)
        return mon,vol

    def battle_action(self,battle,side,key,data,*,preview=False):
        self._owned_item(battle.items[side],key);rule=self.rule(key)
        require(rule.get('battle') and rule['effect'] not in ('capture','tera'),'That item cannot be used with this battle action.')
        active=battle.mon(side);effect=rule['effect'];target=active
        if effect=='escape':
            require(battle.kind=='wild','This item can only end a wild Pokémon battle.')
            if not preview:
                battle.ended=True;battle.winner=None
                battle.audio('escape',side)
                battle.logs.append(f'{battle.names[side]} got away safely!')
        elif effect in ('xstat','direhit','guardspec'):
            require(data.get('uid') in (None,active['uid']),'This item is only used on the active Pokémon.')
            if effect=='xstat':require(battle.tiers(active)[rule['stat']]<6,'That stat is already at its maximum battle stage.')
            elif effect=='direhit':require(not battle.vol(active).get('focusEnergy'),'Critical-hit focus is already active.')
            else:require(battle.side[side]['mist']<=0,'Guard Spec. protection is already active.')
            if not preview:
                if effect=='xstat':battle._change_stage(side,rule['stat'],1,source_side=side)
                elif effect=='direhit':battle.vol(active)['focusEnergy']=True
                else:battle.side[side]['mist']=5
                self.increase_friendship(active,1 if active.get('friendship',70)<200 else 0)
        elif effect=='pokeflute':
            targets=[mon for roster in battle.rosters for mon in roster if mon['hp']>0 and mon['status']=='sleep' and battle.ability(mon)!=43]
            require(bool(targets),'No Pokémon can be awakened. Nothing was used.')
            if not preview:
                for mon in targets:mon['status']='';mon['sleep']=0;battle.vol(mon).pop('nightmare',None)
        else:
            uid=data.get('uid',active['uid']);require(isinstance(uid,str),'Select a party Pokémon.')
            target=next((m for m in battle.rosters[side] if m['uid']==uid),None)
            require(target is not None,'That Pokémon is not in your battle party.')
            if effect=='pp' and battle.vol(target).get('transformed'):require(False,'Switch out of Transform before restoring the original move’s PP.')
            result,vol=self.apply_mon(key,target,data,battle=True,volatile=battle.vol(target))
            if not preview:target.clear();target.update(result);battle.volatile[target['uid']]=vol
        if not preview:
            if not rule.get('reusable'):battle.items[side][key]-=1
            battle.logs.append(f'{battle.names[side]} used {self.c.items[key]["name"]}'+(f' on {battle.name(target)}.' if effect!='pokeflute' else '. Sleeping Pokémon woke up.'))
            battle.audio('recover',side,species=target['species'],item=key)

    def evolve_with_item(self,state,key,data):
        mon=self.c.growth.owned(state,data.get('uid'));rule=self.rule(key);token=rule.get('evolutionAlias',key)
        options=[o for o in self.c.growth.options(mon) if o.get('item')==token and not o.get('deferred')]
        require(options,'That Pokémon has no available evolution using this item.')
        target=data.get('target');require(isinstance(target,str) and any(o['target']==target for o in options),'Choose and confirm an available evolution.')
        if token==key:return self.c.growth.evolve(state,mon['uid'],target,item=token)
        # Alias substitution happens only in the detached transaction. It does
        # not grant a real extra item or change the owner's original token stack.
        candidate=copy.deepcopy(state);original=candidate['items'].get(token,0)
        candidate['items'][key]-=1;candidate['items'][token]=original+1
        candidate=self.c.growth.evolve(candidate,mon['uid'],target,item=token)
        if original==0:candidate['items'].pop(token,None)
        else:candidate['items'][token]=original
        return candidate

    def field_use(self,state,key,data):
        self._owned_item(state['items'],key);rule=self.rule(key)
        require(rule.get('field'),'Use this item through its battle, held-item, or sale action.')
        candidate=copy.deepcopy(state);effect=rule['effect']
        if self.definition(key).get('source')=='kanto' and rule.get('target') in ('pokemon','move','machine'):
            require(data.get('uid') in candidate['party'],'Select a Pokémon in your current party.')
        if effect=='evolution':return self.evolve_with_item(candidate,key,data)
        if effect=='mail':return self.equip(candidate,{**data,'item':key})
        if effect=='machine':
            mon=self.c.growth.owned(candidate,data.get('uid'));move=rule['move']
            require(key in self.c.species[mon['species']].get('machines',[]),'This Pokémon is not compatible with that machine.')
            require(move not in [m['id'] for m in mon['moves']],'That Pokémon already knows this move.')
            slot=integer(data.get('slot'),0,3,'Move slot');require(slot<=len(mon['moves']),'Choose an existing move or the next empty slot.')
            if slot<len(mon['moves']) and data.get('expectedMove') is not None:require(data['expectedMove']==mon['moves'][slot]['id'],'That move slot changed. Reopen the teaching menu.')
            if self.definition(key).get('source')=='kanto' and slot<len(mon['moves']):
                require(mon['moves'][slot]['id'] not in (15,19,57,70,148,249,127,291),'An HM move cannot be forgotten with a TM. Visit the Move Deleter first.')
            value={'id':move,'pp':self.c.moves[str(move)]['pp'],'ppUps':0}
            if slot==len(mon['moves']):mon['moves'].append(value)
            else:mon['moves'][slot]=value
            mon['pendingLearn']=[p for p in mon.get('pendingLearn',[]) if p.get('move')!=move]
        elif effect in ('medicine','revive','pp','ppboost','vitamin','level','ability'):
            original=self.c.growth.owned(candidate,data.get('uid'));result,_=self.apply_mon(key,original,data)
            original.clear();original.update(result)
        elif effect in ('sacredash','pokeflute'):
            party=[m for m in candidate['creatures'] if m['uid'] in candidate['party']]
            targets=[m for m in party if m['hp']==0] if effect=='sacredash' else [m for m in party if m['hp']>0 and m['status']=='sleep']
            require(targets,'No current party member needs that item. Nothing was used.')
            for mon in targets:
                if effect=='sacredash':mon['hp']=self.c.stats(mon)[0]
                mon['status']='';mon['sleep']=0
        elif effect=='repel':
            require(candidate.get('repelSteps',0)<=0,'A Repel is already active. Wait until it wears off.')
            candidate['repelSteps']=rule['steps']
        else:require(False,'Choose this item’s dedicated service or field interaction.')
        if not rule.get('reusable'):candidate['items'][key]-=1
        return candidate

    def _return_held(self,candidate,mon):
        if not mon.get('heldItemId'):return
        key=self.held_key(mon)
        if key:
            require(candidate['items'].get(key,0)<999,'Make room in the Bag for the currently held item first.')
            candidate['items'][key]=candidate['items'].get(key,0)+1
            if mon.get('heldMail'):candidate.setdefault('mailMessages',{}).setdefault(key,[]).append(mon['heldMail'])
        else:
            # Preserve older source-specific objects losslessly instead of
            # converting (for example) FireRed Berry Juice into Sigma Up-Grade.
            source=self.held_source(mon);sid=mon['heldItemId'];token=f'{source}:{sid}'
            reserve=candidate.setdefault('heldReserve',{});entry=reserve.get(token,{'id':sid,'source':source,'name':self.held_label(mon),'quantity':0})
            require(entry['quantity']<999,'Make room for this source-specific held item first.')
            entry['quantity']+=1;reserve[token]=entry
        replace_held(mon,{'heldItemId':0})

    def equip(self,state,data,*,take=False):
        candidate=copy.deepcopy(state);mon=self.c.growth.owned(candidate,data.get('uid'))
        if data.get('expectedHeld') is not None:require(data['expectedHeld']==mon.get('heldItemId',0),'The held item changed. Reopen this Pokémon’s summary.')
        if take:
            require(mon.get('heldItemId',0)>0,'This Pokémon is not holding an item.')
            self._return_held(candidate,mon);return candidate
        reserve_key=data.get('reserve')
        if reserve_key is not None:
            require(isinstance(reserve_key,str),'Select a source-specific held item.')
            entry=candidate.get('heldReserve',{}).get(reserve_key)
            require(entry and entry['quantity']>0,'That source-specific held item is unavailable.')
            # Decrement first so exchanging identical source items cannot fail
            # merely because the return stack was previously full.
            entry['quantity']-=1;value={'heldItemId':entry['id'],'heldItemSource':entry['source']}
        else:
            key=data.get('item');self._owned_item(candidate['items'],key);rule=self.rule(key)
            require(bool(rule.get('held')),'That item is not a held item. Use its displayed action instead.')
            item=self.c.items[key]
            if item.get('source')=='kanto':require(mon['uid'] in candidate['party'],'Select a Pokémon in your current party.')
            require(self.held_key(mon)!=key,'This Pokémon is already holding that item.')
            candidate['items'][key]-=1
            value={'heldItemId':item['sourceId'],'heldItemSource':item.get('source','johto'),'heldItemKey':key}
            if rule['effect']=='mail':
                messages=candidate.setdefault('mailMessages',{}).setdefault(key,[])
                previous=messages.pop(0) if messages else None
                message=data.get('message',previous)
                if message is not None:
                    require(isinstance(message,str) and len(message)<=144 and all(c.isprintable() or c=='\n' for c in message),'Mail must be at most 144 printable characters.')
                    message=message.strip()
                    if message:value['heldMail']=message
        self._return_held(candidate,mon);replace_held(mon,value);return candidate

    def sell(self,state,key,quantity):
        self._owned_item(state['items'],key);count=integer(quantity,1,999,'Quantity')
        price=int(self.rule(key).get('sellPrice',0));require(price>0,'That item is not for sale.')
        require(state['items'].get(key,0)>=count,'You do not have that many items.')
        require(state['money']+price*count<=2_000_000_000,'Your money balance would exceed the limit.')
        candidate=copy.deepcopy(state);candidate['items'][key]-=count;candidate['money']+=price*count
        if key in candidate.get('mailMessages',{}):candidate['mailMessages'][key]=candidate['mailMessages'][key][:candidate['items'][key]]
        return candidate

    def experience_recipients(self,roster,participants,total):
        """Split one defeated Pokémon's EXP using the Gen III Exp. Share rule.

        A participant holding Exp. Share receives both shares. Fainted party
        members receive neither EXP nor EVs; stored Pokémon are not passed in.
        """
        participants=set(participants)
        fighters=[m for m in roster if m['hp']>0 and m['uid'] in participants]
        holders=[m for m in roster if m['hp']>0 and self.held(m).get('expShare')]
        if not holders:return [(m,max(1,total//len(fighters))) for m in fighters]
        awards={m['uid']:0 for m in roster}
        if fighters:
            for mon in fighters:awards[mon['uid']]+=max(1,total//2//len(fighters))
        for mon in holders:awards[mon['uid']]+=max(1,total//2//len(holders))
        return [(m,awards[m['uid']]) for m in roster if awards[m['uid']]]

    def award_experience(self,mon,enemy_species,amount):
        """Return actual EXP/levels; apply held training effects before level-up."""
        self.ensure_mon(mon);held=self.held(mon);oldhp=self.c.stats(mon)[0]
        yields=list(self.c.species[enemy_species].get('evYield',[0]*6))
        if 'evStat' in held:yields[held['evStat']]+=held.get('evAdd',4)
        for index,value in enumerate(yields):
            gain=max(0,min(value*held.get('evMultiplier',1),255-mon['evs'][index],510-sum(mon['evs'])))
            mon['evs'][index]+=gain
        if mon['hp']>0:mon['hp']+=self.c.stats(mon)[0]-oldhp
        num,den=held.get('exp',[1,1]);actual=max(1,amount*num//den);levels=self.c.gain_xp(mon,actual)
        for _ in range(levels):self.positive_friendship(mon)
        return actual,levels

    def service(self,state,key,data):
        """Small explicitly authored MMO services, after World location checks."""
        self._owned_item(state['items'],key);candidate=copy.deepcopy(state);action=data.get('action')
        if key=='whtapricorn':
            require(action=='craft','Choose Make Fast Ball.');require(candidate['items'].get('fastball',0)<999,'Your Fast Ball stack is full.')
            candidate['items'][key]-=1;candidate['items']['fastball']=candidate['items'].get('fastball',0)+1
        elif key=='coincase':
            if action=='buycoins':
                count=integer(data.get('quantity'),1,9999,'Coin quantity');cost=count*20
                require(candidate['money']>=cost,'You do not have enough money.');require(candidate.get('coins',0)+count<=9999,'The Coin Case holds at most 9,999 coins.')
                candidate['money']-=cost;candidate['coins']=candidate.get('coins',0)+count
            elif action=='prize':
                prizes={'greatball':60,'ultraball':120,'timerball':100,'netball':100,'rarecandy':500}
                reward=data.get('reward');require(isinstance(reward,str) and reward in prizes,'Choose a displayed exchange prize.')
                cost=prizes[reward];require(candidate.get('coins',0)>=cost,'You do not have enough coins.');require(candidate['items'].get(reward,0)<999,'That item stack is full.')
                candidate['coins']-=cost;candidate['items'][reward]=candidate['items'].get(reward,0)+1
            else:require(False,'Choose a Coin Case exchange action.')
        elif key=='pokeblockcas':
            blocks=candidate.setdefault('pokeblocks',[])
            if action=='blend':
                berry=data.get('berry');require(berry in ('lumberry','sitrusberry'),'Choose a Lum or Sitrus Berry.')
                require(candidate['items'].get(berry,0)>0,'You do not have that berry.');require(len(blocks)<40,'The case holds at most 40 blocks. Feed a block first.')
                candidate['items'][berry]-=1
                # Explicit, stable MMO recipe; no fabricated native contest data.
                blocks.append({'id':data['_blockId'],'flavor':'beauty' if berry=='sitrusberry' else 'smart','power':20,'feel':10})
            elif action=='feed':
                mon=self.c.growth.owned(candidate,data.get('uid'));bid=data.get('block');require(isinstance(bid,str),'Select a Pokéblock.')
                index=next((i for i,b in enumerate(blocks) if b['id']==bid),None);require(index is not None,'That block was already used or is unavailable.')
                block=blocks[index];condition=mon.setdefault('condition',{});require(condition.get('sheen',0)<255,'That Pokémon is too full for another Pokéblock.')
                require(condition.get(block['flavor'],0)<255 or mon.get('friendship',70)<255,'That block would have no effect.')
                condition[block['flavor']]=min(255,condition.get(block['flavor'],0)+block['power']);condition['sheen']=min(255,condition.get('sheen',0)+block['feel']);self.increase_friendship(mon,10);blocks.pop(index)
            else:require(False,'Choose Blend or Feed.')
        else:require(False,'This item has no exchange service.')
        return candidate
