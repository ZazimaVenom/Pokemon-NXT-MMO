# Regional Surf — 0.6.12-alpha

Surf uses a regional badge and a Water-type Pokémon in your active party.
You do not need an HM item, to teach Surf, or to replace a battle move.

| Region being explored | Required victory | Badge |
| --- | --- | --- |
| Kanto | Koga, Fuchsia City Gym | Soul Badge |
| Johto | Morty, Ecruteak City Gym | Fog Badge |

Your starting-region choice determines where your account begins; it never
grants a badge. The same rules apply to new and existing accounts. Licenses
are checked independently when travelling between Kanto and Johto.

## Getting onto the water

1. Win the region's required Gym battle.
2. Keep a Water-type Pokémon in your active party. Dual types count; Pokémon
   in storage do not. Its moves and HP do not determine field eligibility.
3. Stand on accessible land beside a legal water tile.
4. Click **Surf**. The button explains a missing badge, party member or shoreline.
5. Move with WASD or the arrow keys. Step onto accessible land to dismount.

The server chooses the first eligible Water partner in party order and keeps
that partner while surfing when it remains eligible. It checks the facing
water tile first, then other adjacent legal water. Surf cannot board through
walls, obstacles or invalid shore edges. Your normal party order and land
follower are preserved. The Water partner is displayed beneath the rider;
other players see the same surfing state.

There is no mid-water toggle that leaves the trainer standing on water.
Removing or trading away the final eligible Water partner while still at sea
is rejected. Return to land first. Surf also dismounts the Bicycle.

## Saves and upgrades

Badges remain part of the existing character save. No account reset, HM
recollection, move teaching or SQL schema reset is required. Existing earned
badges are used immediately, regardless of whether an older save already
contained an advisory Surf unlock string. An old unlock string by itself
cannot bypass the actual badge requirement.

Valid saved surfing sessions restore their Water partner. Legacy or malformed
saves that leave a character on water without the required badge or party
partner are moved to a validated safe shore, with the home hub as the final
recovery fallback. This does not award badges or alter party ownership.

The legacy `allow_alpha_surf` setting no longer bypasses normal Surf rules.
Build and deploy a matching 0.6.12 client and server. Older clients use the
previous toggle protocol and must be updated. Preserve your configured
server, database, passwords and certificates when replacing program files.

## Installation and verification

Extract all four `Pokemon_NXT_MMO_v0.6.12-alpha_Source_RegionalSurf_Part*.zip`
archives into the same destination, then run `BUILD_ALL.bat` from the combined
source folder. Native assets are included; no ROM is needed for this build.

`REGIONAL_SURF_TEST_REPORT.md` records the checks run for this release.
The previous Kanto item/Bag features and their documented parity limits remain
included; see `KANTO_ITEMS_RELEASE.md`.
