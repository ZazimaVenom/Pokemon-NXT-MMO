#!/usr/bin/env python3
"""Recover bounded FireRed field service operands; never execute ROM scripts.

Only the project's reviewed Rev 1 ROM is accepted. Door coordinates come from
background events, and prize species/items/prices from exact setvar operands.
The resulting sidecar contains facts, not executable ROM code.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
try:
    from .extract_adventure_data import Rom
except ImportError:
    from extract_adventure_data import Rom

ROOT = Path(__file__).resolve().parents[1]
SHA = '729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059'

def extract(rom_path, root=ROOT):
    r = Rom(rom_path)
    if len(r.b) != 16777216 or hashlib.sha256(r.b).hexdigest() != SHA:
        raise ValueError('Unreviewed FireRed ROM revision')
    world = json.loads((root/'Server/data/world.json').read_text(encoding='utf-8'))
    doors = {}
    for mid, m in world['maps'].items():
        if not mid.startswith('kanto_') or not m.get('sourceHeader'): continue
        events = r.ptr(int(m['sourceHeader'],16)+4)
        count = r.b[events+3]
        table = r.ptr(events+16) if count else 0
        for index in range(count):
            off = table+index*12
            if r.b[off+5] != 0 or not r.validptr(off+8): continue
            script = r.ptr(off+8)
            # Twenty explicit, identical Silph Card Key wrappers. Their only
            # variable operands are a door number and its persisted flag.
            if not 0x1a8993 <= script <= 0x1a8b81 or (script-0x1a8993)%26: continue
            raw = r.raw(script,26)
            if raw[:4] != b'\x69\x16\x01\x40' or raw[6:9] != b'\x16\x04\x80' or raw[11] != 0x2b or raw[20:25] != b'\x05\x9b\x8b\x1a\x08':
                raise ValueError('Card Key script signature changed')
            number, flag = r.u16(script+4), r.u16(script+9)
            if flag != 0x279+number or r.u16(script+12) != flag:
                raise ValueError('Card Key door flag changed')
            key = f'silph_card_{number}'
            row = doors.setdefault(key, {'id':key,'map':mid,'sourceFlag':flag,'tiles':[], 'sourceScript':hex(script)})
            if row['map'] != mid: raise ValueError('Door spans maps')
            x,y = r.u16(off),r.u16(off+2)
            if not 0<=x<m['width'] or not 0<=y<m['height']: raise ValueError('Door tile out of bounds')
            row['tiles'].append([x,y])
    if len(doors) != 20 or any(len(d['tiles']) != 4 for d in doors.values()):
        raise ValueError('Expected twenty four-tile Silph doors')

    def tile_commands(start):
        rows=[];off=start
        for _ in range(128):
            if r.b[off]==3:return rows
            if r.b[off]!=0xa2:raise ValueError('Unexpected metatile script opcode at '+hex(off))
            rows.append({'x':r.u16(off+1),'y':r.u16(off+3),'metatile':r.u16(off+5),'collision':r.u16(off+7)})
            off+=9
        raise ValueError('Unbounded metatile script')
    # The common Card Key handler selects a native metatile rewrite per door.
    dispatch=r.raw(0x1a8b9b,1024)
    for number in range(1,21):
        needle=b'\x21\x01\x40'+number.to_bytes(2,'little')+b'\x07\x01'
        at=dispatch.find(needle)
        if at<0:raise ValueError('Missing native Card Key door dispatch')
        script=r.ptr(0x1a8b9b+at+len(needle))
        doors[f'silph_card_{number}']['openTiles']=tile_commands(script)

    prizes = []
    # Each selected prize block sets native item/species and cost variables.
    for kind, starts, npc in (
        ('pokemon',[0x16cc8d,0x16cc9d,0x16ccad,0x16ccbd,0x16cccd],3),
        ('item',[0x16cf1d,0x16cf31,0x16cf45,0x16cf59,0x16cf6d],4),
        ('item',[0x16d088,0x16d098,0x16d0a8,0x16d0b8,0x16d0c8],5),
    ):
        for off in starts:
            if r.raw(off,3)!=b'\x16\x01\x40' or r.raw(off+5,3)!=b'\x16\x02\x40':
                raise ValueError('Prize script signature changed')
            prizes.append({'kind':kind,'sourceId':r.u16(off+3),'coins':r.u16(off+8),'npc':npc,'sourceScript':hex(off)})
    # Native givepokemon commands in the corresponding prize branches.
    for row,off in zip(prizes[:5],[0x16cd4c,0x16cd61,0x16cd76,0x16cd8b,0x16cda0]):
        if r.raw(off,3)!=b'\x79\x01\x40': raise ValueError('Prize level signature changed')
        row['level']=r.b[off+3]
    fossils=[]
    for item_id,species_id,off in [(357,138,0x16e7e1),(358,140,0x16e826),(354,142,0x16e86b)]:
        if r.b[off]!=0x79 or r.u16(off+1)!=species_id or r.b[off+3]!=5:
            raise ValueError('Fossil revival species/level signature changed at '+hex(off))
        fossils.append({'sourceId':item_id,'species':f'fr_{species_id}','level':5,'sourceScript':hex(off)})
    # Giovanni's office opens only after BOTH Rocket guards are defeated.
    # Read the native checktrainerflag operands and six open-door metatiles.
    if r.b[0x16136b]!=0x60 or r.b[0x161374]!=0x60:
        raise ValueError('Rocket guard condition changed')
    guard_ids=[r.u16(0x16136c),r.u16(0x161375)]
    gate_tiles=[]
    for off in range(0x161519,0x16154f,9):
        if r.b[off]!=0xa2 or r.u16(off+7)!=0:raise ValueError('Rocket open door changed')
        gate_tiles.append([r.u16(off+1),r.u16(off+3)])
    trainer_doors=[{'map':'kanto_1_45','requiredTrainerIds':guard_ids,'tiles':gate_tiles,'openTiles':tile_commands(0x161519),'sourceScript':'0x161519'}]
    mansion=[]
    for mid,switches,on,off in [
        ('kanto_1_59',[[5,5]],0x1a7bf2,0x1a7cd4),
        ('kanto_1_60',[[2,16]],0x1a7db6,0x1a7e50),
        ('kanto_1_61',[[12,5]],0x1a7eea,0x1a7f57),
        ('kanto_1_62',[[24,29],[27,5]],0x1a7fc4,0x1a809d),
    ]:
        mansion.append({'map':mid,'switches':switches,'sourceFlag':0x26c,
                        'on':tile_commands(on),'off':tile_commands(off),'sourceScripts':[hex(on),hex(off)]})
    handovers=[
        {'sourceId':349,'map':'kanto_4_3','npc':4,'removeOffset':0x1696af,'flags':[0x829],'variables':{'16508':1},'role':'parcel'},
        {'sourceId':353,'map':'kanto_11_7','npc':1,'removeOffset':0x16d847,'flags':[0x23a],'role':'goldteeth'},
        {'sourceId':374,'map':'kanto_32_0','npc':3,'removeOffset':0x17102e,'flags':[0x844,0x5c,0x8c],'variables':{'16502':6},'requiresSourceId':368,'role':'sapphire'},
    ]
    for mid,off in [('kanto_17_1',0x16f9d0),('kanto_18_0',0x16fa96),('kanto_19_0',0x16fb5d),('kanto_20_0',0x16fc23)]:
        handovers.append({'sourceId':369,'map':mid,'npc':1,'removeOffset':off,'flags':[],'variables':{'16482':1},'role':'tea'})
    for row in handovers:
        off=row['removeOffset']
        if r.raw(off,5)!=b'\x45'+row['sourceId'].to_bytes(2,'little')+b'\x01\x00':raise ValueError('Native story item handover changed')
        row['sourceScript']=hex(row.pop('removeOffset'))
    elevator_options=[]
    for label,off in [('B1F',0x16160e),('B2F',0x161636),('B4F',0x16165e)]:
        if r.b[off]!=0x3f:raise ValueError('Rocket elevator destination command changed')
        mid=f'kanto_{r.b[off+1]}_{r.b[off+2]}';x,y=r.u16(off+4),r.u16(off+6)
        if mid not in world['maps']:raise ValueError('Unknown elevator destination')
        elevator_options.append({'id':mid,'label':label,'door':[x,y],'arrival':[x,y+1],'sourceScript':hex(off)})
    elevators=[{'map':'kanto_1_46','sourceId':356,'panel':[0,2],'destinations':elevator_options}]
    powder_prizes=[]
    for off in range(0x16afe4,0x16b0c0,20):
        if r.b[off]!=0x80 or r.raw(off+4,3)!=b'\x16\x08\x80' or r.raw(off+9,3)!=b'\x16\x09\x80':
            raise ValueError('Berry Powder medicine branch changed')
        sid,cost=r.u16(off+7),r.u16(off+12)
        if r.u16(off+2)!=sid:raise ValueError('Berry Powder item identity mismatch')
        powder_prizes.append({'sourceId':sid,'powder':cost,'sourceScript':hex(off)})
    result={'format':1,'sourceSha256':SHA,'doors':list(doors.values()),'coinPrizes':prizes,'trainerDoors':trainer_doors,'mansionSwitches':mansion,'handovers':handovers,'elevators':elevators,'powderPrizes':powder_prizes,
            'fossils':fossils,'fossilLab':{'map':'kanto_12_4','npc':2},
            'coinCounter':{'map':'kanto_10_14','npc':2},'prizeCounterMap':'kanto_10_15',
            'policy':'Revival requires leaving the lab room. Native slot/prize operands are preserved; no slot-machine gambling is simulated.'}
    target=root/'Server/data/kanto_field_services.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Extracted {len(doors)} Card Key doors, {len(prizes)} prizes, and {len(fossils)} fossil recipes')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('rom',type=Path);parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args();extract(args.rom,args.root)
