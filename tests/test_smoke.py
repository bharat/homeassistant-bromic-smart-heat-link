"""
Smoke test for the Bromic Smart Heat Link integration.

Verifies that the integration loads under the currently-pinned Home Assistant
release and fails in the documented, predictable way (`ConfigEntryNotReady`
→ entry state `SETUP_RETRY`) when no real Bromic Smart Heat Link bridge is
reachable. CI has no serial hardware, so this is the natural failure path.

This is a **baseline** test for the fleet's "auto-merge HA-stack major bumps
only if smoke test passes" policy (see fleet memory
`feedback_renovate_pr_handling_policy.md`). When HA core is upgraded, this
test passing means the integration still:

1. Imports cleanly under the new HA's Python.
2. Lets HA construct a config entry with our domain and platform list.
3. Successfully enters `async_setup_entry`.
4. Reaches `BromicHub.async_connect()`.
5. Translates the connect failure into `ConfigEntryNotReady`, leaving the
   entry in `ConfigEntryState.SETUP_RETRY`.

If any of those steps regresses under a new HA, the assertion below fails
with a different state name and surfaces the regression before merge.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bromic_smart_heat_link.const import (
    CONF_SERIAL_PORT,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_setup_fails_predictably_without_hardware(
    hass: HomeAssistant,
    tmp_path,
) -> None:
    """
    Set up the integration with a bogus serial port; expect SETUP_RETRY.

    The integration's `async_setup_entry` wraps any `BromicHub.async_connect()`
    failure in `ConfigEntryNotReady`, which HA renders as
    `ConfigEntryState.SETUP_RETRY`. Pointing at a non-existent device path
    under pytest's per-test tmp_path is the simplest way to provoke that
    failure in CI without mocking.
    """
    bogus_port = str(tmp_path / "bromic-nonexistent-port")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SERIAL_PORT: bogus_port},
        title="Bromic Smoke Test",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.SETUP_RETRY, (
        f"Expected entry to be in SETUP_RETRY after a failed serial connect, "
        f"but state is {entry.state.name}. This indicates the integration is "
        f"no longer translating BromicHub.async_connect() failures into "
        f"ConfigEntryNotReady, or it crashed before reaching that path."
    )
