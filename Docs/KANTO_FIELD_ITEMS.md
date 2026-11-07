# Kanto field item guide and implementation scope

The server owns item quantities, field progress, encounter selection, and all
service prices. Item use is saved as one transaction. A failed eligibility,
location, capacity, or currency check leaves the original character unchanged.

## Field actions

| Item or action | How to use it |
| --- | --- |
| Bicycle | Use it from the Bag on a map whose FireRed header permits cycling. Use it again to dismount. Entering a prohibited map or enabling Surf dismounts automatically. |
| Old, Good, or Super Rod | Face an adjacent water tile and use the rod. Each rod selects only its own ordered FireRed slots and native level ranges. A healthy party is required. |
| Itemfinder | Use it to receive a direction toward a nearby uncollected hidden item. Search the tile underfoot with the Itemfinder for the special rewards that require it, including both Snorlax Leftovers. |
| Poké Flute | Use it beside a sleeping Route 12 or Route 16 Snorlax to start its level-30 encounter. Its normal party and battle sleep-curing functions remain available. |
| Card Key | Face a locked Silph Co. door and use the key. Its native door tiles open for your character and stay open after reconnecting. |
| Lift Key | Enter the Rocket Hideout elevator. Select B1F, B2F, or B4F from the Lift Key’s Bag action, then walk out of the lift. These are the cartridge’s three destinations; B3F has no lift stop. |
| Secret Key | Carry it when entering the Cinnabar Gym. The key is reusable. |
| S.S. Ticket | Carry it when boarding the S.S. Anne through Vermilion’s harbor. The ticket is reusable. |
| Bike Voucher | Stand beside the clerk in Cerulean’s Bike Shop and use the voucher to receive the Bicycle. |
| Oak’s Parcel | Use it beside Professor Oak in his Pallet lab. The delivery records the native Pokédex progression and awards five FireRed Poké Balls atomically. |
| Gold Teeth | Return them to the Warden in his Fuchsia house using the Bag. The native handover is saved. The HM reward is excluded from this update. |
| Tea | Use it beside any of the four Saffron gate guards. The native shared gate state opens all four gates. |
| Ruby / Sapphire | The Celio NPC exchange handles the Ruby and Rainbow Pass. Use the Sapphire beside Celio after that exchange to complete the Network Machine story state. |
| Black / White Flute | Use the flute to change the walking encounter rate. Neither consumes the flute. |
| VS Seeker | Walk 100 successful tile steps, then use it outdoors near trainers you have already defeated. Speak to a responding trainer before leaving the map to start a rewarded rematch. |

The Pokémon Mansion’s statue switches are also active. Face a statue switch and
press the normal interaction key. The shared native switch flag changes the
correct doors on all four Mansion floors. Opening one set closes the other;
collision and the selected native artwork use the same saved state. Rocket
Hideout’s Giovanni-office door opens after defeating both of its native guards.

## Fossil revival

Take a Helix Fossil, Dome Fossil, or Old Amber to the scientist in the last room
of Cinnabar’s Pokémon Lab. Stand beside him and use the fossil from the Bag.
Leave that room and return, then choose **Collect revived Pokémon** in his
dialogue. The result is a level-5 Omanyte, Kabuto, or Aerodactyl, respectively.
Collection waits safely if Pokémon storage is full. Hoenn’s Root and Claw
Fossils are not accepted by this FireRed scientist.

## Celadon coins and prizes

Buy 50 coins for ₽1,000 or 500 for ₽10,000 beside the coin seller in Celadon Game
Corner. The Coin Case holds 9,999 coins. The three counters in the separate
prize exchange use the cartridge’s exact item/species identities, prices, and
Pokémon levels. The Bag shows only the appropriate nearby service as available.

The Pokémon prizes are Abra (180 coins, level 9), Clefairy (500, level 8),
Dratini (2,800, level 18), Scyther (5,500, level 25), and Porygon (9,999, level
26). The five TM prizes and five held-item/flute prizes are read directly from
their FireRed event commands. Money, coins, prizes, and storage additions are
committed together.

## Powder Jar

The Powder Jar displays the saved Berry Powder balance. The Berry Powder man
in Cerulean City exchanges that balance for the eleven medicines at their
native prices: EnergyPowder 50, Energy Root 80, Heal Powder 50, Revival Herb
300, each vitamin 1,000, and PP Up 3,000 units. An insufficient balance cannot
spend an item or award medicine.

**Berry Crush’s linked multiplayer minigame is not implemented.** This release
does not fabricate a powder-earning recipe or an alternative currency source.
Existing/imported powder balances can use the native exchange. The Bag states
this limitation, so a new zero-balance character is not promised an unavailable
way to earn powder.

## Adaptations and remaining limits

- Fishing starts the selected native encounter immediately. The cartridge’s
  timing and button-press minigame is not recreated.
- The VS Seeker has its 100-step recharge and spatial restrictions. Its
  responders are deterministic and use the currently published trainer team.
  Cartridge response odds and later upgraded rematch-team tiers are not
  implemented. Eligible rematches receive the MMO’s existing EXP/reward rules.
- Celadon’s native coin purchase and prize exchange are implemented; the slot
  machine gambling minigame is not.
- The Town Map uses the Atlas, TM Case and Berry Pouch use Bag pockets, Fame
  Checker uses the Adventure Journal, and Teachy TV uses the game’s help.
  Cartridge cutscenes, recorded biographies, and tutorials are not emulated.
- Ruby/Sapphire handovers save their native completion flags. This MMO already
  owns its networking and regional trading; it does not emulate GBA link-cable
  hardware.
- ROM item-table entries used only in Ruby/Sapphire locations do not gain
  invented Kanto services. Mystery-event transport and their event tickets
  need the corresponding authored travel/story implementation; they are not
  unrestricted teleports.
- HMs remain outside this item update, as requested.

## Reproducible data and checks

`Tools/extract_kanto_field_services.py` accepts only the reviewed FireRed Rev 1
ROM SHA-256 recorded in the project. It validates exact native script operand
signatures and writes `Server/data/kanto_field_services.json` without executing
ROM code. The sidecar contains twenty Card Key doors, all four Mansion switch
states, the Rocket guard door, three lift destinations, fifteen coin prizes,
eleven powder medicines, three fossil recipes, and native handover evidence.
The publisher adds this sidecar to the world data; a separate graphics
extractor renders the referenced native tile variants.

Run `python -m unittest Tests.test_kanto_field -v` for focused regression tests
covering native rod partitions, owner-only doors, reversible Mansion switches,
lift destination validation, fossil handover and collection, exact native
prizes, atomic currency checks, key entrances, Itemfinder collection, story
handovers, VS Seeker recharge, and the powder exchange.
