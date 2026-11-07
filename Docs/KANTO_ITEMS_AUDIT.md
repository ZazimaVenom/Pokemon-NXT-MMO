# FireRed inventory and map extraction

The accepted input is the supplied **Pokémon FireRed USA/Europe Rev 1** ROM:

* Size: 16,777,216 bytes.
* SHA-256: `729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059`.
* Build-time extractor: `Tools/extract_kanto_items.py`.
* Reproducible sidecar: `Server/data/kanto_items.json`.
* ROM-free publisher: `Tools/publish_kanto_items.py`.

The running server and client do not read or execute a ROM. Native FireRed items
use `fr_` inventory keys. Existing Sigma keys, quantities, and held-item source
identities remain separate. For example, FireRed item 44 is Berry Juice; Sigma
item 44 is Up-Grade. Sharing that numeric ID would corrupt their meaning.

## Coverage

| Extracted record | Count |
| --- | ---: |
| Kanto and Sevii maps audited | 425 |
| Named native item records, excluding HMs | 299 |
| Native item icons | 299 |
| FireRed TMs | 50 |
| Native species compatibility profiles | 386 |
| Standard visible item pickups | 167 |
| Hidden inventory item caches | 171 |
| Hidden Coin Case coin caches | 12 |
| Hidden caches requiring an underfoot Itemfinder search | 6 |
| Native Poké Mart clerk stock lists | 20 |

The catalog also preserves named native records that FireRed itself does not
normally distribute, such as Hoenn-only key items. A native catalog record does
not imply an invented field placement or an invented Hoenn service in Kanto.

All 178 Poké Ball graphics actors are accounted for:

* 167 ordinary inventory pickups are bound to their original map object IDs,
  coordinates, script commands, quantities, and persistence flags.
* The Icefall Cave HM07 pickup is excluded by scope.
* Rocket Hideout's Lift Key and Silph Scope use the scripted gift service.
* Eight actors are Pokémon rather than inventory: three Oak starter choices,
  Eevee, two Fighting Dojo choices, and two Power Plant wild Pokémon decoys.

The six underfoot caches are Soothe Bell, Sacred Ash, two Leftovers, PP Max,
and Macho Brace. Their packed quantity high bit is a placement requirement,
not an extra 128 items. Coin caches use source item ID zero and award their
native quantity to the Coin Case, never a fake inventory item.

## Validated source tables

| Data | ROM offset | Active reference |
| --- | --- | --- |
| Item records, 44 bytes each | `0x3db098` | pointer at `0x1c8` |
| Item icon and palette pointers | `0x3d4304` | each icon and palette decompresses and validates |
| TM/HM move table | `0x45a86c` | pointers at `0x125b04`, `0x125b24` |
| TM/HM compatibility bitsets | `0x252c38` | pointers at `0x43c7c`, `0x43c94` |
| Evolution records | `0x2597c4` | five eight-byte entries per native species |

The earlier duplicate TM table at `0x45a604` is not the active referenced table.
All 50 published TMs point to the native FireRed move definitions, and each
species retains its exact native compatibility bits. HMs and their compatibility
bits are not published as Kanto inventory entries.

Item records preserve the native description, pocket, importance, price, held
effect and parameter, field function, battle function, battle usage, and
secondary ID. Species records additionally preserve their two native held-item
slots and Safari flee rate. Native map headers supply bicycle, running, and
Escape Rope permissions.

Three Isle Path has two native layouts. Its default header uses the undug
layout, while its on-load story script can select completed-tunnel layout 319.
For NXT's already-accessible postgame maps, publication explicitly selects the
original completed-tunnel layout and extracts its matching art and collision
grids. The hidden Nugget retains its native coordinate `(21, 3)` and becomes
approachable from `(20, 3)`. This adaptation is identified in `mapOverrides`;
no artificial passage or relocated reward is introduced.

`Tools/extract_kanto_field_tiles.py` also extracts the original replacement
metatiles used when Card Key doors, Rocket Hideout doors, and Mansion switches
change state. The resulting 102 metatiles across 15 maps supply matching
per-player graphics alongside collision changes. Their tileset pointers and
native layer attributes are retained in `kanto_field_tiles.json`.

## Scripted rewards and rebuilds

`Tools/extract_kanto_gifts.py` follows bounded, decoded script control flow and
records item grants, prerequisite checks, consumed items, source flags, and
shop commands. Its candidates are an audit: they are not automatically turned
into unconditional rewards. `Server/nxt/kanto_gifts.py` implements reviewed
acquisition rules and documents the NXT adaptations needed where the baseline
does not run FireRed's complete story-script interpreter.

`Tools/extract_kanto_field_services.py` separately verifies service data such
as Game Corner prize costs and fossil conversion operands. Source offsets and
the input digest remain available in the service sidecar.

Re-extract with:

```sh
python Tools/extract_kanto_items.py /path/to/firered-rev1.gba
python Tools/extract_kanto_field_services.py /path/to/firered-rev1.gba
python Tools/extract_kanto_field_tiles.py /path/to/firered-rev1.gba
```

Then rebuild matching server and client packs with:

```sh
python Tools/repack_content.py
python Tools/verify_kanto_items.py
```

The publisher runs after the original Sigma publication stages, preserves
source namespaces, validates map-object bindings, and produces release
`0.6.11-alpha`. Repeating those assembly stages is deterministic.

Native map-event layouts and packed hidden-item fields were cross-checked with
the [pret FireRed map definitions](https://github.com/pret/pokefirered/blob/master/include/global.fieldmap.h)
and [field interaction implementation](https://github.com/pret/pokefirered/blob/master/src/field_control_avatar.c).
