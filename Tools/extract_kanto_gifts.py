#!/usr/bin/env python3
"""Bounded, conservative extraction of FireRed object-script item grants.

This module reports acquisition paths, not executable free-gift definitions.
Native special functions, story variables, choices and trainer requirements are
retained as prerequisites. A candidate may only be granted after its conditions
have been implemented by the server. No ROM code is executed.
"""
from __future__ import annotations

import collections
import json
import struct
from dataclasses import dataclass, replace

try:
    from .extract_adventure_data import normalize_objects
    from .extract_sigma_dialogue import LENGTHS, read_item_names
except ImportError:
    from extract_adventure_data import normalize_objects
    from extract_sigma_dialogue import LENGTHS, read_item_names

RESULT = 0x800D
HMS = set(range(339, 347))
RELATIONS = ("lt", "eq", "gt", "le", "ge", "ne")
INVERSE = {"lt": "ge", "eq": "ne", "gt": "le", "le": "gt", "ge": "lt", "ne": "eq"}
MAX_STATES = 4096


@dataclass(frozen=True)
class State:
    pc: int
    stack: tuple = ()
    variables: tuple = ()
    compare: tuple = ("unknown",)
    conditions: tuple = ()
    set_flags: tuple = ()
    clear_flags: tuple = ()
    consumed: tuple = ()
    pending: tuple = ()
    specials: tuple = ()
    seen_pc: tuple = ()


def _resolve(state, value):
    return dict(state.variables).get(value, ("variable", value)) if value >= 0x4000 else value


def _condition(expr, relation, value, offset):
    return (expr, relation, value, offset)


def _json_condition(condition):
    expr, relation, value, offset = condition
    if isinstance(expr, int):
        kind, operand = "literal", expr
    else:
        kind, *operand = expr
        operand = operand[0] if len(operand) == 1 else operand
    return {"kind": kind, "operand": operand, "relation": relation,
            "value": value, "sourceCommand": hex(offset)}


def _compare(left, relation, right):
    if not isinstance(left, int) or not isinstance(right, int):
        return None
    return {"lt": left < right, "eq": left == right, "gt": left > right,
            "le": left <= right, "ge": left >= right, "ne": left != right}[relation]


def _implied_result(conditions, left, relation, right):
    result = _compare(left, relation, right)
    if result is not None:
        return result
    for expr, previous_relation, value, _ in reversed(conditions):
        if expr != left:
            continue
        if previous_relation == "eq":
            result = _compare(value, relation, right)
            if result is not None:
                return result
        if value == right:
            if previous_relation == relation:
                return True
            if INVERSE[previous_relation] == relation:
                return False
    return None


def script_gifts(rom, start, item_names, marts=None):
    """Return successful grant paths and decoding stop reasons for one script."""
    todo = [State(start)]
    seen = set()
    finished = []
    stops = collections.Counter()

    def finish(state, reason):
        stops[reason] += 1
        for gift in state.pending:
            item_id, quantity, pc, method, conditions, consumed, specials = gift
            finished.append({"sourceItemId": item_id, "name": item_names[item_id],
                "quantity": quantity, "sourceGiveCommand": hex(pc), "method": method,
                "conditions": [_json_condition(c) for c in conditions],
                "consumedItems": [{"sourceItemId": i, "quantity": n} for i, n in state.consumed],
                "setFlags": list(state.set_flags), "clearFlags": list(state.clear_flags),
                "nativeSpecials": [hex(v) for v in state.specials], "pathEnd": reason})

    while todo and len(seen) < MAX_STATES:
        state = todo.pop()
        # No path is allowed to acquire a gift by circling a script loop.
        execution_key = (state.pc, state.stack, state.variables, state.set_flags, state.clear_flags)
        if execution_key in state.seen_pc or len(state.seen_pc) >= 512:
            finish(state, "loop-or-path-limit")
            continue
        key = replace(state, seen_pc=())
        if key in seen:
            continue
        seen.add(key)
        pc = state.pc
        if not 0 <= pc < len(rom.b):
            finish(state, "range")
            continue
        state = replace(state, seen_pc=state.seen_pc + (execution_key,))
        op = rom.b[pc]

        def push(next_pc, **changes):
            todo.append(replace(state, pc=next_pc, **changes))

        def setvar(next_pc, var, value, **changes):
            values = dict(state.variables)
            values[var] = value
            push(next_pc, variables=tuple(sorted(values.items())), **changes)

        def grant(next_pc, item_id, quantity, method, terminal=False):
            if not isinstance(item_id, int) or not isinstance(quantity, int):
                finish(state, "dynamic-item-or-quantity")
                return
            if item_id in HMS:
                stops["excluded-hm"] += 1
                return
            if item_id not in item_names or not 1 <= item_id <= 374 or not 1 <= quantity <= 999:
                finish(state, "invalid-item-or-quantity")
                return
            gift = (item_id, quantity, pc, method, state.conditions, state.consumed, state.specials)
            values = dict(state.variables)
            values[RESULT] = 1  # Continue only the successful inventory-add path.
            new = replace(state, pc=next_pc, pending=state.pending + (gift,),
                          variables=tuple(sorted(values.items())))
            if terminal:
                finish(new, "standard-goto")
            else:
                todo.append(new)

        try:
            if op in (0x02, 0x0D):
                finish(state, "end")
            elif op in (0x03, 0x0C):
                if state.stack:
                    push(state.stack[-1], stack=state.stack[:-1])
                else:
                    finish(state, "return")
            elif op in (0x04, 0x05):
                target = rom.ptr(pc + 1)
                if op == 0x04 and len(state.stack) >= 12:
                    finish(state, "call-depth")
                else:
                    push(target, stack=state.stack + (pc + 5,) if op == 0x04 else state.stack)
            elif op in (0x06, 0x07):
                rel = RELATIONS[rom.b[pc + 1]]
                target = rom.ptr(pc + 2)
                left, right = state.compare if len(state.compare) == 2 else (("unknown", pc), 1)
                result = _implied_result(state.conditions, left, rel, right)
                for take in (False, True):
                    if result is not None and result != take:
                        continue
                    conditions = state.conditions
                    if result is None:
                        conditions += (_condition(left, rel if take else INVERSE[rel], right, pc),)
                    if len(conditions) > 32:
                        finish(state, "condition-limit")
                    elif take and op == 0x07:
                        if len(state.stack) < 12:
                            push(target, stack=state.stack + (pc + 6,), conditions=conditions)
                    else:
                        push(target if take else pc + 6, conditions=conditions)
            elif op in (0x08, 0x09):
                std = rom.b[pc + 1]
                if std in (0, 1):
                    grant(pc + 2, _resolve(state, 0x8000), _resolve(state, 0x8001),
                          f"standard-{std}", terminal=op == 0x08)
                elif op == 0x08:
                    finish(state, "standard-goto")
                elif std == 5:  # yes/no message box writes VAR_RESULT.
                    setvar(pc + 2, RESULT, ("choice", pc))
                elif 2 <= std <= 9:
                    push(pc + 2)
                else:
                    finish(state, "unknown-standard")
            elif op in (0x16, 0x19, 0x1A):
                var, value = rom.u16(pc + 1), rom.u16(pc + 3)
                setvar(pc + 5, var, _resolve(state, value) if op != 0x16 else value)
            elif op in (0x17, 0x18):
                var, increment = rom.u16(pc + 1), rom.u16(pc + 3)
                value = _resolve(state, var)
                if isinstance(value, int):
                    value = (value + increment * (1 if op == 0x17 else -1)) & 0xFFFF
                setvar(pc + 5, var, value)
            elif op in (0x21, 0x22):
                left, right = _resolve(state, rom.u16(pc + 1)), rom.u16(pc + 3)
                push(pc + 5, compare=(left, _resolve(state, right) if op == 0x22 else right))
            elif op in (0x29, 0x2A):
                flag = rom.u16(pc + 1)
                flags = set(state.set_flags)
                clear = set(state.clear_flags)
                (flags if op == 0x29 else clear).add(flag)
                (clear if op == 0x29 else flags).discard(flag)
                push(pc + 3, set_flags=tuple(sorted(flags)), clear_flags=tuple(sorted(clear)))
            elif op == 0x2B:
                flag = rom.u16(pc + 1)
                value = 1 if flag in state.set_flags else 0 if flag in state.clear_flags else ("flag", flag)
                push(pc + 3, compare=(value, 1))
            elif op in (0x25, 0x26):
                special = rom.u16(pc + (1 if op == 0x25 else 3))
                specials = tuple(sorted(set(state.specials + (special,))))
                # Even no-output specials can write VAR_RESULT in the native code.
                setvar(pc + (3 if op == 0x25 else 5),
                       RESULT if op == 0x25 else rom.u16(pc + 1),
                       ("special", special), specials=specials)
            elif op == 0x44:
                grant(pc + 5, _resolve(state, rom.u16(pc + 1)), _resolve(state, rom.u16(pc + 3)), "additem")
            elif op == 0x45:
                item_id, quantity = _resolve(state, rom.u16(pc + 1)), _resolve(state, rom.u16(pc + 3))
                push(pc + 5, consumed=state.consumed + ((item_id, quantity),))
            elif op in (0x46, 0x47):
                item_id, quantity = _resolve(state, rom.u16(pc + 1)), _resolve(state, rom.u16(pc + 3))
                setvar(pc + 5, RESULT, ("bagSpace" if op == 0x46 else "hasItem", item_id, quantity))
            elif op in (0x6E, 0x6F, 0x70, 0x71):
                setvar(pc + LENGTHS[op], RESULT, ("choice", pc))
            elif op == 0x5C:
                # Mode 1/2/6/8 includes a post-battle script; mode 3 has no intro.
                mode, trainer = rom.b[pc + 1], rom.u16(pc + 2)
                if mode not in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9):
                    finish(state, "unknown-trainer-mode")
                    continue
                size = 10 if mode == 3 else 18 if mode in (1, 2, 4, 6, 7) else 22 if mode == 8 else 14
                rom.raw(pc, size)
                cond = state.conditions + (_condition(("trainerDefeated", trainer), "eq", 1, pc),)
                push(pc + size, conditions=cond)
                if mode in (1, 2):
                    push(rom.ptr(pc + 14), conditions=cond)
            elif op == 0x60:
                push(pc + 3, compare=(("trainerDefeated", rom.u16(pc + 1)), 1))
            elif op == 0x92:
                setvar(pc + 6, RESULT, ("moneyAtLeast", rom.u32(pc + 1)))
            elif op == 0x91:
                push(pc + 6, consumed=state.consumed + (("money", rom.u32(pc + 1)),))
            elif op == 0xB3:
                setvar(pc + 3, rom.u16(pc + 1), ("coins",))
            elif op == 0xB5:
                push(pc + 3, consumed=state.consumed + (("coins", _resolve(state, rom.u16(pc + 1))),))
            elif op == 0x86:
                stock = rom.ptr(pc + 1)
                ids = []
                for index in range(128):
                    item_id = rom.u16(stock + index * 2)
                    if item_id == 0:
                        break
                    if item_id not in item_names or not 1 <= item_id <= 374:
                        raise ValueError("Invalid mart stock")
                    ids.append(item_id)
                else:
                    raise ValueError("Unterminated mart stock")
                if marts is not None:
                    entry = {"sourceIds": ids, "sourceCommand": hex(pc), "stockOffset": hex(stock),
                             "conditions": [_json_condition(c) for c in state.conditions]}
                    if entry not in marts:
                        marts.append(entry)
                push(pc + 5)
            elif op in LENGTHS:
                rom.raw(pc, LENGTHS[op])
                push(pc + LENGTHS[op])
            else:
                finish(state, f"unsupported-opcode-{op:02x}")
        except (IndexError, KeyError, ValueError, struct.error):
            finish(state, "invalid-instruction")
    if todo:
        stops["state-limit"] += 1
    unique = {json.dumps(row, sort_keys=True): row for row in finished}
    return list(unique.values()), dict(stops)


def extract_gifts(rom, world, item_by_id=None):
    """Extract object-bound grants, preserving story gates and exchange costs.

    ``rom`` is the project's ``Rom`` adapter. ``item_by_id`` may map numeric
    source IDs to item records with ``id``/``key``; it is optional metadata only.
    Ordinary standard-1 item balls are omitted (the field-pickup extractor owns
    them). Other ball scripts, including story key items, remain in this audit.
    """
    names = read_item_names(rom)
    candidates = []
    marts = {}
    audit = collections.Counter()
    stops = collections.Counter()
    for map_id, map_data in sorted(world["maps"].items()):
        if not map_id.startswith("kanto_"):
            continue
        audit["maps"] += 1
        try:
            events = rom.ptr(int(map_data["sourceHeader"], 16) + 4)
            count = rom.b[events]
            table = rom.ptr(events + 4) if count else 0
        except (KeyError, ValueError, IndexError, struct.error):
            audit["invalidMapEvents"] += 1
            continue
        for obj in normalize_objects(rom, map_data):
            index = obj.get("sourceObjectIndex")
            if index is None or not 0 <= index < count:
                continue
            audit["objectsScanned"] += 1
            offset = table + index * 24
            try:
                script = rom.ptr(offset + 16)
                object_marts = []
                rows, reasons = script_gifts(rom, script, names, object_marts)
            except (ValueError, IndexError, struct.error):
                audit["objectsWithoutScript"] += 1
                continue
            stops.update(reasons)
            for mart in object_marts:
                mart.update({"map": map_id, "npc": obj["id"], "sourceScript": hex(script)})
                mart["items"] = []
                for item_id in mart["sourceIds"]:
                    metadata = (item_by_id or {}).get(item_id, (item_by_id or {}).get(str(item_id)))
                    item = metadata.get("id", metadata.get("key")) if isinstance(metadata, dict) else metadata
                    mart["items"].append(item or f"fr_{item_id}")
                key = f"{map_id}:{obj['id']}"
                if key not in marts:
                    marts[key] = mart
                elif mart["sourceIds"] != marts[key]["sourceIds"]:
                    marts[key].setdefault("conditionalStock", []).append(mart)
            for row in rows:
                if obj.get("graphics") == 92 and row["method"] == "standard-1":
                    audit["ordinaryItemBallsOwnedByPickupExtractor"] += 1
                    continue
                row.update({"map": map_id, "mapName": map_data.get("name", map_id),
                    "npc": obj["id"], "x": obj["x"], "y": obj["y"],
                    "graphics": obj.get("graphics"), "sourceScript": hex(script),
                    "sourceObjectOffset": hex(offset), "sourceObjectIndex": index,
                    "sourceLocalId": obj.get("sourceLocalId", obj["id"]),
                    "objectFlag": rom.u16(offset + 20)})
                if row["objectFlag"]:
                    row["objectVisibility"] = {"kind": "flag", "operand": row["objectFlag"],
                                               "relation": "eq", "value": 0,
                                               "meaning": "Object is hidden while its event flag is set."}
                metadata = (item_by_id or {}).get(row["sourceItemId"], (item_by_id or {}).get(str(row["sourceItemId"])))
                if isinstance(metadata, dict):
                    row["item"] = metadata.get("id", metadata.get("key"))
                elif isinstance(metadata, str):
                    row["item"] = metadata
                kinds = {c["kind"] for c in row["conditions"]}
                if row["consumedItems"]:
                    kind = "exchange"
                elif "choice" in kinds:
                    kind = "choice-gift"
                elif kinds - {"flag", "bagSpace"} or row["nativeSpecials"]:
                    kind = "story-gift"
                elif row["conditions"]:
                    kind = "flag-gated-gift"
                else:
                    kind = "gift"
                row["acquisition"] = {"kind": kind,
                    "repeatability": "flag-gated" if row["setFlags"] else "script-controlled",
                    "runtimePolicy": "evaluate-all-prerequisites-before-grant",
                    "requiresNativeScriptSupport": bool(kinds - {"flag", "bagSpace", "hasItem", "choice"} or row["nativeSpecials"]),
                    "completePath": row["pathEnd"] in ("end", "return", "standard-goto")}
                candidates.append(row)
    # Two native arrival scenes hand items to the player on behalf of an NPC.
    # NXT exposes these as interactions with that same map's authoritative NPC;
    # retain the scene gate and source command instead of inventing item grants.
    for map_id, npc in (("kanto_32_0", 3), ("kanto_5_3", 1)):
        data = world["maps"].get(map_id)
        if not data:
            continue
        obj = next((o for o in data.get("objects", []) if o["id"] == npc), None)
        if not obj:
            continue
        try:
            table = rom.ptr(int(data["sourceHeader"], 16) + 8)
            for table_index in range(32):
                entry = table + table_index * 5
                kind = rom.b[entry]
                if kind == 0:
                    break
                if kind not in (2, 4):
                    continue
                conditions = rom.ptr(entry + 1)
                for condition_index in range(32):
                    condition_offset = conditions + condition_index * 8
                    variable = rom.u16(condition_offset)
                    if variable == 0:
                        break
                    value = rom.u16(condition_offset + 2)
                    script = rom.ptr(condition_offset + 4)
                    rows, reasons = script_gifts(rom, script, names)
                    stops.update(reasons)
                    for row in rows:
                        if row["sourceItemId"] not in ({280, 367, 361} if map_id == "kanto_32_0" else {349}):
                            continue
                        row["conditions"].insert(0, {"kind": "variable", "operand": variable,
                            "relation": "eq", "value": value, "sourceCommand": hex(condition_offset)})
                        row.update({"map": map_id, "mapName": data.get("name", map_id), "npc": npc,
                            "x": obj["x"], "y": obj["y"], "graphics": obj.get("graphics"),
                            "sourceScript": hex(script), "sourceScene": {"kind": kind, "offset": hex(entry)},
                            "acquisition": {"kind": "scene-gift", "repeatability": "scene-gated",
                            "runtimePolicy": "evaluate-all-prerequisites-before-grant",
                            "requiresNativeScriptSupport": True,
                            "completePath": row["pathEnd"] in ("end", "return", "standard-goto")}})
                        metadata = (item_by_id or {}).get(row["sourceItemId"], (item_by_id or {}).get(str(row["sourceItemId"])))
                        row["item"] = metadata.get("id", metadata.get("key")) if isinstance(metadata, dict) else metadata
                        candidates.append(row)
        except (ValueError, IndexError, struct.error):
            audit["invalidSceneEvents"] += 1
    candidates.sort(key=lambda row: (row["map"], row["npc"], int(row["sourceGiveCommand"], 16), row["sourceItemId"], json.dumps(row["conditions"], sort_keys=True)))
    audit["candidatePaths"] = len(candidates)
    audit["objectsWithCandidateGrants"] = len({(r["map"], r["npc"]) for r in candidates})
    audit["uniqueSourceItems"] = len({r["sourceItemId"] for r in candidates})
    audit["marts"] = len(marts)
    return {"format": 1, "policy": "Acquisition audit; never flatten conditional paths into free pickups.",
            "candidates": candidates, "marts": marts, "audit": dict(audit), "scriptStops": dict(sorted(stops.items()))}
