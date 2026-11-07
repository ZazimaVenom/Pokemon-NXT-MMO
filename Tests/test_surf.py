"""Surf acceptance against native tiles, production commands, SQLite and TCP.

Only travel and badge/party setup are shortened by fixtures. Boarding, movement,
shore exit, command validation, save failures and network replication are real.
The rules intentionally replace an HM move with a Water-type party companion.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
sys.path.insert(0, str(ROOT / 'Tests'))
from nxt.config import Settings
from nxt.content import Content
from nxt.security import RequestError
from nxt.store import Store
from nxt.world import World, WATER
import test_adventure_network as network_fixture

# Both ROM-derived shorelines cross land elevation 3 to water elevation 1.
SHORES = {
    'kanto': {'map': 'kanto_3_0', 'x': 7, 'y': 16, 'direction': 'down', 'badge': 'kanto_5'},
    'johto': {'map': 'johto_1_7', 'x': 26, 'y': 5, 'direction': 'down', 'badge': 'johto_4'},
}


class SurfIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / 'config.ini'
        path.write_bytes((ROOT / 'Build/config_templates/Server/config.ini').read_bytes())
        settings = Settings.load(path)
        settings.config.set('database', 'backend', 'sqlite')
        settings.config.set('world', 'allow_alpha_surf', 'false')
        self.settings = dataclasses.replace(settings, encounter_chance=0)
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.world = World(self.content, self.db, self.settings)
        state = self.world.initial('SurfOwner', 'Johto', 'fr_4', 0)
        self.uid = self.db.create('SurfOwner', 'isolated-not-network-hash', state)
        self.player = await self.world.join(self.uid, 'SurfOwner', None, asyncio.Queue(maxsize=4096))
        self.seq = 0

    async def asyncTearDown(self):
        self.world.players.clear()
        self.db.close()
        self.temp.cleanup()

    def packets(self):
        out = []
        while not self.player.queue.empty():
            out.append(self.player.queue.get_nowait())
        return out

    async def stage(self, region='kanto', *, species='fr_130', badge=True, in_party=True, fainted=False):
        shore = SHORES[region]
        state = copy.deepcopy(self.player.state)
        state.update({key: shore[key] for key in ('map', 'x', 'y', 'direction')})
        self.world.adventure.visit(state, shore['map'])
        state['surf'] = False
        state['adventure']['badges'] = [shore['badge']] if badge else []
        mon = self.content.new_mon(species, 10, self.player.username)
        if fainted:
            mon['hp'] = 0
        state['creatures'].append(mon)
        if in_party:
            state['party'].append(mon['uid'])
        await self.world.commit(self.player, state)
        self.packets()
        return mon

    def command(self, request='surf-test', **extra):
        state = self.player.state
        return {'op': 'surf', 'map': state['map'], 'x': state['x'], 'y': state['y'],
                'direction': state['direction'], 'requestId': request, **extra}

    async def move(self, direction):
        self.seq += 1
        self.player.last_move = 0
        await self.world.dispatch(self.player, {'op': 'move', 'seq': self.seq, 'direction': direction})

    async def cold_restart(self):
        self.world.players.clear()
        self.db.close()
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.world = World(self.content, self.db, self.settings)
        self.player = await self.world.join(self.uid, 'SurfOwner', None, asyncio.Queue(maxsize=4096))

    async def test_native_kanto_and_johto_board_traverse_and_auto_exit_without_changing_lead(self):
        for region, shore in SHORES.items():
            with self.subTest(region=region):
                partner = await self.stage(region)
                party = list(self.player.state['party'])
                m = self.content.maps[shore['map']]
                source = shore['y'] * m['width'] + shore['x']
                target = source + m['width']
                self.assertEqual((m['elevation'][source], m['elevation'][target]), (3, 1))
                self.assertEqual(m['collision'][target], 0)
                self.assertIn(m['behavior'][target], WATER)
                await self.world.dispatch(self.player, self.command('native-' + region))
                self.assertEqual((self.player.state['x'], self.player.state['y']), (shore['x'], shore['y'] + 1))
                self.assertTrue(self.player.state['surf'])
                selected = self.player.entity()['surfPokemon']
                self.assertEqual(selected['species'], 'fr_130')
                self.assertIn(self.player.state['surfPokemon']['uid'], party)
                self.assertEqual(self.player.entity()['follower'], 'fr_4')
                self.assertEqual(self.player.state['party'], party)
                self.assertEqual(self.db.load(self.uid), self.player.state)
                await self.move('down')
                self.assertEqual(self.player.state['y'], shore['y'] + 2)
                await self.move('up')
                await self.move('up')
                self.assertEqual((self.player.state['x'], self.player.state['y']), (shore['x'], shore['y']))
                self.assertFalse(self.player.state['surf'])
                self.assertFalse(self.player.entity().get('surfPokemon'))
                self.assertEqual(self.player.state['party'], party)
                self.assertEqual(self.db.load(self.uid), self.player.state)

    async def test_regional_badge_is_required_independent_of_birth_region_and_forged_unlock(self):
        for region in SHORES:
            with self.subTest(region=region):
                await self.stage(region, badge=False)
                state = copy.deepcopy(self.player.state)
                state['adventure']['badges'] = [SHORES['johto' if region == 'kanto' else 'kanto']['badge']]
                state['adventure']['unlocks'].append('surf_' + region)
                await self.world.commit(self.player, state)
                before = copy.deepcopy(self.player.state)
                with self.assertRaises(RequestError):
                    await self.world.dispatch(self.player, self.command('wrong-badge-' + region))
                self.assertEqual(self.player.state, before)
                self.assertEqual(self.db.load(self.uid), before)
                state = copy.deepcopy(before)
                state['adventure']['badges'].append(SHORES[region]['badge'])
                await self.world.commit(self.player, state)
                await self.world.dispatch(self.player, self.command('right-badge-' + region))
                self.assertTrue(self.player.state['surf'])

    async def test_water_type_in_storage_cannot_enable_surf(self):
        await self.stage(in_party=False)
        before = copy.deepcopy(self.player.state)
        with self.assertRaises(RequestError):
            await self.world.dispatch(self.player, self.command())
        self.assertEqual(self.player.state, before)
        self.assertEqual(self.db.load(self.uid), before)

    async def test_non_water_party_cannot_enable_surf(self):
        await self.stage(species='fr_25')
        before = copy.deepcopy(self.player.state)
        with self.assertRaises(RequestError):
            await self.world.dispatch(self.player, self.command())
        self.assertEqual(self.player.state, before)

    async def test_fainted_dual_type_party_water_partner_requires_no_hm(self):
        partner = await self.stage(fainted=True)
        self.assertEqual(self.content.species[partner['species']]['types'], [11, 2])
        self.assertNotIn(57, [move['id'] for move in partner['moves']])
        await self.world.dispatch(self.player, self.command())
        self.assertEqual(self.player.state['surfPokemon']['uid'], partner['uid'])
        self.assertEqual(self.player.state['creatures'][-1]['hp'], 0)

    async def test_button_finds_legal_adjacent_water_when_facing_away(self):
        await self.stage()
        state = copy.deepcopy(self.player.state)
        state['direction'] = 'up'
        await self.world.commit(self.player, state)
        await self.world.dispatch(self.player, self.command())
        self.assertEqual((self.player.state['x'], self.player.state['y']), (7, 17))
        self.assertEqual(self.player.state['direction'], 'down')

    async def test_inland_activation_and_client_target_coordinates_cannot_teleport(self):
        await self.stage()
        state = copy.deepcopy(self.player.state)
        state.update(x=10, y=10)
        await self.world.commit(self.player, state)
        before = copy.deepcopy(self.player.state)
        for command in (self.command('inland'), self.command('forged-origin', x=7, y=16)):
            with self.assertRaises(RequestError):
                await self.world.dispatch(self.player, command)
            self.assertEqual(self.player.state, before)
            self.assertEqual(self.db.load(self.uid), before)

    async def test_native_wall_occupied_water_and_raised_bank_reject_boarding(self):
        await self.stage()
        for map_id, x, y, direction in (
                ('kanto_1_4', 47, 2, 'up'),       # S.S. Anne rail: water collision 1.
                ('kanto_3_8', 22, 7, 'right'),   # Cinnabar water occupied by a native NPC.
                ('kanto_1_64', 35, 17, 'up')):   # Safari raised bank: elevation 4, not a shore.
            with self.subTest(map=map_id):
                state = copy.deepcopy(self.player.state)
                state.update(map=map_id, x=x, y=y, direction=direction)
                await self.world.commit(self.player, state)
                before = copy.deepcopy(self.player.state)
                with self.assertRaises(RequestError):
                    await self.world.dispatch(self.player, self.command('blocked-' + map_id))
                self.assertEqual(self.player.state, before)
                self.assertEqual(self.db.load(self.uid), before)

    async def test_surf_cannot_climb_native_raised_bank(self):
        await self.stage()
        await self.world.dispatch(self.player, self.command())
        state = copy.deepcopy(self.player.state)
        state.update(map='kanto_1_64', x=35, y=16, direction='down')
        await self.world.commit(self.player, state)
        await self.move('down')
        self.assertEqual((self.player.state['x'], self.player.state['y']), (35, 16))
        self.assertTrue(self.player.state['surf'])

    async def test_failed_boarding_save_rolls_back_partner_position_and_receipt(self):
        await self.stage()
        before = copy.deepcopy(self.player.state)
        self.packets()
        command = self.command()
        with patch.object(self.db, 'save_many', side_effect=OSError('boarding save failed')):
            with self.assertLogs('nxt.world', level='ERROR'):
                with self.assertRaises(RequestError):
                    await self.world.dispatch(self.player, command)
        self.assertEqual(self.player.state, before)
        self.assertEqual(self.db.load(self.uid), before)
        self.assertFalse(self.packets())
        await self.world.dispatch(self.player, command)
        self.assertTrue(self.player.state['surf'])

    async def test_failed_shore_exit_save_keeps_rider_on_water(self):
        await self.stage()
        await self.world.dispatch(self.player, self.command())
        before = copy.deepcopy(self.player.state)
        follower = (self.player.fx, self.player.fy)
        self.packets()
        with patch.object(self.db, 'save_many', side_effect=OSError('shore exit save failed')):
            with self.assertLogs('nxt.world', level='ERROR'):
                with self.assertRaises(RequestError):
                    await self.move('up')
        self.assertEqual(self.player.state, before)
        self.assertEqual(self.db.load(self.uid), before)
        self.assertEqual((self.player.fx, self.player.fy), follower)
        self.assertFalse(any(p['type'] in ('state', 'audio') for p in self.packets()))

    async def test_boarding_receipt_replay_never_toggles_or_moves_twice(self):
        await self.stage()
        command = self.command()
        await self.world.dispatch(self.player, command)
        before = copy.deepcopy(self.player.state)
        await self.world.dispatch(self.player, command)
        self.assertEqual(self.player.state, before)
        self.assertEqual(self.db.load(self.uid), before)
        with self.assertRaises(RequestError):
            await self.world.dispatch(self.player, {**command, 'x': command['x'] + 1})
        self.assertEqual(self.player.state, before)

    async def test_stale_map_or_origin_request_changes_nothing(self):
        await self.stage()
        before = copy.deepcopy(self.player.state)
        for extra in ({'map': 'johto_1_7'}, {'x': 8}, {'direction': 'left'}):
            with self.subTest(extra=extra):
                with self.assertRaises(RequestError):
                    await self.world.dispatch(self.player, self.command(**extra))
                self.assertEqual(self.player.state, before)

    async def test_cold_restart_restores_water_partner_badge_and_unchanged_party(self):
        partner = await self.stage()
        party = list(self.player.state['party'])
        command = self.command()
        await self.world.dispatch(self.player, command)
        before = copy.deepcopy(self.player.state)
        await self.cold_restart()
        self.assertEqual(self.player.state, before)
        self.assertEqual(self.player.state['surfPokemon']['uid'], partner['uid'])
        self.assertEqual(self.player.state['party'], party)
        await self.world.dispatch(self.player, command)
        self.assertEqual(self.player.state, before)
        await self.move('up')
        self.assertFalse(self.player.state['surf'])

    async def test_reordering_party_while_riding_keeps_selected_water_partner(self):
        partner = await self.stage()
        state = copy.deepcopy(self.player.state)
        second = self.content.new_mon('fr_7', 10, self.player.username)
        state['creatures'].append(second)
        state['party'].append(second['uid'])
        await self.world.commit(self.player, state)
        await self.world.dispatch(self.player, self.command())
        order = list(reversed(self.player.state['party']))
        await self.world.dispatch(self.player, {'op': 'party', 'party': order})
        self.assertEqual(self.player.state['surfPokemon']['uid'], partner['uid'])
        self.assertEqual(self.player.state['party'], order)
        self.assertEqual(self.db.load(self.uid), self.player.state)

    async def test_trading_away_only_water_partner_cannot_commit_either_owner(self):
        partner = await self.stage()
        await self.world.dispatch(self.player, self.command())
        other = self.world.initial('SurfTradePeer', 'Kanto', 'fr_4', 0)
        other.update(map='kanto_3_0', x=8, y=16)
        other_id = self.db.create('SurfTradePeer', 'isolated-trade-fixture', other)
        peer = await self.world.join(other_id, 'SurfTradePeer', None, asyncio.Queue(maxsize=2048))
        before = {player.id: copy.deepcopy(player.state) for player in (self.player, peer)}
        await self.world.dispatch(self.player, {'op': 'invite', 'kind': 'trade', 'target': peer.id})
        await self.world.dispatch(peer, {'op': 'invite.answer', 'id': next(iter(self.world.invites)), 'accept': True})
        trade = self.world.trades[self.player.trade]
        await self.world.dispatch(self.player, {'op': 'trade', 'id': trade['id'], 'action': 'offer',
            'revision': trade['revision'], 'offer': {'pokemon': [partner['uid']], 'items': {}, 'money': 0}})
        for player in (self.player, peer):
            await self.world.dispatch(player, {'op': 'trade', 'id': trade['id'], 'action': 'lock', 'revision': trade['revision']})
        await self.world.dispatch(self.player, {'op': 'trade', 'id': trade['id'], 'action': 'confirm',
            'revision': trade['revision'], 'digest': self.world.trade_digest(trade)})
        with self.assertRaisesRegex(RequestError, 'Water'):
            await self.world.dispatch(peer, {'op': 'trade', 'id': trade['id'], 'action': 'confirm',
                'revision': trade['revision'], 'digest': self.world.trade_digest(trade)})
        for player in (self.player, peer):
            self.assertEqual(player.state, before[player.id])
            self.assertEqual(self.db.load(player.id), before[player.id])

    async def test_legacy_unlicensed_water_save_is_recovered_and_saved_on_login(self):
        legacy = copy.deepcopy(self.player.state)
        legacy.update(map='kanto_3_0', x=7, y=17, surf=True)
        legacy['surfAnchor'] = {'map': 'kanto_3_0', 'x': 7, 'y': 16, 'direction': 'down'}
        self.db.save_many([(self.uid, legacy)])
        await self.cold_restart()
        self.assertFalse(self.player.state['surf'])
        self.assertEqual((self.player.state['x'], self.player.state['y']), (7, 16))
        self.assertFalse(self.player.entity().get('surfPokemon'))
        self.assertNotIn('kanto_5', self.player.state['adventure']['badges'])
        self.assertEqual(self.db.load(self.uid), self.player.state)

    async def test_home_transition_clears_rider_and_old_request_cannot_board_new_map(self):
        await self.stage()
        command = self.command()
        await self.world.dispatch(self.player, command)
        await self.world.dispatch(self.player, {'op': 'unstuck'})
        before = copy.deepcopy(self.player.state)
        self.assertEqual(before['map'], self.content.data['homes']['Johto'])
        self.assertFalse(before['surf'])
        self.assertFalse(self.player.entity().get('surfPokemon'))
        try:
            await self.world.dispatch(self.player, command)
        except RequestError:
            pass
        self.assertEqual(self.player.state, before)
        self.assertEqual(self.db.load(self.uid), before)


class SurfNetworkTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(network_fixture.AdventureNetworkTests.setUpClass.__func__)
    asyncSetUp = network_fixture.AdventureNetworkTests.asyncSetUp
    asyncTearDown = network_fixture.AdventureNetworkTests.asyncTearDown
    start_service = network_fixture.AdventureNetworkTests.start_service
    stop_service = network_fixture.AdventureNetworkTests.stop_service
    auth = network_fixture.AdventureNetworkTests.auth
    pair = network_fixture.AdventureNetworkTests.pair
    close_account = network_fixture.AdventureNetworkTests.close_account
    stage = network_fixture.AdventureNetworkTests.stage

    async def test_rejected_surf_error_correlates_request_without_mutating_owner(self):
        owner, uid, _ = await self.auth('SurfDenied', 'fr_4')
        before = copy.deepcopy(self.db.load(uid))
        await owner.send(op='surf', map=before['map'], requestId='network-surf-denied')
        error = await owner.until('error')
        self.assertEqual(error['operation'], 'surf')
        self.assertEqual(error['requestId'], 'network-surf-denied')
        self.assertEqual(self.db.load(uid), before)
        self.assertEqual(self.world.players[uid].state, before)

    async def test_native_shore_boarding_replicates_selected_partner_and_preserves_private_owner_state(self):
        (owner, uid, initial), (peer, pid, _) = await self.pair()

        def prepare(state):
            state.update(map='kanto_3_0', x=7, y=16, direction='down')
            state['adventure']['badges'] = ['kanto_5']
            mon = self.content.new_mon('fr_130', 10, 'Akumavenom')
            state['creatures'].append(mon)
            state['party'].append(mon['uid'])

        await self.stage(owner, uid, prepare)
        await self.stage(peer, pid, lambda state: state.update(map='kanto_3_0', x=8, y=16))
        party = list(self.world.players[uid].state['party'])
        peer_before = copy.deepcopy(self.db.load(pid))
        await self.world.tick()
        await owner.barrier()
        await peer.barrier()
        await owner.send(op='surf', map='kanto_3_0', x=7, y=16, direction='down', requestId='network-board')
        boarded = await owner.until('state', lambda packet: packet.get('surfContext', {}).get('active'))
        self.assertEqual(boarded['party'], party)
        await self.world.tick()
        packets = await peer.barrier()
        entity = next(entity for packet in packets if packet['type'] == 'scene'
                      for entity in packet.get('players', []) if entity['id'] == uid)
        self.assertTrue(entity['surf'])
        self.assertEqual(entity['surfPokemon']['species'], 'fr_130')
        self.assertEqual(entity['follower'], initial['creatures'][0]['species'])
        self.assertFalse(any(packet['type'] == 'state' for packet in packets))
        self.assertEqual(self.db.load(pid), peer_before)
        self.assertEqual(self.db.load(uid), self.world.players[uid].state)
        await self.close_account(owner, uid)
        owner, same_uid, restored = await self.auth('Akumavenom', 'fr_4', 'login')
        self.assertEqual(same_uid, uid)
        self.assertTrue(restored['surfContext']['active'])
        self.assertEqual(restored['party'], party)
        await owner.send(op='move', seq=1, direction='up')
        await owner.until('move', lambda packet: packet.get('accepted'))
        await owner.barrier()
        self.assertFalse(self.db.load(uid)['surf'])
        self.assertEqual(self.db.load(uid)['party'], party)
