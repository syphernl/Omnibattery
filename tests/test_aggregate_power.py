"""System charge/discharge power aggregation across mixed-brand coordinators.

Regression: Zendure coordinators only synthesise ``battery_power`` (+charge /
−discharge); they never expose Marstek's ``ac_power`` register. The aggregate
sensors summed ``ac_power`` only, so Zendure power was missing from System
Charge Power / System Discharge Power.
"""
from custom_components.marstek_venus_energy_manager.sensors.aggregate_sensors import (
    MarstekVenusAggregateSensor,
)
from tests.conftest import FakeCoordinator


def _sensor(coordinators, key):
    """Build an aggregate sensor without running __init__ (no listener wiring)."""
    sensor = MarstekVenusAggregateSensor.__new__(MarstekVenusAggregateSensor)
    sensor.coordinators = coordinators
    sensor.definition = {"key": key, "precision": 0}
    return sensor


def test_ac_convention_power_prefers_ac_power():
    # Marstek: ac_power used as-is (charge negative / discharge positive).
    assert MarstekVenusAggregateSensor._ac_convention_power({"ac_power": -300}) == -300
    assert MarstekVenusAggregateSensor._ac_convention_power({"ac_power": 450}) == 450


def test_ac_convention_power_falls_back_to_negated_battery_power():
    # Zendure: only battery_power (+charge / −discharge) → negate to ac convention.
    assert MarstekVenusAggregateSensor._ac_convention_power({"battery_power": 300}) == -300
    assert MarstekVenusAggregateSensor._ac_convention_power({"battery_power": -450}) == 450


def test_ac_convention_power_ac_power_wins_over_battery_power():
    data = {"ac_power": -300, "battery_power": 999}
    assert MarstekVenusAggregateSensor._ac_convention_power(data) == -300


def test_ac_convention_power_none_when_no_power_keys():
    assert MarstekVenusAggregateSensor._ac_convention_power({"battery_soc": 50}) is None


def test_charge_power_sums_marstek_and_zendure():
    marstek = FakeCoordinator(data={"ac_power": -200})       # charging 200 W
    zendure = FakeCoordinator(data={"battery_power": 300})   # charging 300 W
    sensor = _sensor([marstek, zendure], "system_charge_power")
    assert sensor._calculate_total_charge_power() == 500


def test_discharge_power_sums_marstek_and_zendure():
    marstek = FakeCoordinator(data={"ac_power": 150})        # discharging 150 W
    zendure = FakeCoordinator(data={"battery_power": -450})  # discharging 450 W
    sensor = _sensor([marstek, zendure], "system_discharge_power")
    assert sensor._calculate_total_discharge_power() == 600


def test_charge_power_excludes_discharging_zendure():
    zendure = FakeCoordinator(data={"battery_power": -450})  # discharging
    sensor = _sensor([zendure], "system_charge_power")
    assert sensor._calculate_total_charge_power() == 0


def test_unavailable_zendure_not_counted():
    zendure = FakeCoordinator(data={"battery_power": 300}, is_available=False)
    sensor = _sensor([zendure], "system_charge_power")
    assert sensor._calculate_total_charge_power() == 0


class _FakeState:
    def __init__(self, value, unit="W"):
        self.state = str(value)
        self.attributes = {"unit_of_measurement": unit}


class _FakeHass:
    def __init__(self, states):
        self.states = type("S", (), {"get": staticmethod(states.get)})()


class _FakeEntry:
    def __init__(self, data):
        self.data = data


def _home_sensor(coordinators, grid, solar):
    sensor = _sensor(coordinators, "home_consumption")
    sensor.hass = _FakeHass({"sensor.grid": _FakeState(grid), "sensor.solar": _FakeState(solar)})
    sensor.entry = _FakeEntry({
        "consumption_sensor": "sensor.grid",
        "solar_production_sensor": "sensor.solar",
    })
    return sensor


def test_home_consumption_includes_zendure_battery_power():
    # Regression: a registerless Zendure exposes only battery_power. Home
    # Consumption summed raw ac_power, dropping the Zendure's discharge — home
    # read low and the dashboard Home node collapsed toward 0 once an excluded
    # device was subtracted. grid 236 + marstek 0 + zendure 614 + solar 2249.
    marstek = FakeCoordinator(data={"ac_power": 0})
    zendure = FakeCoordinator(data={"battery_power": -614})  # discharging 614 W
    sensor = _home_sensor([marstek, zendure], grid=236, solar=2249)
    assert sensor._calculate_home_consumption() == 3099


def test_home_consumption_charging_zendure_reduces_home():
    # Charging Zendure (battery_power +400) draws from the bus → subtracts.
    zendure = FakeCoordinator(data={"battery_power": 400})
    sensor = _home_sensor([zendure], grid=1000, solar=0)
    assert sensor._calculate_home_consumption() == 600
