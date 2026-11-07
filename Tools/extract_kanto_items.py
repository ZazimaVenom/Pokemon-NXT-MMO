#!/usr/bin/env python3
"""Extract audited FireRed Rev 1 items, field rewards and machine compatibility.

The ROM is a build-time input only. Every offset below is validated against the
reviewed digest and active engine references; no arbitrary ROM code is executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

try:
    from .extract_adventure_data import Rom, normalize, normalize_objects, field_item_script, ITEM_POCKETS
    from .extract_sigma_dialogue import CHARS, decode_text
except ImportError:
    from extract_adventure_data import Rom, normalize, normalize_objects, field_item_script, ITEM_POCKETS
    from extract_sigma_dialogue import CHARS, decode_text

ROOT = Path(__file__).resolve().parents[1]
SHA = '729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059'
HMS = set(range(339, 347))
ITEM_TABLE = 0x3db098
ICON_TABLE = 0x3d4304
MACHINE_TABLE = 0x45a86c
COMPATIBILITY_TABLE = 0x252c38
HIDDEN_FLAG_BASE = 0x3e8
BALL_EXCLUSIONS = {
    'kanto_10_11:2': 'Eevee gift actor; not an inventory item',
    'kanto_14_2:6': 'Fighting Dojo Pokemon choice actor; not an inventory item',
    'kanto_14_2:7': 'Fighting Dojo Pokemon choice actor; not an inventory item',
    'kanto_1_45:2': 'Silph Scope story grant; handled by audited gift service',
    'kanto_1_45:4': 'Lift Key story grant; handled by audited gift service',
    'kanto_1_95:7': 'Power Plant scripted wild Pokemon decoy; not an inventory item',
    'kanto_1_95:8': 'Power Plant scripted wild Pokemon decoy; not an inventory item',
    'kanto_4_3:5': 'Oak starter Pokemon choice actor; not an inventory item',
    'kanto_4_3:6': 'Oak starter Pokemon choice actor; not an inventory item',
    'kanto_4_3:7': 'Oak starter Pokemon choice actor; not an inventory item',
}


def native_name(raw):
    return ''.join(CHARS.get(byte, '?') for byte in raw.split(b'\xff')[0]).strip()


def display_name(name):
    if name.startswith(('TM', 'HM')) and name[2:].isdigit():
        return name
    result = name.title().replace('Poké', 'Poké').replace('Pp ', 'PP ').replace('Hp ', 'HP ')
    return result.replace('Vs Seeker', 'VS Seeker').replace('Tm Case', 'TM Case').replace('S.s.', 'S.S.')


def extract_catalog(rom):
    if rom.ptr(0x1c8) != ITEM_TABLE:
        raise ValueError('FireRed item table reference changed')
    records, by_id, excluded = {}, {}, []
    for source_id in range(1, 375):
        offset = ITEM_TABLE + source_id * 44
        raw = rom.raw(offset, 44)
        name = native_name(raw[:14])
        if not name or name == '????????':
            excluded.append({'sourceId': source_id, 'reason': 'unused native catalog slot'})
            continue
        if source_id in HMS:
            excluded.append({'sourceId': source_id, 'name': name, 'reason': 'HM excluded by requested scope'})
            continue
        if '?' in name or rom.u16(offset + 14) != source_id:
            raise ValueError(f'Invalid named native item record: {source_id}: {name}')
        key = 'fr_' + normalize(name.replace('é', 'e'))
        if key in records:
            raise ValueError('Duplicate native item identity: ' + key)
        pointer = rom.ptr(offset + 20)
        description, metadata = decode_text(rom, pointer)
        if not description or metadata.get('reason'):
            raise ValueError(f'Invalid item description: {key}: {metadata}')
        pocket, importance, price = raw[26], raw[24], rom.u16(offset + 16)
        if pocket not in ITEM_POCKETS:
            raise ValueError('Invalid native inventory pocket: ' + key)
        records[key] = {
            'name': display_name(name), 'sourceName': name, 'source': 'kanto',
            'sourceId': source_id, 'sourceOffset': hex(offset),
            'sourceStoredId': source_id, 'sourcePrice': price, 'price': price,
            'priceSource': 'firered-rom', 'pocket': pocket,
            'pocketName': ITEM_POCKETS[pocket], 'importance': importance,
            'keyItem': pocket == 2 or bool(importance), 'buyable': False,
            'tradable': not bool(importance) and source_id != 5, 'description': ' '.join(description.split()),
            'icon': f'items/kanto/{source_id}.png',
            'native': {
                'holdEffect': raw[18], 'holdParameter': raw[19],
                'descriptionOffset': hex(pointer), 'type': raw[27],
                'fieldFunction': hex(rom.u32(offset + 28)), 'battleUsage': raw[32],
                'battleFunction': hex(rom.u32(offset + 36)),
                'secondaryId': rom.u32(offset + 40),
            },
        }
        if 93 <= source_id <= 98:
            records[key]['evolutionStone'] = True
        if source_id == 5:
            records[key]['safariOnly'] = True
        by_id[source_id] = key
    return records, by_id, excluded


def extract_machines(rom, world, by_id):
    if (rom.ptr(0x125b04), rom.ptr(0x125b24)) != (MACHINE_TABLE, MACHINE_TABLE):
        raise ValueError('FireRed machine engine references changed')
    if (rom.ptr(0x43c7c), rom.ptr(0x43c94)) != (COMPATIBILITY_TABLE, COMPATIBILITY_TABLE):
        raise ValueError('FireRed compatibility engine references changed')
    machines = {}
    for index in range(50):
        offset = MACHINE_TABLE + index * 2
        move = rom.u16(offset)
        if str(move) not in world['moves']:
            raise ValueError('Unpublished FireRed machine move: ' + str(move))
        machines[by_id[index + 289]] = {
            'index': index, 'sourceMoveId': move, 'move': move,
            'moveName': world['moves'][str(move)]['name'], 'offset': hex(offset),
        }
    species = {}
    stats = rom.ptr(0x1bc)
    for key, row in sorted(world['species'].items()):
        if row.get('source') != 'kanto':
            continue
        source_id = row['sourceId']
        offset = COMPATIBILITY_TABLE + source_id * 8
        bits = struct.unpack('<Q', rom.raw(offset, 8))[0]
        raw = rom.raw(stats + source_id * 28, 28)
        held_ids = [struct.unpack_from('<H', raw, at)[0] for at in (12, 14)]
        ev_bits = struct.unpack_from('<H', raw, 10)[0]
        species[key] = {
            'sourceId': source_id, 'compatibilityOffset': hex(offset),
            'compatibilityHex': rom.raw(offset, 8).hex(),
            'machines': [machine for machine, data in machines.items() if bits & (1 << data['index'])],
            'heldItems': [{'sourceId': item, 'item': by_id.get(item)} for item in held_ids],
            'safariFleeRate': raw[24],
            'evYield': [(ev_bits >> (index * 2)) & 3 for index in range(6)],
            'baseFriendship': raw[18],
            'baseStatsOffset': hex(stats + source_id * 28),
        }
    return machines, species


def extract_evolutions(rom, world, by_id):
    table = 0x2597c4
    lookup = {row['sourceId']: key for key, row in world['species'].items() if row.get('source') == 'kanto'}
    methods = {1: 'friendship', 2: 'friendshipDay', 3: 'friendshipNight', 4: 'level',
               5: 'trade', 6: 'tradeItem', 7: 'stone', 8: 'attackHigher', 9: 'attackEqual',
               10: 'defenseHigher', 11: 'personalityLow', 12: 'personalityHigh',
               13: 'shedinjaPrimary', 14: 'shedinjaExtra', 15: 'beauty'}
    result = {}
    for source_id, key in sorted(lookup.items()):
        entries = []
        for slot in range(5):
            offset = table + (source_id * 5 + slot) * 8
            method, parameter, target, padding = struct.unpack('<4H', rom.raw(offset, 8))
            if not method:
                continue
            if padding or target not in lookup or method not in methods:
                raise ValueError('Invalid native evolution edge: ' + key)
            row = {'source': 'kanto', 'sourceSpeciesId': source_id, 'targetSourceId': target,
                   'rawMethod': method, 'rawParameter': parameter, 'offset': hex(offset),
                   'target': lookup[target], 'method': methods[method]}
            if method in (6, 7):
                row['item'] = by_id[parameter]
            if method in (4, 8, 9, 10, 11, 12, 13, 14):
                row['level'] = parameter
            if world['species'][key]['growth'] != world['species'][lookup[target]]['growth']:
                row['migrateGrowth'] = True
            entries.append(row)
        if entries:
            result[key] = entries
    return result


def extract_fields(rom, world, by_id):
    pickups, hidden, map_flags, excluded = {}, {}, {}, []
    maps_scanned = 0
    ball_count = 0
    for map_id, data in sorted(world['maps'].items()):
        if not map_id.startswith('kanto_'):
            continue
        maps_scanned += 1
        header = int(data['sourceHeader'], 16)
        map_flags[map_id] = {
            'escapeAllowed': bool(rom.b[header + 0x19] & 1),
            'bicycleAllowed': bool(rom.b[header + 0x18]),
            'runningAllowed': bool(rom.b[header + 0x19] & 2),
            'offset': hex(header + 0x18), 'raw': rom.raw(header + 0x18, 2).hex(),
        }
        events = rom.ptr(header + 4)
        count, bg_count = rom.b[events], rom.b[events + 3]
        objects = rom.ptr(events + 4) if count else None
        for obj in normalize_objects(rom, data):
            if obj['graphics'] != 92:
                continue
            ball_count += 1
            offset = objects + obj['sourceObjectIndex'] * 24
            script = rom.ptr(offset + 16)
            match = field_item_script(rom, script)
            key = f'{map_id}:{obj["id"]}'
            base = {
                'id': key, 'map': map_id, 'npc': obj['id'], 'source': 'kanto',
                'x': obj['x'], 'y': obj['y'], 'graphics': obj['graphics'],
                'sourceObjectIndex': obj['sourceObjectIndex'],
                'sourceLocalId': obj['sourceLocalId'], 'sourceObjectOffset': hex(offset),
                'sourceScript': hex(script), 'sourceFlag': rom.u16(offset + 20),
                'elevation': rom.b[offset + 8],
            }
            if not match:
                if key not in BALL_EXCLUSIONS:
                    raise ValueError('Unreviewed non-linear FireRed ball script: ' + key)
                excluded.append(dict(base, reason=BALL_EXCLUSIONS[key]))
                continue
            if match['sourceItemId'] in HMS:
                excluded.append(dict(base, sourceItemId=match['sourceItemId'], reason='HM excluded by requested scope'))
                continue
            if match['sourceItemId'] not in by_id:
                raise ValueError('Ball references undefined item: ' + key)
            pickups[key] = dict(base, **match, item=by_id[match['sourceItemId']], rewardType='item')
        backgrounds = rom.ptr(events + 16) if bg_count else None
        for index in range(bg_count):
            offset = backgrounds + index * 12
            if rom.b[offset + 5] != 7:
                continue
            x, y = struct.unpack('<hh', rom.raw(offset, 4))
            if not (0 <= x < data['width'] and 0 <= y < data['height']):
                raise ValueError('Hidden reward outside map: ' + map_id)
            source_id = rom.u16(offset + 8)
            flag_index, packed_quantity = rom.b[offset + 10:offset + 12]
            quantity, underfoot = packed_quantity & 0x7f, bool(packed_quantity & 0x80)
            if not quantity or (source_id and source_id not in by_id):
                raise ValueError('Invalid hidden inventory reward: ' + map_id)
            key = f'{map_id}:hidden:{index}'
            hidden[key] = {
                'id': key, 'map': map_id, 'source': 'kanto', 'x': x, 'y': y,
                'elevation': rom.b[offset + 4], 'sourceEventOffset': hex(offset),
                'sourceHiddenIndex': index, 'sourceItemId': source_id,
                'sourceFlag': HIDDEN_FLAG_BASE + flag_index, 'sourceFlagIndex': flag_index,
                'sourcePackedValue': hex(rom.u32(offset + 8)),
                'item': by_id[source_id] if source_id else None,
                'rewardType': 'item' if source_id else 'coins', 'quantity': quantity,
                'underfootOnly': underfoot, 'requiresItemfinder': underfoot,
            }
    if (maps_scanned, ball_count, len(pickups), len(hidden)) != (425, 178, 167, 183):
        raise ValueError(f'Unexpected FireRed field audit: {(maps_scanned, ball_count, len(pickups), len(hidden))}')
    if len({reward['sourceFlag'] for reward in hidden.values()}) != len(hidden):
        raise ValueError('Duplicate hidden source flags')
    audit = {
        'mapsScanned': maps_scanned, 'scannedPokeballObjects': ball_count,
        'verifiedPickups': len(pickups), 'hiddenRewards': len(hidden),
        'hiddenItems': sum(row['rewardType'] == 'item' for row in hidden.values()),
        'hiddenCoins': sum(row['rewardType'] == 'coins' for row in hidden.values()),
        'underfootItems': sum(row['underfootOnly'] for row in hidden.values()),
        'excludedBalls': excluded,
    }
    return pickups, hidden, map_flags, audit


def extract_icons(rom_path, root, items):
    # Kept out of the ordinary publisher: only extraction needs graphics libraries.
    try:
        from .extract_assets import Rom as GraphicsRom
    except ImportError:
        from extract_assets import Rom as GraphicsRom
    rom = GraphicsRom(rom_path)
    for item in items.values():
        source_id = item['sourceId']
        entry = ICON_TABLE + source_id * 8
        tiles, palette = rom.ptr(entry), rom.ptr(entry + 4)
        raw = rom.lz(tiles)
        if len(raw) != 288:
            raise ValueError('Native item icon has unexpected dimensions')
        output = root / 'Client/app/assets' / item['icon']
        output.parent.mkdir(parents=True, exist_ok=True)
        rom.sprite(raw, rom.palette(palette, True), 24, 24).save(output)
        item['native']['iconOffset'] = hex(tiles)
        item['native']['iconPaletteOffset'] = hex(palette)


def extract_layout_variants(rom_path, root, world):
    """Publish native postgame geometry where the baseline lacks script layouts.

    Three Isle Path's ordinary header intentionally points to its undug layout.
    Its native on-load script chooses layout 319 after the tunnel is completed.
    NXT exposes postgame maps without the original complete story interpreter,
    so this one reviewed layout is selected explicitly, with its original art.
    """
    import numpy as np
    from PIL import Image
    try:
        from .extract_assets import Rom as GraphicsRom
    except ImportError:
        from extract_assets import Rom as GraphicsRom
    rom = GraphicsRom(rom_path)
    map_id, layout_id, layout = 'kanto_2_34', 319, 0x345430
    if rom.ptr(0x34ebfc + (layout_id - 1) * 4) != layout or rom.raw(0x164dc8, 4) != bytes.fromhex('a73f0103'):
        raise ValueError('Three Isle Path native layout-switch references changed')
    width, height = rom.u32(layout), rom.u32(layout + 4)
    if (width, height) != (30, 7):
        raise ValueError('Expanded Three Isle Path dimensions changed')
    grid_pointer = rom.ptr(layout + 12)
    primary, secondary = rom.ptr(layout + 16), rom.ptr(layout + 20)
    grid = np.frombuffer(rom.raw(grid_pointer, width * height * 2), dtype='<u2').reshape(height, width)
    metatiles = grid & 1023
    tiles, attributes = rom.metatiles(primary, secondary)
    composite = tiles[metatiles].transpose(0, 2, 1, 3, 4).reshape(height * 16, width * 16, 4)
    ground = composite.copy()
    overlay = np.zeros_like(composite)
    for tile in np.unique(metatiles):
        if ((attributes[tile] >> 29) & 3) == 2:
            for yy, xx in np.argwhere(metatiles == tile):
                overlay[yy * 16:yy * 16 + 16, xx * 16:xx * 16 + 16] = rom.meta_upper[tile]
                ground[yy * 16:yy * 16 + 16, xx * 16:xx * 16 + 16] = rom.meta_lower[tile]
    paths = {'image': 'maps/kanto/2_34_expanded.png', 'ground': 'maps/kanto/2_34_expanded_ground.png', 'overlay': None}
    assets = root / 'Client/app/assets'
    Image.fromarray(composite).save(assets / paths['image'])
    Image.fromarray(ground).save(assets / paths['ground'])
    if overlay[:, :, 3].any():
        paths['overlay'] = 'maps/kanto/2_34_expanded_over.png'
        Image.fromarray(overlay).save(assets / paths['overlay'])
    fields = dict(paths, width=width, height=height,
                  collision=((grid >> 10) & 3).flatten().tolist(),
                  elevation=(grid >> 12).flatten().tolist(),
                  behavior=(attributes[metatiles] & 511).astype(int).flatten().tolist(),
                  sourceLayout=hex(layout), sourceLayoutId=layout_id,
                  layoutPolicy='nxt-postgame-access-native-expanded-layout')
    x, y = 21, 3
    if not any(fields['collision'][yy * width + xx] == 0 for xx, yy in ((x, y), (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)) if 0 <= xx < width and 0 <= yy < height):
        raise ValueError('Native expanded path does not expose its hidden Nugget')
    return {map_id: {'fields': fields,
                    'sourceLayoutTable': '0x34ebfc', 'sourceOnLoadScript': '0x164da4',
                    'sourceLayoutCommand': '0x164dc8', 'sourceGrid': hex(grid_pointer),
                    'policy': 'Use the original completed-tunnel layout for NXT postgame access. The native coordinates and metatiles are unmodified; no invented collision corridor is carved.'}}


def extract(rom_path, root=ROOT, icons=True):
    root = Path(root)
    rom = Rom(rom_path)
    if len(rom.b) != 16777216 or hashlib.sha256(rom.b).hexdigest() != SHA:
        raise ValueError('Unreviewed FireRed ROM revision')
    world = json.loads((root / 'Server/data/world.json').read_text(encoding='utf-8'))
    items, by_id, excluded = extract_catalog(rom)
    machines, species = extract_machines(rom, world, by_id)
    pickups, hidden, flags, audit = extract_fields(rom, world, by_id)
    result = {
        'format': 1, 'source': 'kanto', 'sourceSha256': SHA, 'sourceBytes': len(rom.b),
        'items': items, 'itemIds': {str(key): value for key, value in by_id.items()},
        'machines': machines, 'species': species, 'itemPickups': pickups,
        'evolutions': extract_evolutions(rom, world, by_id),
        'hiddenItemPickups': hidden, 'mapFlags': flags, 'audit': audit,
        'mapOverrides': extract_layout_variants(rom_path, root, world),
        'excludedCatalogSlots': excluded,
        'references': {
            'itemTable': hex(ITEM_TABLE), 'itemPointerOffset': '0x1c8',
            'itemIconTable': hex(ICON_TABLE), 'machineTable': hex(MACHINE_TABLE),
            'machinePointerOffsets': ['0x125b04', '0x125b24'],
            'compatibilityTable': hex(COMPATIBILITY_TABLE),
            'compatibilityPointerOffsets': ['0x43c7c', '0x43c94'],
            'formatDocumentation': 'https://github.com/pret/pokefirered/blob/master/include/global.fieldmap.h',
        },
        'policy': 'Native FireRed inventory identities are namespaced fr_ to preserve existing Sigma saves. All 425 Kanto and Sevii maps are audited. HMs are excluded. Hidden coins, quantities and underfoot-only Itemfinder rewards retain their packed source semantics. NPC scripts are statically audited; only explicitly supported acquisition conditions are published.',
    }
    if icons:
        extract_icons(rom_path, root, items)
    gift_file = root / 'Tools/extract_kanto_gifts.py'
    if gift_file.exists():
        try:
            from .extract_kanto_gifts import extract_gifts
        except ImportError:
            from extract_kanto_gifts import extract_gifts
        result['scriptGifts'] = extract_gifts(rom, world, by_id)
    output = root / 'Server/data/kanto_items.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Extracted {len(items)} FireRed items, {len(machines)} TMs, {len(species)} compatibility profiles, {len(pickups)} visible and {len(hidden)} hidden rewards across {len(flags)} maps.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--no-icons', action='store_true')
    args = parser.parse_args()
    extract(args.rom, args.root, not args.no_icons)
