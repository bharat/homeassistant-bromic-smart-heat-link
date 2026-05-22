# AGENTS.md — Bromic Smart Heat Link HA Integration

This is the canonical agent guide for `bharat/homeassistant-bromic-smart-heat-link`. New Claude/Codex/Cursor sessions should read this before making changes.

## What this is

A Home Assistant custom integration for **Bromic outdoor heaters** controlled through the **Bromic Smart Heat Link** RS-232 bridge. The bridge speaks a small binary protocol over a serial link (19200 baud, 8N1); this integration discovers controllers, runs a guided learning wizard so they can be paired against existing physical remotes, and exposes them as `switch` (ON/OFF controllers) or `light` entities (Dimmer controllers, with discrete brightness levels: 0 / 25 / 50 / 75 / 100%).

Up to 50 ID locations are supported per bridge. Connection is local-only (no cloud, no MQTT). `iot_class: assumed_state` because the device gives no telemetry — sent commands are believed to have worked unless the bridge ACKs an error.

## Layout

```
.
├── README.md                   # Feature overview, hardware reqs, install, config, troubleshooting
├── CONTRIBUTING.md             # Fork/PR flow
├── socat.log                   # **Stray** dev log (see Oddities below — not in .gitignore)
│
├── custom_components/bromic_smart_heat_link/
│   ├── __init__.py             # async_setup_entry; sets PLATFORMS=[SWITCH, LIGHT]
│   ├── manifest.json           # Domain bromic_smart_heat_link; requires pyserial>=3.5
│   ├── const.py                # Serial config, protocol bytes, button maps, brightness LUT, errors
│   ├── protocol.py             # BromicProtocol: encode_command, decode_response, checksum, frame validation
│   ├── hub.py                  # BromicHub: serial I/O, retry, stats, connection callbacks
│   ├── config_flow.py          # User step + manual port entry + add/adopt + learning wizard UI
│   ├── light.py                # BromicLight (Dimmer controllers; discrete 5 brightness levels)
│   ├── switch.py               # BromicSwitch (ON/OFF controllers)
│   ├── entity.py               # BromicEntity base; device_info, command send, connection state attrs
│   ├── services.py             # learn_button, clear_controller, send_raw_command
│   ├── services.yaml
│   ├── diagnostics.py          # Diagnostics payload (redacts serial port)
│   ├── exceptions.py           # 8 exception types: BromicError → connection / timeout / protocol / learning / config
│   ├── strings.json
│   └── translations/en.json
│
├── docs/
│   └── Bromic-Smart-Heat-Link-Installation-Guide.pdf
│                               # Vendor's hardware install guide (binary; reference only)
│
├── brands/                     # icon.png / icon@2x.png / dark_icon.png / dark_icon@2x.png
├── config/                     # Dev sandbox HA config (configuration.yaml)
│
├── scripts/
│   ├── setup                   # apt + pip + act + pre-commit install
│   ├── develop                 # PYTHONPATH=custom_components hass --config ./config --debug
│   ├── lint                    # ruff format && ruff check --fix
│   ├── tty-bridge-host.sh      # On host: socat TCP:7777 ↔ /dev/ttyXXX (real serial)
│   ├── tty-bridge-container.sh # In container: PTY ↔ TCP:host:7777 (used by HA)
│   ├── serial_test.py          # Round-trip: writes a known cmd, reads response
│   ├── serial_send.py          # CLI: send raw ID/button or hex bytes
│   ├── customize.py            # Blueprint repo customizer (one-shot init tool; not used in dev)
│   └── __init__.py             # Marks scripts/ as a Python package
│
├── tests/                      # pytest suite (163 tests) using pytest-homeassistant-custom-component
│   ├── conftest.py             # Enables custom-integration discovery; loads the pytest-HA plugin
│   ├── test_smoke.py           # Loads the integration under the pinned HA version; expects SETUP_RETRY
│   ├── test_protocol.py        # Pure-function encode/decode/checksum and frame validation
│   ├── test_hub.py             # BromicHub with mocked serial.Serial: connect, send, retry, locking
│   ├── test_config_flow.py     # User step, manual port entry, add/adopt, learning wizard (hub mocked)
│   ├── test_light.py / test_switch.py / test_entity.py
│   ├── test_services.py        # learn_button, clear_controller, send_raw_command (hub mocked)
│   ├── test_diagnostics.py     # Payload shape, serial-port redaction
│   ├── test_const.py           # Protocol constants, button maps, brightness LUT, error codes
│   └── test_exceptions.py      # Exception hierarchy and BromicCommandError.error_code
│
├── .pre-commit-config.yaml     # ruff + EOF/whitespace + check-yaml
├── .ruff.toml                  # Per-project ruff config
└── requirements.txt            # HA, ruff, pre-commit, pyserial, pytest-homeassistant-custom-component
```

## Dev workflow

```bash
# In the devcontainer (PostCreateCommand=scripts/setup):
pre-commit install

# Lint
./scripts/lint                                      # ruff format + ruff check --fix
pre-commit run --all-files

# Tests (163 unit tests, no hardware required, ~10s)
pytest tests/

# Run HA against the integration (no real serial device, UI testing only)
./scripts/develop                                   # http://localhost:8123

# To exercise the integration with a REAL Bromic bridge, you need a serial
# tunnel from the host into the container (the container can't see /dev/ttyUSB*):
#
#   On the host:    ./scripts/tty-bridge-host.sh -d /dev/ttyUSB0
#   In container:   ./scripts/tty-bridge-container.sh
#   Then point the HA config flow at the resulting in-container PTY.

# Manual one-off commands (without HA)
python3 scripts/serial_send.py --id 5 --button 1     # Send button 1 to ID 5
python3 scripts/serial_test.py                       # Hard-coded round-trip
```

## Conventions and gotchas

- **`tests/` is a pure unit-test suite, no hardware in the loop.** All 163 tests run in CI in under 15 seconds and mock the serial layer. The smoke test (`test_smoke.py`) deliberately reaches `BromicHub.async_connect()` with a bogus port and asserts the integration enters `ConfigEntryState.SETUP_RETRY` (the documented failure path). Real-hardware validation against a Bromic bridge is still required before cutting a release; use `scripts/serial_test.py` / `serial_send.py` for that.
- **Tests are additive only by default.** If you're tempted to refactor production code to make a test easier, prefer adding a mock or fixture instead. The integration is deployed to real heater hardware; production behavior changes need separate, deliberate PRs.
- **Serial tunnel is the dev pattern, not a hack.** Devcontainers can't see host `/dev/tty*` devices, so `scripts/tty-bridge-{host,container}.sh` use `socat` to bridge the bridge. `socat.log` is a runtime artifact from those scripts.
- **`socat.log` is in the working tree but not in `.gitignore`.** It shouldn't be committed; if it shows up in `git status`, add `*.log` to `.gitignore` rather than checking it in. (Don't delete the existing `socat.log` without asking bharat, investigate first.)
- **Brightness mapping is discrete.** `const.py` maps HA's 0-255 brightness scale to 5 device levels (0/64/128/191/255 → 0/25/50/75/100%). Don't try to interpolate finer, the hardware doesn't accept it.
- **`scripts/customize.py` is a one-shot template-init tool** from the integration_blueprint scaffold. Don't run it again, it'd ask interactive questions and overwrite identifiers.
- **No retries beyond 3.** Hub retries each command up to 3 times with a 0.1s inter-frame delay, then surfaces a `BromicTimeoutError`. Don't add unbounded retry, outdoor heaters that misfire are a safety concern.
- **`country: ["US", "AU", "NZ", "CA", "GB"]`** in `hacs.json`. If you add region-specific behavior, update this.

## Existing docs

- `README.md` — feature overview, hardware requirements, install (HACS + manual), config flow walkthrough, entity types, services, troubleshooting.
- `CONTRIBUTING.md` — fork/PR flow; expects manual hardware testing.
- `docs/Bromic-Smart-Heat-Link-Installation-Guide.pdf` — vendor's hardware install guide (binary; reference only).

## Releases

Tags use **CalVer**: `v<YYYY>.<M>.<DD>` (e.g. `v2026.5.13`). Release titles use `Bromic v<YYYY>.<M>.<DD>` (e.g. `Bromic v2026.5.13`). Matches the fleet-wide HA-integration convention (triad-ams set the canonical shape). Historical `v0.1.x` tags stay as-is — the CalVer convention applies going forward only.

There is no automated release workflow in `.github/workflows/`. Cutting a release is manual:

```bash
# 1. Bump version in custom_components/bromic_smart_heat_link/manifest.json
# 2. Commit, push, get the bump merged
DATE=$(date -u +%Y.%-m.%d)                           # e.g. 2026.5.13
git tag "v${DATE}"
git push origin "v${DATE}"
gh release create "v${DATE}" --title "Bromic v${DATE}" --notes "..."   # body format below
```

Build the GitHub release body in three parts:

1. **Lead paragraph** (no header): 1–3 sentences of plain-English summary of what this release means for users.
2. **`## What's Changed`**: bullet list of non-dependabot merged PRs since the previous tag, one per line: `* <commit subject> by @<author> in <PR url>`. Skip dependabot PRs.
3. **`N dependabot updates:`** (rollup at the bottom): one line per dependency: `* <package>: <oldest version in window> → <newest version>`. Collapse all bumps for the same dep into one line.

End with `**Full Changelog**: <compare link>` (GitHub auto-generates if you let it; or pass `--generate-notes` to `gh release create`).

Reference example (sister project, different title format): https://github.com/bharat/homeassistant-lockly/releases/tag/v1.0.4

## What NOT to touch

- `socat.log`: investigate before deleting; it's the trailing artifact of dev sessions and not currently `.gitignore`d.
- `scripts/customize.py`: one-shot template init; running it again will ask interactive questions and overwrite identifiers.
- The 3-retry / 0.1s inter-frame timing in `hub.py`: see "no retries beyond 3" above (safety).
- Production code under `custom_components/bromic_smart_heat_link/` when the task is to add or fix tests; tests should adapt to production behavior, not the other way around.
