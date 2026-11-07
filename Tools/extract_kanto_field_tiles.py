#!/usr/bin/env python3
"""Extract native replacement metatile art for private Kanto door/switch states."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .extract_assets import Rom
except ImportError:
    from extract_assets import Rom

ROOT = Path(__file__).resolve().parents[1]
SHA = '729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059'


def extract(rom_path, root=ROOT):
    from PIL import Image
    root = Path(root)
    rom = Rom(rom_path)
    if len(rom.b) != 16777216 or hashlib.sha256(rom.b).hexdigest() != SHA:
        raise ValueError('Unreviewed FireRed ROM revision')
    services = json.loads((root / 'Server/data/kanto_field_services.json').read_text(encoding='utf-8'))
    world = json.loads((root / 'Server/data/world.json').read_text(encoding='utf-8'))
    if services.get('sourceSha256') != SHA:
        raise ValueError('Unreviewed field service source')
    required = {}
    for row in services.get('doors', []) + services.get('trainerDoors', []):
        required.setdefault(row['map'], set()).update(tile['metatile'] for tile in row.get('openTiles', []))
    for row in services.get('mansionSwitches', []):
        required.setdefault(row['map'], set()).update(tile['metatile'] for state in ('on', 'off') for tile in row[state])
    by_map = {}
    references = {}
    assets = root / 'Client/app/assets'
    for map_id, ids in sorted(required.items()):
        if not ids:
            continue
        header = int(world['maps'][map_id]['sourceHeader'], 16)
        layout = rom.ptr(header)
        primary, secondary = rom.ptr(layout + 16), rom.ptr(layout + 20)
        composite, attributes = rom.metatiles(primary, secondary)
        references[map_id] = {'header': hex(header), 'layout': hex(layout),
                              'primaryTileset': hex(primary), 'secondaryTileset': hex(secondary)}
        entries = {}
        for metatile in sorted(ids):
            if not 0 <= metatile < 1024:
                raise ValueError('Native replacement metatile exceeds tileset')
            stem = f'world/field_tiles/{map_id}/{metatile}'
            image_path, ground_path = stem + '.png', stem + '_ground.png'
            (assets / image_path).parent.mkdir(parents=True, exist_ok=True)
            layer = int((attributes[metatile] >> 29) & 3)
            ground = rom.meta_lower[metatile] if layer == 2 else composite[metatile]
            Image.fromarray(composite[metatile]).save(assets / image_path)
            Image.fromarray(ground).save(assets / ground_path)
            overlay_path = None
            if layer == 2 and rom.meta_upper[metatile][:, :, 3].any():
                overlay_path = stem + '_over.png'
                Image.fromarray(rom.meta_upper[metatile]).save(assets / overlay_path)
            entries[str(metatile)] = {'image': image_path, 'ground': ground_path,
                                      'overlay': overlay_path, 'layerType': layer,
                                      'metatile': metatile, 'width': 16, 'height': 16}
        by_map[map_id] = entries
    result = {'format': 1, 'sourceSha256': SHA, 'byMap': by_map, 'references': references,
              'policy': 'Exact native FireRed metatile art for server-selected private map state. Draw the selected ground before actors, suppress the old baked overlay within each replacement tile, then draw the selected native overlay after actors.',
              'audit': {'maps': len(by_map), 'metatiles': sum(len(rows) for rows in by_map.values()),
                        'groundImages': sum(len(rows) for rows in by_map.values()),
                        'overlayImages': sum(bool(row['overlay']) for rows in by_map.values() for row in rows.values())}}
    output = root / 'Server/data/kanto_field_tiles.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Extracted Kanto field-state graphics:', result['audit'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    extract(args.rom, args.root)
