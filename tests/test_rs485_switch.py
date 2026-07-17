"""Regression tests for the manual RS485 Control Mode switch."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.omnibattery.switch import MarstekVenusSwitch


def _switch(*, mode: int) -> tuple[MarstekVenusSwitch, SimpleNamespace]:
    coordinator = SimpleNamespace(
        name="BAT1",
        data={"rs485_control_mode": mode},
        set_rs485_user_disabled=Mock(),
        async_reconnect_fresh=AsyncMock(return_value=True),
        set_rs485_control=AsyncMock(return_value=True),
        rs485_control_enabled=AsyncMock(return_value=True),
        async_request_refresh=AsyncMock(),
        write_control=AsyncMock(return_value=True),
    )
    switch = MarstekVenusSwitch.__new__(MarstekVenusSwitch)
    switch.coordinator = coordinator
    switch.definition = {"key": "rs485_control_mode"}
    switch._command_on = 0x55AA
    switch._command_off = 0x55BB
    return switch, coordinator


async def test_rs485_turn_on_from_off_reconnects_and_verifies_register():
    switch, coordinator = _switch(mode=0x55BB)

    await switch.async_turn_on()

    coordinator.set_rs485_user_disabled.assert_called_once_with(False)
    coordinator.async_reconnect_fresh.assert_awaited_once()
    coordinator.set_rs485_control.assert_not_awaited()
    coordinator.rs485_control_enabled.assert_awaited_once()
    coordinator.async_request_refresh.assert_awaited_once()
    coordinator.write_control.assert_not_awaited()


async def test_rs485_turn_on_when_already_on_does_not_reconnect():
    switch, coordinator = _switch(mode=0x55AA)

    await switch.async_turn_on()

    coordinator.async_reconnect_fresh.assert_not_awaited()
    coordinator.set_rs485_control.assert_awaited_once_with(True)
    coordinator.rs485_control_enabled.assert_awaited_once()


async def test_rs485_turn_on_fails_when_readback_is_not_enabled():
    switch, coordinator = _switch(mode=0x55BB)
    coordinator.rs485_control_enabled.return_value = False

    with pytest.raises(HomeAssistantError, match="could not be verified"):
        await switch.async_turn_on()

    coordinator.async_reconnect_fresh.assert_awaited_once()
    coordinator.async_request_refresh.assert_not_awaited()


async def test_rs485_turn_on_fails_when_reconnect_fails():
    switch, coordinator = _switch(mode=0x55BB)
    coordinator.async_reconnect_fresh.return_value = False

    with pytest.raises(HomeAssistantError, match="Unable to enable"):
        await switch.async_turn_on()

    coordinator.rs485_control_enabled.assert_not_awaited()


async def test_rs485_turn_off_writes_semantic_command_and_verifies_register():
    switch, coordinator = _switch(mode=0x55AA)
    coordinator.rs485_control_enabled.return_value = False

    await switch.async_turn_off()

    coordinator.set_rs485_user_disabled.assert_called_once_with(True)
    coordinator.set_rs485_control.assert_awaited_once_with(False)
    coordinator.rs485_control_enabled.assert_awaited_once()
    coordinator.async_request_refresh.assert_awaited_once()
    coordinator.write_control.assert_not_awaited()


async def test_rs485_turn_off_fails_when_readback_is_not_disabled():
    switch, coordinator = _switch(mode=0x55AA)

    with pytest.raises(HomeAssistantError, match="verified as disabled"):
        await switch.async_turn_off()

    coordinator.set_rs485_user_disabled.assert_called_once_with(True)
    coordinator.set_rs485_control.assert_awaited_once_with(False)
    coordinator.async_request_refresh.assert_not_awaited()
