"""Publish the reviewed FireRed sidecar into matching server/client content.

This runs after the original Sigma publishers. Existing save keys and source
identities stay intact; native FireRed items use an independent fr_ namespace.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

SHA = '729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059'


def assemble(world, root):
    root = Path(root)
    native = json.loads((root / 'Server/data/kanto_items.json').read_text(encoding='utf-8'))
    if native.get('format') != 1 or native.get('sourceSha256') != SHA:
        raise ValueError('Unreviewed FireRed inventory sidecar')
    sys.path.insert(0, str(root / 'Server'))
    try:
        from nxt.items import kanto_item_rule
    finally:
        sys.path.pop(0)
    ids = {}
    for key, record in native['items'].items():
        if not key.startswith('fr_') or record.get('source') != 'kanto':
            raise ValueError('Invalid native item namespace: ' + key)
        sid = record['sourceId']
        if sid in range(339, 347) or sid in ids:
            raise ValueError('HM or duplicate source identity in Kanto catalog')
        ids[sid] = key
        item = copy.deepcopy(record)
        item['mechanics'] = kanto_item_rule(item, native['machines'].get(key))
        if 'capture' in item['mechanics']:
            item['capture'] = item['mechanics']['capture']
        if 'heal' in item['mechanics']:
            item['heal'] = item['mechanics']['heal']
        if not (root / 'Client/app/assets' / item['icon']).is_file():
            raise ValueError('Missing FireRed item icon: ' + key)
        world['items'][key] = item
    for key, profile in native['species'].items():
        target = world['species'].get(key)
        if not target or target.get('source') != 'kanto' or target.get('sourceId') != profile['sourceId']:
            raise ValueError('Kanto machine species binding changed: ' + key)
        target['machines'] = list(dict.fromkeys(target.get('machines', []) + profile['machines']))
        target['kantoHeldItems'] = copy.deepcopy(profile['heldItems'])
        target['heldItems'] = [row['sourceId'] for row in profile['heldItems']]
        target['safariFleeRate'] = profile['safariFleeRate']
        target['evYield'] = list(profile['evYield'])
        target['baseFriendship'] = profile['baseFriendship']
    for key, flags in native['mapFlags'].items():
        if key not in world['maps']:
            raise ValueError('Unknown FireRed map permission: ' + key)
        for field in ('escapeAllowed', 'bicycleAllowed', 'runningAllowed'):
            world['maps'][key][field] = flags[field]
    for key, variant in native.get('mapOverrides', {}).items():
        data = world['maps'].get(key)
        if not data or key != 'kanto_2_34' or variant['fields'].get('sourceLayoutId') != 319:
            raise ValueError('Unreviewed native map layout override: ' + key)
        data.update(copy.deepcopy(variant['fields']))
    adventure = world['adventureRom']
    for key, reward in native['itemPickups'].items():
        data = world['maps'].get(reward['map'])
        obj = next((obj for obj in data.get('objects', []) if obj['id'] == reward['npc']), None) if data else None
        if not obj or obj.get('graphics') != 92 or [obj['x'], obj['y']] != [reward['x'], reward['y']] or obj.get('sourceObjectIndex') != reward['sourceObjectIndex']:
            raise ValueError('FireRed field item object binding changed: ' + key)
        if reward['item'] not in world['items'] or reward['quantity'] < 1:
            raise ValueError('FireRed field award missing catalog identity: ' + key)
        obj['itemPickup'] = key
        adventure.setdefault('itemPickups', {})[key] = copy.deepcopy(reward)
    adventure['hiddenItemPickups'] = copy.deepcopy(native['hiddenItemPickups'])
    for data in world['maps'].values():
        if data['id'].startswith('kanto_'):
            # Coordinates are private discovery targets: clients receive them
            # for local interaction, but no visual sprite is ever attached.
            data['hiddenItems'] = [copy.deepcopy(row) for row in native['hiddenItemPickups'].values() if row['map'] == data['id']]
    for key, entries in native.get('evolutions', {}).items():
        adventure['evolutions'][key] = copy.deepcopy(entries)
    adventure.setdefault('evolutionsBySource', {})['kanto'] = copy.deepcopy(native.get('evolutions', {}))
    adventure['kantoItemAudit'] = copy.deepcopy(native['audit'])
    adventure['kantoScriptGiftAudit'] = copy.deepcopy(native.get('scriptGifts', {}))
    marts = native.get('scriptGifts', {}).get('marts', {})
    adventure['kantoMarts'] = copy.deepcopy(marts)
    for mart in marts.values():
        for item_key in mart.get('items', []):
            if item_key not in world['items']:
                raise ValueError('Mart inventory references missing item: ' + item_key)
            world['items'][item_key]['buyable'] = True
    world['kantoItems'] = {
        'format': 1, 'sourceSha256': SHA, 'catalogItems': len(native['items']),
        'machines': len(native['machines']), 'mapsScanned': len(native['mapFlags']),
        'visiblePickups': len(native['itemPickups']), 'hiddenRewards': len(native['hiddenItemPickups']),
        'hmPolicy': 'excluded', 'namespace': 'fr_',
    }
    services_path = root / 'Server/data/kanto_field_services.json'
    if services_path.is_file():
        services = json.loads(services_path.read_text(encoding='utf-8'))
        if services.get('sourceSha256') != SHA:
            raise ValueError('Unreviewed Kanto field service sidecar')
        world['kantoFieldServices'] = services
        tile_path = root / 'Server/data/kanto_field_tiles.json'
        if tile_path.is_file():
            tiles = json.loads(tile_path.read_text(encoding='utf-8'))
            if tiles.get('sourceSha256') != SHA or tiles.get('format') != 1:
                raise ValueError('Unreviewed Kanto field-state graphics')
            for map_id, entries in tiles['byMap'].items():
                if map_id not in world['maps']:
                    raise ValueError('Native field graphics reference an unknown map')
                for entry in entries.values():
                    for field in ('image', 'ground', 'overlay'):
                        if entry[field] and not (root / 'Client/app/assets' / entry[field]).is_file():
                            raise ValueError('Missing native field-state graphics')
                world['maps'][map_id]['fieldTiles'] = copy.deepcopy(entries)
            for row in services.get('doors', []) + services.get('trainerDoors', []):
                for tile in row.get('openTiles', []):
                    art = tiles['byMap'].get(row['map'], {}).get(str(tile['metatile']))
                    if not art:
                        raise ValueError('Missing native door replacement art')
                    tile.update(ground=art['ground'], overlay=art['overlay'])
            for row in services.get('mansionSwitches', []):
                for state in ('on', 'off'):
                    for tile in row[state]:
                        art = tiles['byMap'].get(row['map'], {}).get(str(tile['metatile']))
                        if not art:
                            raise ValueError('Missing native Mansion replacement art')
                        tile.update(ground=art['ground'], overlay=art['overlay'])
            services['nativeTileGraphics'] = copy.deepcopy(tiles['audit'])
    # The source game requires the Poké Flute, with no badge gate, to wake
    # either Snorlax. Battles reuse the existing private persistent story flow.
    events = world['adventure'].setdefault('storyEvents', [])
    events[:] = [row for row in events if not row['id'].startswith('fr_snorlax_')]
    for suffix, map_id, npc in [('route12', 'kanto_3_30', 5), ('route16', 'kanto_3_34', 10)]:
        obj = next((row for row in world['maps'][map_id]['objects'] if row['id'] == npc), None)
        if not obj or obj['graphics'] != 109:
            raise ValueError('Snorlax native actor binding changed: ' + map_id)
        event_id = 'fr_snorlax_' + suffix
        obj['storyEvent'] = event_id
        events.append({'id': event_id, 'title': 'The sleeping Snorlax', 'map': map_id,
                       'npc': npc, 'graphics': obj['graphics'], 'species': 'fr_143', 'level': 30,
                       'variety': 'normal', 'requiredItem': 'fr_pokeflute', 'itemName': 'Poké Flute',
                       'awardItemOnBadge': False, 'description': 'Play the Poké Flute to wake the sleeping Snorlax.',
                       'moves': [29, 281, 156, 173]})
    world['version'] = '0.6.12-alpha'
    return native
