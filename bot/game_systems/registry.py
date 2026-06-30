"""Registry for supported game systems."""

from types import ModuleType
from typing import Dict, List

from . import hll, hllv

DEFAULT_GAME_ID = "hll"

_GAME_SYSTEMS: Dict[str, ModuleType] = {
    hll.GAME_ID: hll,
    hllv.GAME_ID: hllv,
}


def get_game_system(game_id: str):
    module = GAME_SYSTEMS.get(game_id)
    if not module:
        return GAME_SYSTEMS["hll"].GAME_SYSTEM
    return module.GAME_SYSTEM


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
            "categories": getattr(game, "CATEGORIES", {}),
            "template_model": getattr(game, "TEMPLATE_MODEL", {}),
            "rsvp_pools": getattr(game, "RSVP_POOLS", []),
            "squad_types": getattr(game, "SQUAD_TYPES", []),
        }
        for game in _GAME_SYSTEMS.values()
    ]
