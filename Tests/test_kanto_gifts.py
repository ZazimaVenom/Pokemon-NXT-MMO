"""Authoritative Kanto gifts: costs, source bindings and durable acquisition."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import types
import unittest
import struct

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Server"))
from nxt import kanto_gifts as gifts
from nxt.security import RequestError
from Tools.extract_adventure_data import Rom
from Tools.extract_kanto_gifts import script_gifts


class KantoGiftsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        world = json.loads((ROOT / "Server/data/world.json").read_text(encoding="utf-8"))
        cls.content = types.SimpleNamespace(data=world, items=world["items"], species=world["species"])
        cls.definitions = gifts.definitions(cls.content)

    def state(self, map_id):
        return {"map": map_id, "items": {}, "adventure": {"badges": [], "caught": [], "trainers": {}}}

    def gift(self, source_id, map_id=None):
        return next(row for row in self.definitions if row["sourceItemId"] == source_id and (map_id is None or row["map"] == map_id))

    def item(self, source_id):
        return gifts._item_key(self.content, source_id)

    def test_native_bindings_and_all_runtime_prerequisites_are_reachable(self):
        self.assertGreaterEqual(len(self.definitions), 48)
        maps = self.content.data["maps"]
        trainers = self.content.data["adventureRom"]["trainers"]
        for gift in self.definitions:
            with self.subTest(gift=gift["id"]):
                self.assertIn(gift["npc"], {obj["id"] for obj in maps[gift["map"]]["objects"]})
                self.assertFalse(339 <= gift["sourceItemId"] <= 346)
                self.assertTrue(all(key in trainers for key in gift.get("trainers", [])))
                state = self.state(gift["map"])
                state["adventure"]["badges"] = [f"kanto_{index}" for index in range(1, 9)]
                state["adventure"]["trainers"] = {key: {"wins": 1} for key in gift.get("trainers", [])}
                state["adventure"]["caught"] = list(self.content.species)
                if gift.get("berryPouchRequired"):
                    state["adventure"]["kantoFlags"] = [2119]
                if gift.get("requiredGiftGroup"):
                    prior = next(row for row in self.definitions if row.get("group") == gift["requiredGiftGroup"])
                    state["adventure"]["kantoGifts"] = [prior["id"]]
                for sid, count in {**gift.get("requiredItems", {}), **gift.get("consumeItems", {})}.items():
                    self.assertIsNotNone(self.item(sid))
                    state["items"][self.item(sid)] = count
                before = copy.deepcopy(state)
                result = gifts.grant(self.content, state, gift["id"])
                self.assertEqual(state, before)
                self.assertEqual(result["items"][gift["item"]], gift["quantity"])
                self.assertIn(gift["id"], result["adventure"]["kantoGifts"])
                for sid in gift.get("consumeItems", {}):
                    self.assertEqual(result["items"].get(self.item(sid), 0), 0)
                with self.assertRaises(RequestError):
                    gifts.grant(self.content, result, gift["id"])

    def test_bicycle_requires_and_consumes_voucher(self):
        gift = self.gift(360)
        state = self.state(gift["map"])
        with self.assertRaisesRegex(RequestError, "Voucher"):
            gifts.grant(self.content, state, gift["id"])
        state["items"][self.item(352)] = 1
        result = gifts.grant(self.content, state, gift["id"])
        self.assertEqual(result["items"][gift["item"]], 1)
        self.assertNotIn(self.item(352), result["items"])

    def test_fossil_choice_is_shared_between_both_objects(self):
        dome, helix = self.gift(358), self.gift(357)
        state = self.state(dome["map"])
        state["adventure"]["badges"] = ["kanto_1"]
        result = gifts.grant(self.content, state, dome["id"])
        with self.assertRaisesRegex(RequestError, "already chose"):
            gifts.grant(self.content, result, helix["id"])

    def test_gyms_cannot_award_tm_before_badge(self):
        gift = self.gift(327)
        state = self.state(gift["map"])
        with self.assertRaisesRegex(RequestError, "Boulder"):
            gifts.grant(self.content, state, gift["id"])
        state["adventure"]["badges"] = ["kanto_1"]
        self.assertEqual(gifts.grant(self.content, state, gift["id"])["items"][gift["item"]], 1)

    def test_itemfinder_counts_unique_species(self):
        gift = self.gift(261)
        state = self.state(gift["map"])
        content = types.SimpleNamespace(data=self.content.data, items=self.content.items,
            species={**{f"test_{n}": {"nationalDex": n} for n in range(1, 31)}, "alternate": {"nationalDex": 1}})
        state["adventure"]["caught"] = [f"test_{n}" for n in range(1, 30)] + ["alternate"]
        with self.assertRaisesRegex(RequestError, "30 caught"):
            gifts.grant(content, state, gift["id"])
        state["adventure"]["caught"].append("test_30")
        self.assertEqual(gifts.grant(content, state, gift["id"])["items"][gift["item"]], 1)

    def test_remote_unknown_and_exchange_service_grants_are_rejected(self):
        gift = self.gift(13)
        state = self.state("kanto_3_0")
        with self.assertRaisesRegex(RequestError, "location"):
            gifts.grant(self.content, state, gift["id"])
        with self.assertRaisesRegex(RequestError, "unavailable"):
            gifts.grant(self.content, state, "kanto_gift:kanto_10_15:4:301")

    def test_celio_supplies_inputs_for_both_delivery_chains(self):
        for sid in (280, 367):
            gift = self.gift(sid, "kanto_32_0")
            state = self.state(gift["map"])
            state["adventure"]["badges"] = ["kanto_7"]
            self.assertEqual(gifts.grant(self.content, state, gift["id"])["items"][gift["item"]], 1)
        self.assertEqual(self.gift(368)["consumeItems"], {373: 1, 367: 1})

    def test_powder_jar_requires_native_berry_pouch_history_without_creating_powder(self):
        gift = self.gift(372, "kanto_7_9")
        empty = self.state(gift["map"])
        with self.assertRaisesRegex(RequestError, "Berry Pouch"):
            gifts.grant(self.content, empty, gift["id"])
        for evidence in ("berry", "pouch", "flag"):
            with self.subTest(evidence=evidence):
                state = self.state(gift["map"])
                state["berryPowder"] = 0
                if evidence == "flag":
                    state["adventure"]["kantoFlags"] = [2119]
                else:
                    state["items"][self.item(133 if evidence == "berry" else 365)] = 1
                before = copy.deepcopy(state)
                result = gifts.grant(self.content, state, gift["id"])
                self.assertEqual(state, before)
                self.assertEqual(result["items"][gift["item"]], 1)
                self.assertEqual(result["items"][self.item(365)], 1)
                self.assertEqual(result["berryPowder"], 0)
                self.assertIn(699, result["adventure"]["kantoFlags"])
                self.assertIn(2119, result["adventure"]["kantoFlags"])
                if evidence == "berry":
                    self.assertEqual(result["items"][self.item(133)], 1)
                with self.assertRaisesRegex(RequestError, "already received"):
                    gifts.grant(self.content, result, gift["id"])

    def test_first_berry_history_survives_consuming_the_last_berry(self):
        gift = self.gift(372, "kanto_7_9")
        acquired = self.state(gift["map"])
        acquired["items"][self.item(133)] = 1
        gifts.refresh_berry_pouch(self.content, acquired)
        self.assertIn(2119, acquired["adventure"]["kantoFlags"])
        del acquired["items"][self.item(133)]
        self.assertEqual(gifts.grant(self.content, acquired, gift["id"])["items"][gift["item"]], 1)
        # The first operation on an old save may itself consume the last Berry.
        previous = self.state(gift["map"])
        previous["items"][self.item(133)] = 1
        consumed = self.state(gift["map"])
        gifts.refresh_berry_pouch(self.content, consumed, previous)
        self.assertIn(2119, consumed["adventure"]["kantoFlags"])
        self.assertEqual(consumed["items"][self.item(365)], 1)

    def test_first_tm_automatically_creates_and_retains_case_without_berry_flag(self):
        acquired = self.state("kanto_6_2")
        acquired["items"][self.item(327)] = 1
        gifts.refresh_berry_pouch(self.content, acquired)
        self.assertEqual(acquired["items"][self.item(364)], 1)
        self.assertNotIn(2119, acquired["adventure"].get("kantoFlags", []))
        del acquired["items"][self.item(327)]
        gifts.refresh_berry_pouch(self.content, acquired)
        self.assertEqual(acquired["items"][self.item(364)], 1)
        self.assertNotIn(self.item(365), acquired["items"])
        previous = self.state("kanto_6_2")
        previous["items"][self.item(327)] = 1
        consumed = self.state("kanto_6_2")
        gifts.refresh_berry_pouch(self.content, consumed, previous)
        self.assertEqual(consumed["items"][self.item(364)], 1)

    def test_all_remaining_source_acquisitions_are_dedicated_exchange_services(self):
        report = gifts.audit(self.content)
        self.assertEqual(report["enabledGifts"], 52)
        remaining = report["excludedAcquisitions"]
        self.assertEqual(len(remaining), 21)
        self.assertEqual(sum("coin-prize service" in row["reason"] for row in remaining), 10)
        self.assertEqual(sum("Powder exchange service" in row["reason"] for row in remaining), 11)


class GiftExtractionTests(unittest.TestCase):
    def rom(self, data):
        rom = Rom.__new__(Rom)
        rom.b = bytes(data)
        return rom

    def test_repeated_helper_calls_do_not_hide_later_item_grants(self):
        data = bytearray(64)
        data[0:5] = b"\x04" + struct.pack("<I", 0x08000030)
        data[5:10] = b"\x04" + struct.pack("<I", 0x08000030)
        data[10:16] = b"\x44\x0d\x00\x01\x00\x02"
        data[48] = 3
        rows, _ = script_gifts(self.rom(data), 0, {13: "Potion"})
        self.assertEqual([row["sourceItemId"] for row in rows], [13])

    def test_flag_gate_and_post_grant_exchange_cost_are_retained(self):
        data = bytearray(64)
        # If flag 42 is already set, finish. Otherwise give Bicycle and then
        # remove its voucher; the exchange cost must survive source ordering.
        data[0:3] = b"\x2b\x2a\x00"
        data[3:9] = b"\x06\x01" + struct.pack("<I", 0x08000020)
        data[9:14] = b"\x44" + struct.pack("<HH", 360, 1)
        data[14:19] = b"\x45" + struct.pack("<HH", 352, 1)
        data[19:23] = b"\x29\x2a\x00\x02"
        data[32] = 2
        rows, _ = script_gifts(self.rom(data), 0, {360: "Bicycle"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["conditions"][0]["operand"], 42)
        self.assertEqual(rows[0]["conditions"][0]["relation"], "ne")
        self.assertEqual(rows[0]["consumedItems"], [{"sourceItemId": 352, "quantity": 1}])
        self.assertEqual(rows[0]["setFlags"], [42])


if __name__ == "__main__":
    unittest.main()
