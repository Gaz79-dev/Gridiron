"""Registry for supported game systems."""

from types import ModuleType
from typing import Dict, List

from . import hll, hllv

DEFAULT_GAME_ID = "hll"

_GAME_SYSTEMS: Dict[str, ModuleType] = {
    hll.GAME_ID: hll,
    hllv.GAME_ID: hllv,
}


def get_game_system(game_id: str | None = None) -> ModuleType:
    """Return a game system definition module.

    Unknown or blank game ids safely fall back to Hell Let Loose for backward
    compatibility with existing events and templates.
    """
    return _GAME_SYSTEMS.get(game_id or DEFAULT_GAME_ID, hll)


def get_all_game_systems() -> List[ModuleType]:
    """Return all registered game system modules."""
    return list(_GAME_SYSTEMS.values())


def list_game_systems() -> List[dict]:
    """Return the supported game systems for future UI/template selectors."""
    return [
        {
            "game_id": game.GAME_ID,
            "display_name": game.DISPLAY_NAME,
            "roles": getattr(game, "ROLES", []),
            "subclasses": getattr(game, "SUBCLASSES", {}),
            "rsvp_pools": getattr(game, "RSVP_POOLS", []),
            "squad_types": getattr(game, "SQUAD_TYPES", []),
        }
        for game in _GAME_SYSTEMS.values()
    ]
