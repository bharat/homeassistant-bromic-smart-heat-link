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
├── .pre-commit-config.yaml     # ruff + EOF/whitespace + check-yaml
├── .ruff.toml                  # Per-project ruff config
└── requirements.txt            # HA, ruff, pre-commit (note: requires `serial` alias of pyserial)
```

## Dev workflow

```bash
# In the devcontainer (PostCreateCommand=scripts/setup):
pre-commit install

# Lint
./scripts/lint                                      # ruff format + ruff check --fix
pre-commit run --all-files

# Run HA against the integration (no real serial device — UI testing only)
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

- **No `tests/` directory.** This is intentional, not an oversight: there is no fake-device simulator and no unit-test harness. Validation is **manual against real hardware** (or via `scripts/serial_test.py` / `serial_send.py` against a real bridge). If you add Python logic that's testable in isolation (e.g. protocol encode/decode), feel free to start a `tests/` directory and a pytest harness — just don't claim you've "tested" anything you haven't actually run on a real bridge.
- **Serial tunnel is the dev pattern, not a hack.** Devcontainers can't see host `/dev/tty*` devices, so `scripts/tty-bridge-{host,container}.sh` use `socat` to bridge the bridge. `socat.log` is a runtime artifact from those scripts.
- **`socat.log` is in the working tree but not in `.gitignore`.** It shouldn't be committed; if it shows up in `git status`, add `*.log` to `.gitignore` rather than checking it in. (Don't delete the existing `socat.log` without asking bharat — investigate first.)
- **Brightness mapping is discrete.** `const.py` maps HA's 0–255 brightness scale to 5 device levels (0/64/128/191/255 → 0/25/50/75/100%). Don't try to interpolate finer — the hardware doesn't accept it.
- **`requirements.txt` lists `serial==0.0.97`** — that's the *deprecated alias* package on PyPI, not pyserial. The integration's `manifest.json` correctly requires `pyserial>=3.5`. Don't "fix" the requirements.txt entry without checking whether it's compensating for something in the toolchain.
- **`scripts/customize.py` is a one-shot template-init tool** from the integration_blueprint scaffold. Don't run it again — it'd ask interactive questions and overwrite identifiers.
- **No retries beyond 3.** Hub retries each command up to 3 times with a 0.1s inter-frame delay, then surfaces a `BromicTimeoutError`. Don't add unbounded retry — outdoor heaters that misfire are a safety concern.
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

- `socat.log` — investigate before deleting; it's the trailing artifact of dev sessions and not currently `.gitignore`d.
- `scripts/customize.py` — one-shot template init; running it again will ask interactive questions and overwrite identifiers.
- The 3-retry / 0.1s inter-frame timing in `hub.py` — see "no retries beyond 3" above (safety).
- `requirements.txt`'s `serial==0.0.97` — likely intentional; investigate before "fixing."
