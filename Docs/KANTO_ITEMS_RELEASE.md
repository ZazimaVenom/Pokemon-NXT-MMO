# Pokémon NXT MMO 0.6.11-alpha — FireRed Kanto items

This source release extends the supplied 0.6.10-alpha baseline. All four source
archives must be extracted into the same directory; they contain complementary
files, not four standalone builds. Run `BUILD_ALL.bat` from the combined source
folder on Windows. Ordinary builds use the included extracted assets and do not
need the ROM. Keep the existing server configuration and database. Deploy a
matching server and client content pack together.

## What is implemented

- Audits all 425 Kanto/Sevii map records against the supplied FireRed Rev 1 ROM.
  Binds 167 ordinary visible item balls and 183 hidden reward events (171 item
  caches and 12 coin caches), with original positions, quantities and flags.
  Conditional ground gifts are handled through the NPC reward service. HMs
  are excluded from the native Kanto item catalog.
- Adds 299 named native non-HM item definitions and their native icons. This
  number includes dormant Hoenn records carried in FireRed; it is not a claim
  that 299 different items are normally obtainable in a FireRed playthrough.
- Publishes all 50 FireRed TMs with native move assignments and 386 native
  compatibility profiles. Native stones, held items, berries, medicines, PP
  items, vitamins, balls and battle items use source-specific authoritative
  rules. Existing Johto/Sigma items retain their previous identities.
- Adds native shop stock by clerk, NPC rewards and exchanges, private collection
  flags, chosen party targets, no-effect rejection, persisted action receipts,
  and atomic inventory/effect updates. Bags are not changed optimistically.
  The TM Case and Berry Pouch are acquired automatically with the first native
  TM or Berry, and their history persists after those consumables are used;
  Powder Jar eligibility remains unlocked after using the final Berry.
  All 73 extracted acquisition identities are accounted for by 52 approved
  gifts, 10 Game Corner item prizes and 11 Berry Powder exchanges.
- Supports fishing with the three native rod pools, Itemfinder searches,
  Repels, Escape Rope map permissions, cycling, fossil revival, Coin Case
  prizes, Card Key doors, Mansion switches, Rocket lift floors and story
  handovers. Native door/switch images change along with their collision.
- Implements Safari admission, 30 session-only Safari Balls, a 600-step budget,
  native bait/rock/capture/flee mechanics and cleanup on departure. Safari
  encounters do not attack the trainer's party.
- Makes native boulders pushable and breakable rocks clearable through Kanto
  badge field licenses, without granting HM inventory. Boulders reset on leaving
  the map; rock clearing is private and saved, as with existing NXT Cut.
- Rebuilds the Bag with pocket navigation, source icons, search, sorting,
  item details, move information, contextual actions, held Mail, keyboard
  navigation, preserved selection/focus and responsive styles.

## Controls

Press **B** for the Bag. Select an item, then choose its contextual action.
Medicines, held items and TMs ask for a compatible party Pokémon; moves and
replacements require explicit selection. Press **E** while facing a hidden
item tile or a native switch. The six special underfoot caches require using
Itemfinder while standing on their tile. Ordinary visible balls remain
clickable. Rewards, doors and collected objects are private to each character.

Talk to the original reward NPC to receive gifts. A disabled reward explains
its current prerequisite. Aides count distinct caught species. Fossil choices
are mutually exclusive, and a Bike Voucher is consumed only when the Bicycle
is successfully received. After leaving the fossil lab and returning, speak
to the scientist to collect the revived Pokémon.

## Exactness and remaining boundaries

This is a native-data implementation within NXT's existing MMO engine, not a
complete FireRed event-script emulator. The acquisition audit and field guide
identify the differences instead of presenting them as cartridge parity:

- Some unavailable story cutscenes use explicit badge, recorded trainer-win,
  item-delivery or gift-receipt prerequisites. See each acquisition's
  `adaptation` in `KANTO_ITEM_COVERAGE.json` and `nxt/kanto_gifts.py`.
- NXT publishes the real completed Three Isle tunnel layout so its native
  Nugget is reachable in the already-accessible postgame area.
- Fishing uses the native rod species/level slots, with immediate hooking;
  the timed bite input sequence is not reproduced. VS Seeker uses a
  100-step charge and published trainer teams; original random response and
  progressing rematch team tiers are not reproduced.
- Powder Jar acquisition, balance and native medicine exchange prices exist.
  The multiplayer Berry Crush minigame and natural powder earning do not.
  No invented powder recipe or reward is substituted. Game Corner coin
  purchases and prizes work; slot-machine gambling is not implemented.
- Event-distribution ticket transport and complete Fame Checker/Teachy TV
  scenes remain outside the engine. The latter open the existing journal
  and help interfaces. Hoenn-only dormant catalog keys do not gain invented
  Kanto services. These are limits to the requested full cartridge parity.
- Existing NXT inventory stack limits, trading, badge licenses and authored
  trainer prize rules remain MMO policies. This release does not claim a
  cycle-accurate recreation of all GBA interactions.

## Verification

See `KANTO_ITEMS_TEST_REPORT.md` for the checks actually executed. Browser
preview was blocked by the environment's unavailable approval/security check;
no screenshot or Windows/Edge visual acceptance is claimed. The source build
and controls still require normal native Windows acceptance before a live
production rollout.

Reproduction and detailed native evidence: `KANTO_ITEMS_AUDIT.md`,
`KANTO_FIELD_ITEMS.md`, and `KANTO_ITEM_COVERAGE.json`.
