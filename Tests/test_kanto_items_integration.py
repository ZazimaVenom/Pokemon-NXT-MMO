"""Kanto field-item acceptance through the production world and SQLite store.

Coordinates and item identities come from the shipped ROM-derived sidecar. These
checks exercise real server commands and account isolation, not a script mock.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import sys
import tempfile
import unittest
from collections import defaultdict, deque
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
from nxt.config import Settings
from nxt.content import Content
from nxt.security import RequestError
from nxt.store import Store
from nxt.world import World
from nxt import safari, kanto_obstacles, kanto_gifts

# Legal native puzzle solutions found by searching player-connected space and
# boulder positions. Every action is replayed through production validation.
OBSTACLE_ROUTES = {
    'kanto_1_39': {'npc': 4, 'stand': (16, 3), 'actions': [('push', 7, 17, 3)]},
    'kanto_1_97': {'npc': 19, 'stand': (37, 12), 'actions': [
        ('smash', 12, 33, 14), ('push', 15, 34, 17), ('push', 15, 35, 17),
        ('push', 15, 36, 17), ('smash', 13, 37, 15), ('push', 11, 36, 15),
        ('push', 14, 34, 14)]},
    'kanto_3_15': {'npc': 8, 'stand': (5, 8), 'actions': [('smash', 7, 5, 12)]},
    'kanto_3_61': {'npc': 17, 'stand': (41, 32), 'actions': [('push', 12, 40, 32)]},
}


class KantoItemIntegrationTests(unittest.IsolatedAsyncioTestCase):
    maxDiff = None
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')
        cls.sidecar = json.loads((ROOT / 'Server/data/kanto_items.json').read_text())
        cls.visible = cls.sidecar['itemPickups']
        cls.hidden = cls.sidecar['hiddenItemPickups']

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        config = Path(self.temp.name) / 'config.ini'
        config.write_bytes((ROOT / 'Build/config_templates/Server/config.ini').read_bytes())
        settings = Settings.load(config)
        settings.config.set('database', 'backend', 'sqlite')
        self.settings = dataclasses.replace(settings, encounter_chance=0)
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.world = World(self.content, self.db, self.settings)
        self.owner = await self.add('KantoItemsOwner')
        self.peer = await self.add('KantoItemsPeer')

    async def asyncTearDown(self):
        self.world.players.clear()
        self.db.close()
        self.temp.cleanup()

    async def add(self, username):
        state = self.world.initial(username, 'Kanto', 'fr_4', 0)
        uid = self.db.create(username, 'isolated-fixture', state)
        return await self.world.join(uid, username, state, asyncio.Queue(maxsize=4096))

    def walkable_positions(self, pickup, *, adjacent=False):
        m = self.content.maps[pickup['map']]
        offsets = [(0, 0, 'down'), (0, 1, 'up'), (0, -1, 'down'), (1, 0, 'left'), (-1, 0, 'right')]
        if adjacent:
            offsets = offsets[1:]
        for dx, dy, direction in offsets:
            x, y = pickup['x'] + dx, pickup['y'] + dy
            if self.world.walkable(m, x, y, surf=True, state=self.owner.state):
                yield x, y, direction

    async def place(self, pickup, *, adjacent=False):
        x, y, direction = next(self.walkable_positions(pickup, adjacent=adjacent))
        state = copy.deepcopy(self.owner.state)
        state.update(map=pickup['map'], x=x, y=y, direction=direction, surf=True)
        await self.world.commit(self.owner, state)

    def normal_hidden(self):
        return next(row for row in self.hidden.values()
                    if row.get('item') and not row.get('requiresItemfinder')
                    and list(self.walkable_positions(row, adjacent=True)))

    async def interact(self, **extra):
        await self.world.dispatch(self.owner, {'op': 'interact', 'map': self.owner.state['map'], **extra})

    def oran_pickup(self):
        return next(row for row in self.hidden.values()
                    if row.get('item') == 'fr_oranberry'
                    and list(self.walkable_positions(row, adjacent=True)))

    def powder_jar_option(self, player):
        return next(option for option in kanto_gifts.options(self.content, player.state, 'kanto_7_9', 1)
                    if option['item'] == 'fr_powderjar')

    async def relogin(self, player):
        self.world.players.pop(player.id)
        return await self.world.join(player.id, player.username, None, asyncio.Queue(maxsize=4096))

    async def trade_last_berry(self):
        state = copy.deepcopy(self.peer.state)
        state.update({key: self.owner.state[key] for key in ('map', 'x', 'y')})
        await self.world.commit(self.peer, state)
        await self.world.dispatch(self.owner, {'op': 'invite', 'kind': 'trade', 'target': self.peer.id})
        await self.world.dispatch(self.peer, {'op': 'invite.answer', 'id': next(iter(self.world.invites)), 'accept': True})
        trade = self.world.trades[self.owner.trade]
        await self.world.dispatch(self.owner, {'op': 'trade', 'id': trade['id'], 'action': 'offer',
            'revision': trade['revision'], 'offer': {'pokemon': [], 'items': {'fr_oranberry': 1}, 'money': 0}})
        for player in (self.owner, self.peer):
            await self.world.dispatch(player, {'op': 'trade', 'id': trade['id'], 'action': 'lock', 'revision': trade['revision']})
        for player in (self.owner, self.peer):
            await self.world.dispatch(player, {'op': 'trade', 'id': trade['id'], 'action': 'confirm',
                'revision': trade['revision'], 'digest': self.world.trade_digest(trade)})

    async def test_first_berry_consumed_and_relogin_preserve_powder_jar_eligibility(self):
        self.assertFalse(self.powder_jar_option(self.owner)['ready'])
        await self.place(self.oran_pickup(), adjacent=True)
        await self.interact()
        acquired = self.db.load(self.owner.id)
        self.assertEqual(acquired['items']['fr_berrypouch'], 1)
        self.assertIn(2119, acquired['adventure']['kantoFlags'])
        state = copy.deepcopy(self.owner.state)
        state['creatures'][0]['hp'] = 1
        await self.world.commit(self.owner, state)
        await self.world.dispatch(self.owner, {'op': 'use', 'item': 'fr_oranberry',
            'uid': state['party'][0], 'requestId': 'first-berry-consumed'})
        self.assertEqual(self.owner.state['items'].get('fr_oranberry', 0), 0)
        self.owner = await self.relogin(self.owner)
        option = self.powder_jar_option(self.owner)
        self.assertTrue(option['ready'], option['reason'])
        await self.place({'map': 'kanto_7_9', 'x': 7, 'y': 4}, adjacent=True)
        await self.world.dispatch(self.owner, {'op': 'npc', 'map': 'kanto_7_9', 'npc': 1,
            'action': 'gift:' + option['id']})
        saved = self.db.load(self.owner.id)
        self.assertEqual(saved['items']['fr_powderjar'], 1)
        self.assertEqual(saved.get('berryPowder', 0), 0)
        self.assertEqual(saved['items']['fr_berrypouch'], 1)
        self.assertIn(2119, saved['adventure']['kantoFlags'])

    async def test_failed_first_berry_pickup_does_not_grant_pouch_or_eligibility(self):
        await self.place(self.oran_pickup(), adjacent=True)
        before = copy.deepcopy(self.owner.state)
        with patch.object(self.db, 'save_many', side_effect=OSError('first Berry storage failure')):
            with self.assertLogs('nxt.world', level='ERROR'):
                with self.assertRaisesRegex(RequestError, 'database'):
                    await self.interact()
        self.assertEqual(self.owner.state, before)
        self.assertEqual(self.db.load(self.owner.id), before)
        self.assertNotIn('fr_berrypouch', self.owner.state['items'])
        self.assertNotIn(2119, self.owner.state['adventure'].get('kantoFlags', []))
        self.assertFalse(self.powder_jar_option(self.owner)['ready'])

    async def test_first_berry_trade_preserves_sender_and_recipient_pouch_history(self):
        await self.place(self.oran_pickup(), adjacent=True)
        await self.interact()
        self.assertFalse(self.powder_jar_option(self.peer)['ready'])
        await self.trade_last_berry()
        self.assertEqual(self.db.load(self.owner.id)['items'].get('fr_oranberry', 0), 0)
        self.assertEqual(self.db.load(self.peer.id)['items']['fr_oranberry'], 1)
        for player in (self.owner, self.peer):
            saved = self.db.load(player.id)
            self.assertEqual(saved['items']['fr_berrypouch'], 1)
            self.assertIn(2119, saved['adventure']['kantoFlags'])
        self.owner = await self.relogin(self.owner)
        self.peer = await self.relogin(self.peer)
        self.assertTrue(self.powder_jar_option(self.owner)['ready'])
        self.assertTrue(self.powder_jar_option(self.peer)['ready'])

    async def test_failed_first_berry_trade_never_grants_recipient_pouch_history(self):
        await self.place(self.oran_pickup(), adjacent=True)
        await self.interact()
        owner_before = copy.deepcopy(self.owner.state)
        peer_items = copy.deepcopy(self.peer.state['items'])
        with patch.object(self.db, 'trade', side_effect=OSError('first Berry exchange failure')):
            with self.assertLogs('nxt.world', level='ERROR'):
                await self.trade_last_berry()
        self.assertEqual(self.owner.state, owner_before)
        self.assertEqual(self.db.load(self.owner.id), owner_before)
        self.assertEqual(self.peer.state['items'], peer_items)
        self.assertEqual(self.db.load(self.peer.id), self.peer.state)
        self.assertNotIn(2119, self.peer.state['adventure'].get('kantoFlags', []))
        self.assertFalse(self.powder_jar_option(self.peer)['ready'])

    async def safari_reception(self):
        state = copy.deepcopy(self.owner.state)
        state.update(map=safari.GATE, x=7, y=4, direction='up')
        await self.world.commit(self.owner, state)

    async def safari_admit(self):
        await self.world.dispatch(self.owner, {'op': 'npc', 'npc': 1, 'map': safari.GATE, 'action': 'safari_enter'})

    async def test_safari_admission_saves_exact_fee_balls_budget_and_rejects_duplicate(self):
        await self.safari_reception()
        funds = self.owner.state['money']
        peer = copy.deepcopy(self.peer.state)
        await self.safari_admit()
        saved = self.db.load(self.owner.id)
        self.assertEqual(saved['money'], funds - 500)
        self.assertEqual(saved['items'][safari.BALL], 30)
        self.assertEqual(saved['safari']['steps'], 600)
        self.assertEqual(saved['map'], 'kanto_1_63')
        self.assertEqual(self.world.item_context(saved)['safari'], {'steps': 600, 'balls': 30})
        with self.assertRaises(RequestError):
            await self.safari_admit()
        self.assertEqual(self.db.load(self.owner.id), saved)
        self.assertEqual(self.peer.state, peer)

    async def test_safari_failed_admission_never_charges_or_grants_session_resources(self):
        await self.safari_reception()
        before = copy.deepcopy(self.owner.state)
        with patch.object(self.db, 'save_many', side_effect=OSError('admission storage failure')):
            with self.assertLogs('nxt.world', level='ERROR'):
                with self.assertRaisesRegex(RequestError, 'database'):
                    await self.safari_admit()
        self.assertEqual(self.owner.state, before)
        self.assertEqual(self.db.load(self.owner.id), before)

    async def test_safari_step_budget_ignores_blocked_move_and_expiry_returns_to_reception(self):
        await self.safari_reception()
        await self.safari_admit()
        m = self.content.maps[self.owner.state['map']]
        pair = next((x, y, direction) for y in range(m['height']) for x in range(m['width'])
                    for dx, dy, direction in [(1, 0, 'right'), (-1, 0, 'left'), (0, 1, 'down'), (0, -1, 'up')]
                    if self.world.walkable(m, x, y, state=self.owner.state)
                    and self.world.walkable(m, x+dx, y+dy, from_elevation=m['elevation'][y*m['width']+x], state=self.owner.state)
                    and not any(w['x'] == x+dx and w['y'] == y+dy for w in m['warps']))
        state = copy.deepcopy(self.owner.state)
        state.update(x=pair[0], y=pair[1])
        state['safari']['steps'] = 1
        await self.world.commit(self.owner, state)
        with patch.object(self.world, 'walkable', return_value=False):
            await self.world.dispatch(self.owner, {'op': 'move', 'seq': 1, 'direction': pair[2]})
        self.assertEqual(self.owner.state['safari']['steps'], 1)
        self.owner.last_move = 0
        await self.world.dispatch(self.owner, {'op': 'move', 'seq': 2, 'direction': pair[2]})
        saved = self.db.load(self.owner.id)
        self.assertEqual(saved['map'], safari.GATE)
        self.assertNotIn('safari', saved)
        self.assertNotIn(safari.BALL, saved['items'])

    async def test_safari_balls_cannot_be_traded_and_are_removed_when_leaving(self):
        await self.safari_reception()
        await self.safari_admit()
        self.assertFalse(self.content.items[safari.BALL]['tradable'])
        with self.assertRaisesRegex(RequestError, 'cannot be traded'):
            self.world.check_offer(self.owner, {'items': {safari.BALL: 1}})
        await self.world.relocate_saved(self.owner, 'kanto_3_0')
        saved = self.db.load(self.owner.id)
        self.assertNotIn('safari', saved)
        self.assertNotIn(safari.BALL, saved['items'])

    async def test_required_obstacle_routes_save_actions_and_allow_native_pickups(self):
        for map_id, route in OBSTACLE_ROUTES.items():
            with self.subTest(map=map_id):
                state = copy.deepcopy(self.owner.state)
                state.update(map=map_id, surf=False)
                state['adventure']['badges'] = ['kanto_4', 'kanto_6']
                state['adventure']['kantoObstacles'] = {}
                for action, npc, x, y in route['actions']:
                    state.update(x=x, y=y)
                    await self.world.commit(self.owner, state)
                    await self.world.dispatch(self.owner, {'op': 'npc', 'map': map_id, 'npc': npc,
                                                          'action': 'push_boulder' if action == 'push' else 'smash_rock'})
                    self.assertEqual(self.db.load(self.owner.id), self.owner.state)
                    state = copy.deepcopy(self.owner.state)
                state.update(x=route['stand'][0], y=route['stand'][1])
                await self.world.commit(self.owner, state)
                pickup = self.visible[f"{map_id}:{route['npc']}"]
                before = self.owner.state['items'].get(pickup['item'], 0)
                await self.world.dispatch(self.owner, {'op': 'npc', 'map': map_id, 'npc': route['npc']})
                saved = self.db.load(self.owner.id)
                self.assertEqual(saved['items'][pickup['item']], before + pickup['quantity'])
                self.assertIn(pickup['id'], saved['adventure']['itemPickups'])

    async def test_surf_crosses_native_shoreline_in_both_directions(self):
        state = copy.deepcopy(self.owner.state)
        state.update(map='kanto_3_46', x=8, y=18, surf=False)
        await self.world.commit(self.owner, state)
        await self.world.dispatch(self.owner, {'op': 'move', 'seq': 1, 'direction': 'up'})
        self.assertEqual((self.owner.state['x'], self.owner.state['y']), (8, 18))
        state = copy.deepcopy(self.owner.state)
        state['adventure']['badges'] = ['kanto_5']
        partner = self.content.new_mon('fr_7', 10, self.owner.username)
        state['creatures'].append(partner)
        state['party'].append(partner['uid'])
        await self.world.commit(self.owner, state)
        await self.world.dispatch(self.owner, {'op': 'surf', 'map': 'kanto_3_46', 'requestId': 'native-shore'})
        self.assertEqual((self.owner.state['x'], self.owner.state['y']), (8, 17))
        self.owner.last_move = 0
        await self.world.dispatch(self.owner, {'op': 'move', 'seq': 3, 'direction': 'down'})
        self.assertEqual((self.owner.state['x'], self.owner.state['y']), (8, 18))
        self.assertFalse(self.owner.state['surf'])

    async def test_visible_pickup_persists_once_and_only_for_its_owner(self):
        pickup = next(row for row in self.visible.values() if list(self.walkable_positions(row)))
        await self.place(pickup)
        before = self.owner.state['items'].get(pickup['item'], 0)
        peer_before = copy.deepcopy(self.peer.state)
        await self.world.dispatch(self.owner, {'op': 'npc', 'npc': pickup['npc'], 'map': pickup['map']})
        saved = self.db.load(self.owner.id)
        self.assertEqual(saved['items'][pickup['item']], before + pickup['quantity'])
        self.assertIn(pickup['id'], saved['adventure']['itemPickups'])
        self.assertEqual(self.peer.state, peer_before)
        self.assertEqual(self.db.load(self.peer.id), peer_before)
        with self.assertRaisesRegex(RequestError, 'already collected'):
            await self.world.dispatch(self.owner, {'op': 'npc', 'npc': pickup['npc'], 'map': pickup['map']})
        self.assertEqual(self.db.load(self.owner.id), saved)
        old = self.owner
        self.world.players.pop(old.id)
        self.owner = await self.world.join(old.id, old.username, None, asyncio.Queue(maxsize=4096))
        self.assertEqual(self.owner.state['items'][pickup['item']], before + pickup['quantity'])
        self.assertTrue(self.world.adventure.item_collected(self.owner.state, pickup))

    async def test_hidden_pickup_requires_actual_facing_tile_and_ignores_client_coordinates(self):
        pickup = self.normal_hidden()
        await self.place(pickup, adjacent=True)
        toward = self.owner.state['direction']
        away = {'up': 'down', 'down': 'up', 'left': 'right', 'right': 'left'}[toward]
        self.owner.state['direction'] = away
        self.assertNotEqual(self.world.adventure.hidden_at(self.owner.state), pickup)
        before = self.owner.state['items'].get(pickup['item'], 0)
        await self.interact(item=pickup['item'], x=pickup['x'], y=pickup['y'], pickup=pickup['id'], direction=toward)
        self.assertNotIn(pickup['id'], self.owner.state['adventure']['itemPickups'])
        self.assertEqual(self.owner.state['items'].get(pickup['item'], 0), before)
        self.owner.state['direction'] = toward
        await self.interact()
        self.assertEqual(self.db.load(self.owner.id)['items'][pickup['item']], before + pickup['quantity'])
        self.assertIn(pickup['id'], self.owner.state['adventure']['itemPickups'])

    async def test_hidden_pickup_stale_map_rejected_without_inventory_or_progress_change(self):
        pickup = self.normal_hidden()
        await self.place(pickup, adjacent=True)
        before = copy.deepcopy(self.owner.state)
        with self.assertRaisesRegex(RequestError, 'another map'):
            await self.interact(map='johto_3_0')
        self.assertEqual(self.owner.state, before)
        self.assertEqual(self.db.load(self.owner.id), before)

    async def test_hidden_pickup_storage_failure_rolls_back_inventory_and_collection(self):
        pickup = self.normal_hidden()
        await self.place(pickup, adjacent=True)
        before = copy.deepcopy(self.owner.state)
        with patch.object(self.db, 'save_many', side_effect=OSError('fixture storage failure')):
            with self.assertLogs('nxt.world', level='ERROR'):
                with self.assertRaisesRegex(RequestError, 'database'):
                    await self.interact()
        self.assertEqual(self.owner.state, before)
        self.assertEqual(self.db.load(self.owner.id), before)
        await self.interact()
        self.assertIn(pickup['id'], self.db.load(self.owner.id)['adventure']['itemPickups'])

    async def test_hidden_pickup_full_stack_is_not_marked_collected(self):
        pickup = self.normal_hidden()
        await self.place(pickup, adjacent=True)
        state = copy.deepcopy(self.owner.state)
        state['items'][pickup['item']] = 999
        await self.world.commit(self.owner, state)
        before = copy.deepcopy(self.owner.state)
        with self.assertRaisesRegex(RequestError, 'Make room'):
            await self.interact()
        self.assertEqual(self.owner.state, before)
        self.assertEqual(self.db.load(self.owner.id), before)

    async def test_hidden_coins_require_coin_case_and_preserve_overflow_cache(self):
        pickup = next(p for p in self.hidden.values() if p.get('rewardType') == 'coins')
        await self.place(pickup, adjacent=True)
        before = copy.deepcopy(self.owner.state)
        with self.assertRaisesRegex(RequestError, 'Coin Case'):
            await self.interact()
        self.assertEqual(self.owner.state, before)
        state = copy.deepcopy(self.owner.state)
        state['items']['fr_coincase'] = 1
        state['coins'] = 9999
        await self.world.commit(self.owner, state)
        before = copy.deepcopy(self.owner.state)
        with self.assertRaisesRegex(RequestError, 'Make room'):
            await self.interact()
        self.assertEqual(self.owner.state, before)
        self.assertEqual(self.db.load(self.owner.id), before)
        state = copy.deepcopy(self.owner.state)
        state['coins'] = 0
        await self.world.commit(self.owner, state)
        await self.interact()
        saved = self.db.load(self.owner.id)
        self.assertEqual(saved['coins'], pickup['quantity'])
        self.assertEqual(saved['items']['fr_coincase'], 1)
        self.assertIn(pickup['id'], saved['adventure']['itemPickups'])

    async def test_special_underfoot_item_requires_using_itemfinder_on_its_exact_tile(self):
        pickup = next(p for p in self.hidden.values() if p.get('requiresItemfinder')
                      and self.world.walkable(self.content.maps[p['map']], p['x'], p['y'], surf=True, state=self.owner.state))
        await self.place(pickup, adjacent=True)
        state = copy.deepcopy(self.owner.state)
        state['items']['fr_itemfinder'] = 1
        await self.world.commit(self.owner, state)
        before = self.owner.state['items'].get(pickup['item'], 0)
        self.assertIsNone(self.world.adventure.hidden_at(self.owner.state))
        await self.world.dispatch(self.owner, {'op': 'use', 'item': 'fr_itemfinder', 'requestId': 'finder-nearby'})
        self.assertNotIn(pickup['id'], self.owner.state['adventure']['itemPickups'])
        state = copy.deepcopy(self.owner.state)
        state.update(x=pickup['x'], y=pickup['y'])
        await self.world.commit(self.owner, state)
        self.assertIsNone(self.world.adventure.hidden_at(self.owner.state))
        await self.world.dispatch(self.owner, {'op': 'use', 'item': 'fr_itemfinder', 'requestId': 'finder-underfoot'})
        saved = self.db.load(self.owner.id)
        self.assertEqual(saved['items'][pickup['item']], before + pickup['quantity'])
        self.assertEqual(saved['items']['fr_itemfinder'], 1)
        self.assertIn(pickup['id'], saved['adventure']['itemPickups'])

    async def test_same_native_flag_in_johto_does_not_collect_a_kanto_item(self):
        johto = {p['sourceFlag']: p for p in self.world.adventure.item_pickups.values()
                 if p['map'].startswith('johto_') and p.get('sourceFlag')}
        native = next(p for p in self.visible.values() if p['sourceFlag'] in johto)
        other = johto[native['sourceFlag']]
        state = self.world.adventure.collect_item(self.owner.state, other)
        self.assertFalse(self.world.adventure.item_collected(state, native))
        self.assertNotIn(native['id'], self.world.adventure.public(state)['itemPickups'])
        state = self.world.adventure.collect_item(state, native)
        self.assertIn(other['id'], state['adventure']['itemPickups'])
        self.assertIn(native['id'], state['adventure']['itemPickups'])

    async def test_native_no_effect_item_does_not_consume_or_save_a_success_receipt(self):
        state = copy.deepcopy(self.owner.state)
        state['items']['fr_potion'] = 2
        self.content.heal(state['creatures'][0])
        await self.world.commit(self.owner, state)
        before = copy.deepcopy(self.owner.state)
        command = {'op': 'use', 'item': 'fr_potion', 'uid': state['party'][0], 'requestId': 'native-no-effect'}
        with self.assertRaisesRegex(RequestError, 'no effect'):
            await self.world.dispatch(self.owner, command)
        self.assertEqual(self.owner.state, before)
        self.assertEqual(self.db.load(self.owner.id), before)
        state = copy.deepcopy(self.owner.state)
        state['creatures'][0]['hp'] = 1
        await self.world.commit(self.owner, state)
        await self.world.dispatch(self.owner, command)
        self.assertEqual(self.owner.state['items']['fr_potion'], 1)
        self.assertEqual(self.owner.state['creatures'][0]['hp'], min(21, self.content.stats(self.owner.state['creatures'][0])[0]))
        saved = self.db.load(self.owner.id)
        await self.world.dispatch(self.owner, command)
        self.assertEqual(self.db.load(self.owner.id), saved)

    async def test_all_published_field_positions_have_a_real_interaction_tile(self):
        # The Route 10 Super Potion is inspected from a tile occupied by a
        # native Cut tree. Audit post-Cut access; the separate Cut suite checks
        # earning the licence and clearing trees through the real command.
        self.owner.state['adventure']['badges'].append('kanto_2')
        self.owner.state['adventure']['cutTrees'] = {
            key: [o['id'] for o in m['objects'] if o['graphics'] == 95]
            for key, m in self.content.maps.items() if key.startswith('kanto_')
        }
        unreachable = []
        for row in [*self.visible.values(), *self.hidden.values()]:
            m = self.content.maps[row['map']]
            self.assertTrue(0 <= row['x'] < m['width'] and 0 <= row['y'] < m['height'], row['id'])
            self.assertTrue(m.get('playable', True), row['id'])
            if not list(self.walkable_positions(row)):
                unreachable.append((row['id'], m['name'], row['x'], row['y']))
        self.assertEqual(unreachable, [], 'Pickup has no walkable own/adjacent interaction tile.')

    async def test_all_field_items_are_reachable_from_native_entries_after_required_progress(self):
        """Directed ledges, cleared trees, native doors and statue state changes.

        This audits each map after its requirements are earned. It does not
        claim an automated full-story playthrough from a new account.
        """
        base = copy.deepcopy(self.owner.state)
        base['items'].update({k: 1 for k in self.content.items})
        base['adventure']['badges'] = [f'kanto_{i}' for i in range(1, 9)]
        base['adventure']['trainers'] = {k: True for k in self.content.data['adventureRom']['trainers']}
        base['adventure']['storyEvents'] = [e['id'] for e in self.content.data.get('adventure', {}).get('storyEvents', [])]
        base['adventure']['cutTrees'] = {
            key: [o['id'] for o in m['objects'] if o['graphics'] == 95]
            for key, m in self.content.maps.items() if key.startswith('kanto_')}
        catalog = self.content.data['kantoFieldServices']
        base['kantoField'] = {'doors': [d['id'] for d in catalog.get('doors', [])]}
        entries = defaultdict(set)
        for source in self.content.maps.values():
            for warp in source['warps']:
                if warp.get('access', {}).get('arrival'):
                    entries[warp['target']].add(tuple(warp['access']['arrival']))
            for link in source['connections']:
                target = self.content.maps.get(link['target'])
                if not target:
                    continue
                direction, offset = link['direction'], link['offset']
                if direction in (1, 2):
                    entries[target['id']].update((x-offset, 0 if direction == 1 else target['height']-1)
                                                 for x in range(source['width']))
                else:
                    entries[target['id']].update((target['width']-1 if direction == 3 else 0, y-offset)
                                                 for y in range(source['height']))
        for elevator in catalog.get('elevators', []):
            for floor in elevator['destinations']:
                entries[floor['id']].add(tuple(floor['arrival']))
        by_map = defaultdict(list)
        for row in [*self.visible.values(), *self.hidden.values()]:
            by_map[row['map']].append(row)
        unreachable = []
        for key, pickups in by_map.items():
            m = self.content.maps[key]
            switch = next((s for s in catalog.get('mansionSwitches', []) if s['map'] == key), None)
            scene = copy.deepcopy(base)
            scene.update(map=key, surf=False)
            for action, npc, x, y in OBSTACLE_ROUTES.get(key, {}).get('actions', []):
                scene.update(x=x, y=y)
                obj = next(o for o in m['objects'] if o['id'] == npc)
                scene = kanto_obstacles.act(self.content, scene, obj, action, self.world.walkable)
            variants = [copy.deepcopy(scene) for _ in range(2 if switch else 1)]
            walkable = []
            for flag, state in enumerate(variants):
                state['map'] = key
                state['adventure']['kantoFlags'] = [switch['sourceFlag']] if switch and flag else []
                walkable.append({(x, y) for y in range(m['height']) for x in range(m['width'])
                                 if self.world.walkable(m, x, y, surf=True, state=state)})
            seeds = entries[key] or {tuple(m['spawn'])}
            todo = deque((x, y, flag) for x, y in seeds for flag in range(len(variants))
                         if (x, y) in walkable[flag])
            seen = set(todo)
            while todo:
                x, y, flag = todo.popleft()
                variants[flag].update(x=x, y=y, surf=True)
                destinations = []
                for dx, dy, ledge in ((1, 0, 56), (-1, 0, 57), (0, -1, 58), (0, 1, 59)):
                    nx, ny = x+dx, y+dy
                    if not (0 <= nx < m['width'] and 0 <= ny < m['height']):
                        continue
                    behavior = m['behavior'][ny*m['width']+nx]
                    if behavior == ledge:
                        nx, ny = nx+dx, ny+dy
                    if (nx, ny) not in walkable[flag]:
                        continue
                    before = m['elevation'][y*m['width']+x]
                    after = m['elevation'][ny*m['width']+nx]
                    if (behavior not in (56, 57, 58, 59) and before not in (0, 15) and after not in (0, 15, before)
                            and not self.world.walkable(m, nx, ny, surf=True, from_elevation=before,
                                                        from_behavior=m['behavior'][y*m['width']+x], state=variants[flag])):
                        continue
                    destinations.append((nx, ny, flag))
                if switch and any(abs(x-sx)+abs(y-sy) == 1 for sx, sy in switch['switches']):
                    if (x, y) in walkable[1-flag]:
                        destinations.append((x, y, 1-flag))
                for point in destinations:
                    if point not in seen:
                        seen.add(point)
                        todo.append(point)
            for row in pickups:
                points = ([(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)] if row['id'] in self.visible
                          else [(0, 0)] if row.get('underfootOnly')
                          else [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)])
                if not any((row['x']+dx, row['y']+dy, flag) in seen
                           and (row['id'] in self.visible or not row.get('elevation')
                                or m['elevation'][(row['y']+dy)*m['width']+row['x']+dx] == row['elevation'])
                           for dx, dy in points for flag in range(len(variants))):
                    unreachable.append((row['id'], m['name'], row['x'], row['y']))
        self.assertEqual(unreachable, [], 'A native pickup has no route from a published entrance.')

    async def test_client_visible_pickups_match_server_and_hidden_items_stay_hidden(self):
        cache = {}
        for row in self.visible.values():
            key = row['map']
            if key not in cache:
                cache[key] = json.loads((ROOT / f'Client/app/assets/world/maps/{key}.json').read_text())
            server = next(o for o in self.content.maps[key]['objects'] if o['id'] == row['npc'])
            client = next(o for o in cache[key]['objects'] if o['id'] == row['npc'])
            self.assertEqual(server['itemPickup'], row['id'])
            self.assertEqual(client['itemPickup'], row['id'])
            self.assertEqual((server['x'], server['y']), (row['x'], row['y']))
        hidden_ids = set(self.hidden)
        for m in self.content.maps.values():
            self.assertFalse(hidden_ids & {o.get('itemPickup') for o in m['objects']})
        client = json.loads((ROOT / 'Client/app/assets/world/client.json').read_text())
        for key, item in self.content.items.items():
            if item.get('source') == 'kanto':
                self.assertEqual(client['items'][key], item)
                self.assertFalse(339 <= item['sourceId'] <= 346, 'HM items are excluded from this feature.')


if __name__ == '__main__':
    unittest.main()
