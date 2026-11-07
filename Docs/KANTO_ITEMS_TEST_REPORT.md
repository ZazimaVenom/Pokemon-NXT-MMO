> Historical verification for 0.6.11-alpha, retained with its original evidence.
> The current 0.6.12-alpha release is covered by `REGIONAL_SURF_TEST_REPORT.md`;
> current native content parity is recorded in `KANTO_ITEM_COVERAGE.json`.

# Kanto item release verification — 0.6.11-alpha

This report describes checks actually executed on the supplied source baseline
and the extracted FireRed Rev 1 data. It is not a native Windows acceptance
certificate or a claim of complete cartridge story parity.

## Executed checks

| Check | Result | Evidence |
| --- | --- | --- |
| Full Python regression discovery | 802 cases: 800 passed, one Windows-only skip, one launcher line-ending failure subsequently corrected | `evidence/kanto_python_tests.txt` |
| Bootstrap recheck after restoring CRLF | 25 cases: 24 passed; the same Windows-only case skipped | `evidence/kanto_bootstrap_recheck.txt` |
| Build and source-selection checks after adding the three Kanto sidecars | 28 passed | `evidence/kanto_build_recheck.txt` |
| Client interaction, registration, renderer, audio integration, battle feedback and varieties | 125 passed | `evidence/kanto_client_regressions.txt` |
| Final item, Kanto, SQLite persistence, cancellation and network trade recheck after Berry Pouch integration | 157 passed, no failures or skips | `evidence/kanto_final_items_recheck.txt` |
| Native Kanto integration and field access | All 22 passed in the final focused run | `Tests/test_kanto_items_integration.py` |
| Obstacle rules and live World/SQLite transactions | All 13 passed within the full suite | `Tests/test_kanto_obstacles.py` |
| Published data, icons, map events and server/client parity | Passed for matching pack `70d6bc69ad95f4c9fc9afabc` | `KANTO_ITEM_COVERAGE.json` |
| Final gift rules and automatic TM Case/Berry Pouch retention | 13 passed after final helper extension | `evidence/kanto_native_containers_recheck.txt` |
| Original multipart source preservation | All 18,531 baseline paths retained; no missing source/assets | Source allowlist comparison against all four original ZIPs |

The one skipped case is
`test_auto_bootstrap.NativePowerShellTests.test_bootstrap_helper_contracts_on_windows`.
It requires native Windows PowerShell and is explicitly skipped on Linux.
The initial full-run failure is retained in its evidence log. The failing
`BUILD_ALL.bat` line endings were restored to CRLF, then the entire affected
bootstrap module and build module were rerun successfully. No unresolved
regression failure is known from these checks.

## What the field proof establishes

The directed route audit covers every one of the 350 ordinary ground rewards:
167 visible pickups and 183 hidden events, including 12 coin caches. It checks
routes from native entries within each map after the required progress. It
respects collision, ledges, elevations, Surf shore transitions, cleared Cut
and story actors, native doors, Mansion switches, and legal replayed boulder
or breakable-rock solutions. All four formerly isolated obstacle rewards
also pass actual World movement/action/pickup commands.

This is a map-level route proof with earned badges, keys and story progress
provided as prerequisites. It does not establish a complete end-to-end
FireRed campaign. Story substitutions remain explicitly listed in the
acquisition audit and release notes.

The integration tests exercise production World commands with SQLite for
private collection, relogin, rejected forged coordinates, duplicate/replayed
commands, inventory limits, save failure rollback and shared-map isolation.
Safari admission, paid resources, ending conditions, non-tradable Safari
Balls and shoreline movement are included. The final focused run also checks first-Berry acquisition, consuming or trading
the last Berry, relogin, Powder Jar eligibility and failed-save rollback for
both sides of a trade. The native Berry Pouch and obtained-pouch flag persist.
Client tests verify pocket/search
state, pending receipts, contextual targets, shop stock, keyboard control,
service commands, private objects and field-state rendering instructions.

## Reproduction

Run from the combined source root with its Python dependencies installed:

```sh
python -m unittest discover -s Tests
python Tools/verify_kanto_items.py
node --test Tests/check_adventure_ui.mjs Tests/check_registration.mjs Tests/check_renderer_replication.mjs Tests/check_audio_app_integration.mjs Tests/check_battle_fx.mjs Tests/check_varieties.mjs
```

Ordinary builds use the included extracted assets. The ROM is required only
when intentionally re-running ROM extraction. `Tools/repack_content.py`
rebuilds the matching published server/client content from the sidecars.

## Remaining acceptance and parity limits

Browser preview was rejected by the environment's unavailable approval/security
check. No screenshot review or actual browser visual acceptance is claimed.
Windows/Edge launch, Windows native compilation, live MySQL deployment and a
manual complete campaign were not executed here. Validate those in the target
installation before calling this a production-approved build.

Berry Crush earning, slot-machine gambling, mystery-event ticket transport,
complete Fame Checker/Teachy TV scenes, native fishing timing and exact
VS Seeker response/team progression are not reproduced. See
`KANTO_ITEMS_RELEASE.md` and `KANTO_FIELD_ITEMS.md` for the exact implemented
behaviour and the documented NXT progression adaptations.
