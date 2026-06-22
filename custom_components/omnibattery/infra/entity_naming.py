"""Helpers for stable, language-independent entity naming.

Home Assistant derives an entity's ``entity_id`` from its *translated* display
name, so a non-English install produces localized object ids (e.g.
``sensor.marstek_venus_1_potencia_ac``). That makes cross-language support
painful. Building the id from the English ``key`` keeps entity_ids consistent
regardless of the UI language, while the friendly (display) name stays
localized via ``translation_key``.

This only affects *newly* registered entities: the entity registry matches on
``unique_id`` and preserves the stored entity_id for entities it already knows,
so existing installs keep their current (possibly localized) ids untouched.
"""
from __future__ import annotations

from homeassistant.util import slugify


def english_entity_id(domain: str, device_name: str, key: str) -> str:
    """Return an English ``entity_id`` slug, independent of the UI language.

    ``device_name`` is the device's name (used as the entity_id prefix, matching
    HA's default ``has_entity_name`` behavior) and ``key`` is the English
    translation key.
    """
    return f"{domain}.{slugify(f'{device_name} {key}')}"


# System (aggregate) entities keep a stable, brand-legacy ``unique_id`` prefix so
# the registry identity — and the long-term statistics/history tied to it —
# survive the Omnibattery rebrand untouched. Never change this; the v9 heal
# migration and existing installs depend on it.
SYSTEM_UNIQUE_ID_PREFIX = "marstek_venus_system_"

# The *suggested* object id, however, uses the Omnibattery prefix. Existing
# installs keep their stored ``sensor.marstek_venus_system_*`` id until the user
# opts in via HA's built-in "Recreate entity IDs" (which regenerates from the
# suggested object id); fresh installs are born ``omnibattery_*``.
#
# The prefix is just ``omnibattery_`` (not ``omnibattery_system_``): several keys
# already start with ``system_`` (e.g. ``system_soc``), so an ``..._system_``
# prefix would double it into ``omnibattery_system_system_soc``. Keys carry their
# own grouping; this yields ``omnibattery_system_soc`` and ``omnibattery_home_consumption``.
SYSTEM_OBJECT_ID_PREFIX = "omnibattery_"


def system_entity_id(domain: str, key: str) -> str:
    """Return the suggested ``entity_id`` for a system-level entity.

    ``key`` is the English object-id suffix (which may differ from the unique_id
    suffix, e.g. ``net_balance`` vs. unique ``balance_neto``). The unique_id keeps
    :data:`SYSTEM_UNIQUE_ID_PREFIX`; only the suggested entity_id is rebranded.
    """
    return f"{domain}.{SYSTEM_OBJECT_ID_PREFIX}{key}"
