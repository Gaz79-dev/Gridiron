"""
Game System Registry

Central registry for all supported game systems.

This file intentionally supports the current game module format where each game
exports module-level constants such as:

GAME_ID
DISPLAY_NAME
ROLES
SUBCLASSES
CATEGORIES
DEFAULT_TEMPLATES

It also returns a wrapper that supports both styles:

game["display_name"]
game.get("roles")
game.ROLES

That keeps the existing bot code working while also supporting the newer
dictionary-style tests and UI work.
"""

from types import ModuleType
from typing import Any, Dict, List

from . import hll, hllv

DEFAULT_GAME_ID = "hll"

_GAME_SYSTEMS: Dict[str, ModuleType] = {
    hll.GAME_ID: hll,
    hllv.GAME_ID: hllv,
}


class GameSystem:
    """
    Compatibility wrapper around a game module.

    Allows both:
        game["display_name"]
        game.get("display_name")
        game.DISPLAY_NAME
        game.ROLES
    """

    def __init__(self, module: ModuleType):
        self._module = module
        self._data = _module_to_dict(module)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._module, name)

    def as_dict(self) -> dict:
        return dict(self._data)


def _module_to_dict(module: ModuleType) -> dict:
    """
    Convert a game module into the standard dictionary shape used by tests,
    APIs, and future admin UI work.
    """
    return {
        "game_id": getattr(module, "GAME_ID", DEFAULT_GAME_ID),
        "display_name": getattr(module, "DISPLAY_NAME", "Unknown Game"),
        "roles": getattr(module, "ROLES", []),
        "subclasses": getattr(module, "SUBCLASSES", {}),
        "categories": getattr(module, "CATEGORIES", {}),
        "template_model": getattr(module, "TEMPLATE_MODEL", {}),
        "rsvp_pools": getattr(module, "RSVP_POOLS", []),
        "squad_types": getattr(module, "SQUAD_TYPES", []),
        "squad_size_by_type": getattr(module, "SQUAD_SIZE_BY_TYPE", {}),
        "class_limits": getattr(module, "CLASS_LIMITS", {}),
        "role_priority": getattr(module, "ROLE_PRIORITY", []),
        "restricted_roles": getattr(module, "RESTRICTED_ROLES", []),
        "default_emoji_mapping": getattr(module, "DEFAULT_EMOJI_MAPPING", {}),
        "emoji_setting_keys": getattr(module, "EMOJI_SETTING_KEYS", {}),
        "default_templates": getattr(module, "DEFAULT_TEMPLATES", []),
    }


def get_game_system(game_id: str | None = None) -> GameSystem:
    """
    Return a game system wrapper.

    Unknown or blank game IDs safely fall back to Hell Let Loose for backward
    compatibility with existing events and templates.
    """
    module = _GAME_SYSTEMS.get(game_id or DEFAULT_GAME_ID, hll)
    return GameSystem(module)


def get_all_game_systems() -> List[GameSystem]:
    """
    Return all registered game systems as compatibility wrappers.
    """
    return [GameSystem(module) for module in _GAME_SYSTEMS.values()]


def list_game_systems() -> List[dict]:
    """
    Return all supported game systems as plain dictionaries.

    Useful for tests, APIs, dropdowns, and future admin UI selectors.
    """
    return [
        _module_to_dict(module)
        for module in _GAME_SYSTEMS.values()
    ]


def game_exists(game_id: str) -> bool:
    """
    Return True if a game system is registered.
    """
    return game_id in _GAME_SYSTEMS
