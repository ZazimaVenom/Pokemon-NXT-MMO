"""Server-owned Kanto NPC item acquisitions and explicit NXT story adapters.

Native coordinates/items/quantities come from the reviewed ROM extraction.
There is no FireRed event-script VM in NXT. Profiles below preserve cartridge
costs, exclusive choices and one-time receipts; ``adaptation`` documents each
substitution for a missing cutscene or scene variable. Unknown source gifts
remain unavailable rather than becoming unconditional rewards.

The caller verifies object proximity and persists the detached state returned
by ``grant``. Inventory, prerequisites and receipt identities are server-owned.
"""
from __future__ import annotations

import copy
from .security import require


# key: (map ID, local NPC ID, source item ID). None is an intentionally
# ordinary first-conversation gift; every entry still has a durable receipt.
PROFILES = {
    ("kanto_3_19", 1, 13): {},
    ("kanto_10_17", 4, 260): {},
    ("kanto_10_7", 4, 369): {},
    ("kanto_14_8", 1, 317): {},
    ("kanto_23_1", 1, 315): {},
    ("kanto_6_0", 3, 354): {},
    ("kanto_9_1", 5, 362): {},
    ("kanto_7_9", 1, 372): {"berryPouchRequired": True,
        "confirmation": "Tell the Berry expert you are interested in Berries.",
        "nativePrerequisite": "FLAG_SYS_GOT_BERRY_POUCH (2119 / 0x847)",
        "provenance": "FireRed AddBagItem: Berry Pouch literal 0x9a1c4, flag literal 0x9a1c8; gift command 0x16af04."},
    ("kanto_11_8", 1, 263): {"confirmation": "Accept the fishing gift."},
    ("kanto_23_2", 1, 264): {"confirmation": "Accept the fishing gift."},
    ("kanto_9_0", 1, 262): {"confirmation": "Accept the fishing gift."},
    ("kanto_9_3", 1, 352): {"confirmation": "Listen to the chairman and accept his voucher."},
    ("kanto_7_6", 1, 360): {"consumeItems": {352: 1}},
    ("kanto_10_5", 2, 304): {"consumeItems": {26: 1}},
    ("kanto_10_5", 2, 308): {"consumeItems": {27: 1}},
    ("kanto_10_5", 2, 321): {"consumeItems": {28: 1}},
    ("kanto_21_0", 5, 195): {"caughtCount": 20},
    ("kanto_22_1", 2, 261): {"caughtCount": 30},
    ("kanto_24_1", 1, 182): {"caughtCount": 50},
    ("kanto_25_2", 3, 189): {"caughtCount": 40},
    ("kanto_6_2", 1, 327): {"badge": "kanto_1"},
    ("kanto_7_5", 3, 291): {"badge": "kanto_2"},
    ("kanto_9_6", 1, 322): {"badge": "kanto_3"},
    ("kanto_10_16", 7, 307): {"badge": "kanto_4"},
    ("kanto_11_3", 7, 294): {"badge": "kanto_5"},
    ("kanto_14_3", 7, 292): {"badge": "kanto_6"},
    ("kanto_12_0", 8, 326): {"badge": "kanto_7"},
    ("kanto_5_1", 8, 314): {"badge": "kanto_8"},
    ("kanto_3_3", 2, 316): {"badge": "kanto_2",
        "adaptation": "The Cascade Badge replaces the native burglar battle, which has no trainer binding in this NXT baseline."},
    ("kanto_1_114", 6, 374): {"trainers": ["kanto_1_114:6"]},
    ("kanto_1_45", 2, 359): {"trainers": ["kanto_1_45:1"],
        "adaptation": "NXT uses the recorded Hideout Giovanni victory to reveal the Silph Scope."},
    ("kanto_1_45", 4, 356): {"trainers": ["kanto_1_45:3"],
        "adaptation": "NXT uses the nearby key-dropping Rocket's recorded victory instead of its dropped-object cutscene."},
    ("kanto_1_3", 1, 358): {"badge": "kanto_1", "group": "mt_moon_fossil",
        "adaptation": "NXT replaces the unbound fossil Super Nerd scene with the Boulder Badge; choose exactly one fossil."},
    ("kanto_1_3", 2, 357): {"badge": "kanto_1", "group": "mt_moon_fossil",
        "adaptation": "NXT replaces the unbound fossil Super Nerd scene with the Boulder Badge; choose exactly one fossil."},
    ("kanto_4_2", 1, 361): {"group": "town_map",
        "adaptation": "NXT characters already begin with a starter and Pokédex; Daisy's opening-story requirement is complete."},
    ("kanto_3_1", 4, 366): {
        "adaptation": "The NXT interaction replaces the old man's catching demonstration with an explicit Teachy TV gift."},
    ("kanto_30_0", 1, 265): {"badge": "kanto_2", "group": "bill_ticket",
        "adaptation": "The Cascade Badge replaces Bill's unavailable transformation cutscene in NXT."},
    ("kanto_30_0", 2, 265): {"badge": "kanto_2", "group": "bill_ticket",
        "adaptation": "Both native Bill objects share one ticket receipt; Cascade Badge replaces his unavailable cutscene."},
    ("kanto_8_2", 1, 350): {"requiredItems": {359: 1}, "badge": "kanto_3",
        "adaptation": "Silph Scope possession and the Thunder Badge replace the unavailable Mr. Fuji rescue cutscene."},
    ("kanto_1_57", 1, 1): {"requiredItems": {355: 1}, "badge": "kanto_6",
        "adaptation": "Card Key possession and the Marsh Badge replace the unbound Silph president rescue scene."},
    ("kanto_3_43", 1, 110): {"trainers": [f"kanto_3_43:{n}" for n in range(2, 7)],
        "adaptation": "NXT awards the Nugget once the five native bridge trainers have recorded victories."},
    ("kanto_1_102", 1, 373): {"badge": "kanto_8",
        "adaptation": "The Earth Badge gates the Ruby while NXT lacks the native postgame Celio scene."},
    ("kanto_2_34", 1, 110): {"badge": "kanto_8",
        "adaptation": "The Earth Badge replaces the native National Pokédex special for this once-only Nugget."},
    ("kanto_1_109", 1, 147): {"badge": "kanto_7", "group": "lostelle_rescue",
        "adaptation": "The Volcano Badge and reaching Lostelle replace the unavailable Berry Forest rescue battle scene."},
    ("kanto_33_0", 1, 94): {"requiredGiftGroup": "lostelle_rescue", "consumeItems": {280: 1},
        "adaptation": "A saved Lostelle gift receipt and Meteorite delivery replace the Two Island rescue scene variables."},
    ("kanto_3_14", 1, 19): {"requiredGiftGroup": "lostelle_rescue",
        "adaptation": "The saved Lostelle rescue receipt replaces the unavailable biker-scene completion variable."},
    ("kanto_3_57", 1, 330): {"consumeItems": {28: 1},
        "adaptation": "Offer Lemonade through this NPC interaction; the native memorial background event is not an NPC script."},
    ("kanto_32_0", 3, 368): {"consumeItems": {373: 1, 367: 1},
        "adaptation": "Celio directly exchanges Ruby and Tri-Pass for Rainbow Pass; native dialogue branches are replaced."},
    ("kanto_32_0", 3, 280): {"badge": "kanto_7",
        "adaptation": "Celio gives the native arrival-scene Meteorite when spoken to after earning the Volcano Badge."},
    ("kanto_32_0", 3, 367): {"badge": "kanto_7",
        "adaptation": "Celio gives the native arrival-scene Tri-Pass when spoken to after earning the Volcano Badge."},
    ("kanto_32_0", 3, 361): {"badge": "kanto_7", "group": "town_map",
        "adaptation": "Celio's native backup Town Map shares Daisy's permanent receipt."},
    ("kanto_5_3", 1, 349): {
        "adaptation": "Speak to the Viridian clerk to receive the Parcel from the native shop-entry scene."},
}


def _source_rows(content):
    data = content.data.get("adventureRom", {}).get("kantoScriptGiftAudit", {})
    if not data:
        data = content.data.get("kantoItems", {}).get("scriptGifts", {})
    return data.get("candidates", []) if isinstance(data, dict) else []


def _item_key(content, source_id):
    for key, item in content.items.items():
        if item.get("source") == "kanto" and item.get("sourceId") == source_id:
            return key
    return None


def definitions(content):
    """Return approved acquisitions whose source commands exist in this pack."""
    grouped = {}
    for row in _source_rows(content):
        identity = (row.get("map"), row.get("npc"), row.get("sourceItemId"))
        if identity not in PROFILES or not row.get("acquisition", {}).get("completePath"):
            continue
        grouped.setdefault(identity, []).append(row)
    out = []
    for identity, paths in sorted(grouped.items()):
        map_id, npc, source_id = identity
        item = _item_key(content, source_id)
        if item is None:
            continue
        profile = copy.deepcopy(PROFILES[identity])
        source = min(paths, key=lambda row: (len(row.get("conditions", [])), row["sourceGiveCommand"]))
        flags = set()
        for path in paths:
            flags.update(path.get("setFlags", []))
        out.append({"id": f"kanto_gift:{map_id}:{npc}:{source_id}", "map": map_id,
                    "npc": npc, "sourceItemId": source_id, "item": item,
                    "quantity": source["quantity"], "sourceCommand": source["sourceGiveCommand"],
                    "name": content.items[item].get("name", source.get("name", item)),
                    "sourceFlags": sorted(flags), **profile})
    return out


def lookup(content, gift_id):
    return next((gift for gift in definitions(content) if gift["id"] == gift_id), None)


def _receipts(state):
    return set(state.get("adventure", {}).get("kantoGifts", []))


def _group_received(content, state, group):
    receipts = _receipts(state)
    return any(gift.get("group") == group and gift["id"] in receipts for gift in definitions(content))


def _count(content, state, source_id):
    key = _item_key(content, source_id)
    return state.get("items", {}).get(key, 0) if key is not None else 0


def _caught_count(content, state):
    # Form/region aliases of the same National Dex species count once.
    species = getattr(content, "species", content.data.get("species", {}))
    identities = set()
    for key in state.get("adventure", {}).get("caught", []):
        row = species.get(key, {})
        dex = row.get("nationalDex", row.get("dexNumber"))
        identities.add(("dex", dex) if dex is not None else ("name", row.get("name", key)))
    return len(identities)


def _berry_pouch_obtained(content, state):
    """Match FireRed's persistent obtained-pouch flag, including old NXT saves.

    AddBagItem in FireRed creates the pouch and sets flag 0x847 when the first
    Berry is received. A saved Berry or pouch therefore proves this prerequisite
    even when an older NXT save predates the native flag. It is not consumed.
    Primary reference: https://github.com/pret/pokefirered/blob/master/src/item.c
    """
    if 2119 in state.get("adventure", {}).get("kantoFlags", []) or _count(content, state, 365) > 0:
        return True
    return any(count > 0 and content.items.get(key, {}).get("source") == "kanto"
               and content.items[key].get("pocket") == 5
               for key, count in state.get("items", {}).items())


def refresh_berry_pouch(content, state, previous=None):
    """Restore native TM Case/Berry Pouch containers before a detached commit.

    ``previous`` preserves evidence when the current action consumed/traded the
    final TM or Berry from an older save. FireRed AddBagItem automatically gives
    TM Case for pocket 4 with no flag, and Berry Pouch for pocket 5 with flag
    2119. Keep this public helper name for the existing World commit hooks.
    """
    tm_case = _item_key(content, 364)
    if tm_case is not None:
        for snapshot in (state, previous):
            if snapshot and (_count(content, snapshot, 364) > 0 or any(
                    count > 0 and content.items.get(key, {}).get("source") == "kanto"
                    and content.items[key].get("pocket") == 4
                    for key, count in snapshot.get("items", {}).items())):
                state.setdefault("items", {})[tm_case] = 1
                break
    if not _berry_pouch_obtained(content, state) and not (previous and _berry_pouch_obtained(content, previous)):
        return state
    flags = set(state.setdefault("adventure", {}).get("kantoFlags", []))
    flags.add(2119)
    state["adventure"]["kantoFlags"] = sorted(flags)
    pouch = _item_key(content, 365)
    if pouch is not None:
        state.setdefault("items", {})[pouch] = 1
    return state


def _reason(content, state, gift):
    adventure = state.get("adventure", {})
    if gift["id"] in _receipts(state):
        return "You already received this gift."
    if gift.get("group") and _group_received(content, state, gift["group"]):
        return "You already chose a reward from this event."
    if gift.get("requiredGiftGroup") and not _group_received(content, state, gift["requiredGiftGroup"]):
        return "Help Lostelle in Berry Forest first."
    if gift.get("badge") and gift["badge"] not in adventure.get("badges", []):
        badges = {1: "Boulder", 2: "Cascade", 3: "Thunder", 4: "Rainbow", 5: "Soul", 6: "Marsh", 7: "Volcano", 8: "Earth"}
        return f"Earn the {badges[int(gift['badge'].split('_')[1])]} Badge first."
    wins = adventure.get("trainers", {})
    if any(not wins.get(key) for key in gift.get("trainers", [])):
        return "Defeat the required trainer first." if len(gift["trainers"]) == 1 else "Defeat all five Nugget Bridge trainers first."
    if _caught_count(content, state) < gift.get("caughtCount", 0):
        return f"Register {gift['caughtCount']} caught species in your Pokédex first."
    if gift.get("berryPouchRequired") and not _berry_pouch_obtained(content, state):
        return "Obtain a Berry and its Berry Pouch first."
    for source_id, count in {**gift.get("requiredItems", {}), **gift.get("consumeItems", {})}.items():
        if _count(content, state, source_id) < count:
            key = _item_key(content, source_id)
            name = content.items.get(key, {}).get("name", f"item {source_id}")
            return f"Bring {name}" + (f" ×{count}." if count > 1 else ".")
    definition = content.items[gift["item"]]
    maximum = 1 if definition.get("pocket") in ("key", "keyitems", "keyItems") or definition.get("keyItem") else 999
    if state.get("items", {}).get(gift["item"], 0) + gift["quantity"] > maximum:
        return "Make room in your Bag before receiving this gift."
    return ""


def options(content, state, map_id, npc):
    """Expose only authoritative gifts at the selected native object."""
    out = []
    for gift in definitions(content):
        if gift["map"] != map_id or gift["npc"] != npc:
            continue
        reason = _reason(content, state, gift)
        label = f"Receive {gift['name']}"
        if gift.get("consumeItems"):
            costs = [content.items.get(_item_key(content, sid), {}).get("name", str(sid)) for sid in gift["consumeItems"]]
            label = f"Exchange {' + '.join(costs)} for {gift['name']}"
        out.append({"id": gift["id"], "item": gift["item"], "label": label,
                    "ready": not reason, "reason": reason, "quantity": gift["quantity"],
                    "claimed": gift["id"] in _receipts(state),
                    "adaptation": gift.get("adaptation", "")})
    return out


def grant(content, state, gift_id):
    """Recheck, consume costs, and return a detached save; never mutate input."""
    gift = lookup(content, gift_id)
    require(gift is not None, "That Kanto gift is unavailable.")
    require(state.get("map") == gift["map"], "Visit this gift's location first.")
    reason = _reason(content, state, gift)
    require(not reason, reason)
    result = copy.deepcopy(state)
    items = result.setdefault("items", {})
    for source_id, count in gift.get("consumeItems", {}).items():
        key = _item_key(content, source_id)
        items[key] -= count
        if items[key] == 0:
            del items[key]
    items[gift["item"]] = items.get(gift["item"], 0) + gift["quantity"]
    adventure = result.setdefault("adventure", {})
    receipts = adventure.setdefault("kantoGifts", [])
    receipts.append(gift["id"])
    flags = set(adventure.get("kantoFlags", []))
    flags.update(gift.get("sourceFlags", []))
    if gift.get("berryPouchRequired"):
        flags.add(2119)
        pouch = _item_key(content, 365)
        if pouch is not None:
            items[pouch] = 1
    adventure["kantoFlags"] = sorted(flags)
    return result


def audit(content):
    enabled = {(g["map"], g["npc"], g["sourceItemId"]) for g in definitions(content)}
    excluded = sorted({(r["map"], r["npc"], r["sourceItemId"]) for r in _source_rows(content)} - enabled)
    def service_reason(map_id, npc):
        if map_id == "kanto_10_15" and npc in (4, 5):
            return "Dedicated native Game Corner coin-prize service; spends the extracted coin price."
        if map_id == "kanto_7_9" and npc == 1:
            return "Dedicated native Berry Powder exchange service; spends the extracted powder price."
        return "Unimplemented native acquisition; no free grant."
    return {"enabledGifts": len(enabled), "storyAdapters": [g for g in definitions(content) if g.get("adaptation")],
            "excludedAcquisitions": [{"map": m, "npc": n, "sourceItemId": i,
                "reason": service_reason(m, n)} for m, n, i in excluded]}
