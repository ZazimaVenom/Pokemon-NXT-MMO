# Regional Surf verification — 0.6.12-alpha

The source baseline for this release is the complete four-part 0.6.11-alpha
Kanto item update. This report records executed checks and does not claim native Windows or
browser screenshot acceptance.

## Executed checks

| Check | Result | Evidence |
| --- | --- | --- |
| Full Python regression discovery | 843 cases: 842 passed; one native-Windows-only skip; no failures | `evidence/surf_python_tests.txt` |
| Final runtime Surf and progress-persistence recheck | 44 passed; no failures or skips | `evidence/surf_final_runtime_recheck.txt` |
| Client interaction, registration, renderer, audio, battle feedback and varieties | 137 passed; no failures or skips | `evidence/surf_client_regressions.txt` |
| Focused Surf rules, native World/SQLite and TCP checks | 33 passed, followed by one additional passing TCP error-correlation check | `evidence/surf_focused_tests.txt` |
| Build and source-selection contracts | 28 passed | `evidence/surf_build_tests.txt` |
| Kanto item data, icons and server/client parity | Passed; pack `ed3bbfd4c3c26dff1a57e2de` | `KANTO_ITEM_COVERAGE.json`, `evidence/surf_content_verification.txt` |
| Previous source release preservation | All 19,070 baseline files retained; no missing required build files | `evidence/surf_source_preservation.json` |
| Native badge and shoreline evidence | Two valid shores and three blocked examples verified against unchanged map data | `evidence/surf_native_audit.json` |

The sole skipped case is
`test_auto_bootstrap.NativePowerShellTests.test_bootstrap_helper_contracts_on_windows`.
It requires Windows PowerShell. The final 44-test run includes all 20 native,
live-server and TCP Surf checks, all 13 pure rule checks, and 11 progress
persistence checks. It also covers the final equivalent optimization that
avoids recomputing an already supplied movement context. The full suite retains
all 350 Kanto field-reward reachability checks under the stricter shoreline
collision rules.

No known regression failure remained after these checks. These tests establish
functional behaviour in the described environment, not live production load
capacity or native Windows visual acceptance.

## Coverage

The Surf tests exercise new accounts from either starting region, actual
regional Gym victories, saved badge migration, Water-type party ownership,
dual typing, fainted field partners, no-HM movesets, native legal and blocked
shorelines, partner persistence, automatic land dismount, failed database
writes, duplicate/stale requests, party/trade protections and multiplayer
replication. Native shore fixtures include Pallet Town and Johto Route 31.

Primary reference checks confirm Kanto's fifth badge and Johto's fourth badge,
and FireRed's elevation-3 shoreline requirement:

- [FireRed field controls](https://github.com/pret/pokefirered/blob/master/src/field_control_avatar.c)
- [FireRed player and elevation rules](https://github.com/pret/pokefirered/blob/master/src/field_player_avatar.c)
- [Crystal field moves](https://github.com/pret/pokecrystal/blob/master/engine/overworld/field_moves.asm)

The Kanto/Johto badge names and leader identities also match the included
extracted Gym records. The Water-type-party rule and no-HM requirement are
intentional NXT behaviour requested for this release.

## Reproduction

```sh
python -m unittest discover -s Tests
python Tools/verify_kanto_items.py
node --test Tests/check_adventure_ui.mjs Tests/check_registration.mjs Tests/check_renderer_replication.mjs Tests/check_audio_app_integration.mjs Tests/check_battle_fx.mjs Tests/check_varieties.mjs
```

## Platform scope

Verification uses the production Python server with disposable SQLite saves,
actual WebSocket clients where indicated, and Node DOM/canvas test adapters.
No production database or account is modified by these tests. Native Windows
PowerShell, Windows/Edge launch and live MySQL deployment are not run here.
The previous browser-preview approval restriction remains; there is no claim
of screenshot-based visual acceptance. The rendered Surf composition uses
existing Pokémon assets and client canvas code.
