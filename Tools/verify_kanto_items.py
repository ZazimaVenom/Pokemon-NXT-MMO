#!/usr/bin/env python3
"""Check published Kanto inventory parity and write deterministic coverage data."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT, write=True):
    root = Path(root)
    def read(path):
        return json.loads((root / path).read_text(encoding='utf-8'))
    native = read('Server/data/kanto_items.json')
    world = read('Server/data/world.json')
    client = read('Client/app/assets/world/client.json')
    if world['pack'] != client['pack'] or world['version'] != '0.6.12-alpha':
        raise ValueError('Rebuild matching 0.6.12-alpha server/client packs first')
    if set(native['mapFlags']) != {key for key in world['maps'] if key.startswith('kanto_')}:
        raise ValueError('Kanto map audit coverage is incomplete')
    icon_digest = hashlib.sha256()
    for key, source in native['items'].items():
        item = world['items'].get(key)
        if not item or item != client['items'].get(key):
            raise ValueError('Server/client item parity mismatch: ' + key)
        if item.get('source') != 'kanto' or item.get('sourceId') != source['sourceId']:
            raise ValueError('Native inventory identity changed: ' + key)
        for field, value in source.items():
            if field != 'buyable' and item.get(field) != value:
                raise ValueError('Native item metadata differs from current extraction: ' + key + ': ' + field)
        if item['sourceId'] in range(339, 347) or not item.get('mechanics', {}).get('effect'):
            raise ValueError('HM or missing item action contract: ' + key)
        icon = root / 'Client/app/assets' / item['icon']
        icon_digest.update(item['icon'].encode())
        icon_digest.update(hashlib.sha256(icon.read_bytes()).digest())
    for key, reward in native['itemPickups'].items():
        if world['adventureRom']['itemPickups'].get(key) != reward:
            raise ValueError('Published visible award differs from source: ' + key)
        data = world['maps'][reward['map']]
        obj = next((row for row in data['objects'] if row['id'] == reward['npc']), None)
        if not obj or obj.get('itemPickup') != key:
            raise ValueError('Missing native pickup object binding: ' + key)
    if world['adventureRom'].get('hiddenItemPickups') != native['hiddenItemPickups']:
        raise ValueError('Published hidden awards differ from the native sidecar')
    if world['adventureRom'].get('kantoScriptGiftAudit') != native.get('scriptGifts', {}):
        raise ValueError('Published scripted acquisition audit is stale')
    services = read('Server/data/kanto_field_services.json')
    def without_art(value):
        if isinstance(value, list):
            return [without_art(row) for row in value]
        if isinstance(value, dict):
            return {key: without_art(row) for key, row in value.items() if key not in ('ground', 'overlay', 'nativeTileGraphics')}
        return value
    if without_art(world.get('kantoFieldServices', {})) != without_art(services):
        raise ValueError('Published Kanto field services differ from current extraction; repack first')
    tiles = read('Server/data/kanto_field_tiles.json')
    for map_id, entries in tiles['byMap'].items():
        if world['maps'][map_id].get('fieldTiles') != entries:
            raise ValueError('Native field-state graphics have not been published: ' + map_id)
    for map_id, flags in native['mapFlags'].items():
        data = world['maps'][map_id]
        exported = read(f'Client/app/assets/world/maps/{map_id}.json')
        for field in ('collision', 'elevation', 'behavior', 'objects', 'hiddenItems', 'fieldTiles', 'image', 'ground', 'overlay'):
            if data.get(field) != exported.get(field):
                raise ValueError(f'Server/client map mismatch: {map_id}: {field}')
        for field in ('escapeAllowed', 'bicycleAllowed', 'runningAllowed'):
            if data.get(field) != flags[field]:
                raise ValueError('Native map item permission changed: ' + map_id)
    for species, source in native['species'].items():
        actual = {key for key in world['species'][species].get('machines', []) if key.startswith('fr_')}
        if actual != set(source['machines']):
            raise ValueError('Native TM compatibility changed: ' + species)
        for field in ('evYield', 'safariFleeRate', 'baseFriendship'):
            if world['species'][species].get(field) != source[field]:
                raise ValueError('Native item-related species field changed: ' + species + ': ' + field)
        if world['species'][species].get('heldItems') != [row['sourceId'] for row in source['heldItems']]:
            raise ValueError('Native wild held-item slots changed: ' + species)
    sys.path.insert(0, str(root / 'Server'))
    try:
        from nxt.content import Content
        from nxt.kanto_gifts import audit as gift_audit
        gifts = gift_audit(Content(root / 'Server/data/world.json'))
    finally:
        sys.path.pop(0)
    acquisition = collections.defaultdict(set)
    for row in native['itemPickups'].values():
        acquisition[row['item']].add('visible-field')
    for row in native['hiddenItemPickups'].values():
        if row['item']:
            acquisition[row['item']].add('hidden-field')
    for row in native.get('scriptGifts', {}).get('candidates', []):
        key = native['itemIds'].get(str(row['sourceItemId']))
        if key:
            acquisition[key].add('audited-script-candidate')
    for row in native.get('scriptGifts', {}).get('marts', {}).values():
        for key in row['items']:
            acquisition[key].add('native-mart')
    for row in native['species'].values():
        for held in row['heldItems']:
            if held['item']:
                acquisition[held['item']].add('native-held-species')
    hoenn_keys = {259, 266, *range(268, 289)}
    report = {
        'format': 1, 'version': world['version'], 'pack': world['pack'],
        'sourceSha256': native['sourceSha256'], 'checks': 'passed',
        'mapsAudited': len(native['mapFlags']), 'nativeInventoryRecords': len(native['items']),
        'inventoryPockets': dict(sorted(collections.Counter(row['pocketName'] for row in native['items'].values()).items())),
        'nativeIcons': len(native['items']), 'iconDigest': icon_digest.hexdigest(),
        'machines': len(native['machines']), 'compatibilityProfiles': len(native['species']),
        'visiblePickups': len(native['itemPickups']),
        'hiddenItemCaches': native['audit']['hiddenItems'], 'hiddenCoinCaches': native['audit']['hiddenCoins'],
        'underfootItemfinderCaches': native['audit']['underfootItems'],
        'ballActorsAccountedFor': native['audit']['scannedPokeballObjects'],
        'ballActorExceptions': native['audit']['excludedBalls'],
        'nativeMartClerks': len(native.get('scriptGifts', {}).get('marts', {})),
        'nativeFieldStateGraphics': world.get('kantoFieldServices', {}).get('nativeTileGraphics', {}),
        'scriptAudit': native.get('scriptGifts', {}).get('audit', {}),
        'giftRuntime': gifts,
        'acquisitionEvidence': {key: sorted(value) for key, value in sorted(acquisition.items())},
        'catalogWithoutAuditedAcquisition': [dict(item=key, sourceId=row['sourceId'], name=row['name']) for key, row in native['items'].items() if key not in acquisition],
        'hoennCarryoverKeyRecords': [dict(item=key, sourceId=row['sourceId'], name=row['name']) for key, row in native['items'].items() if row['sourceId'] in hoenn_keys],
        'nativeLayoutAdapters': {key: {field: value for field, value in row.items() if field != 'fields'} for key, row in native.get('mapOverrides', {}).items()},
        'parityChecks': ['server/client inventory', 'all Kanto map geometry and object bindings',
                        'hidden awards and native quantities', 'all native TM compatibility bits',
                        'native held slots, EV yields and Safari flee rates',
                        'HM exclusion', 'native icon files', 'map item permissions'],
        'policy': 'Coverage verifies published data and source bindings. Runtime and transaction behavior is covered separately by the Kanto item, gift, field-service and Safari tests. Catalog presence does not fabricate native acquisition routes for unused Hoenn carryover items.',
    }
    if write:
        (root / 'Docs/KANTO_ITEM_COVERAGE.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    report = verify(args.root)
    print(json.dumps({key: report[key] for key in ('pack', 'checks', 'mapsAudited', 'nativeInventoryRecords', 'visiblePickups', 'hiddenItemCaches', 'hiddenCoinCaches')}, indent=2))
