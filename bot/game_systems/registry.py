"""
Game System Registry

This module provides a central registry for all supported game systems.
Every game module must expose a GAME_SYSTEM dictionary.
"""

from bot.game_systems import hll, hllv

GAME_SYSTEMS = {
    "hll": hll,
    "hllv": hllv,
}


def get_game_system(game_id: str = "hll") -> dict:
    """
    Returns the GAME_SYSTEM definition for the requested game.

    Falls back to HLL if the requested game does not exist.
    """
    module = GAME_SYSTEMS.get(game_id)

    if module is None:
        module = GAME_SYSTEMS["hll"]

    return module.GAME_SYSTEM


def list_game_systems() -> list[dict]:
    """
    Returns a lightweight list of all registered game systems.
    Useful for populating dropdowns and admin UI.
    """
    systems = []

    for module in GAME_SYSTEMS.values():
        game = module.GAME_SYSTEM

        systems.append({
            "game_id": game["game_id"],
            "display_name": game["display_name"],
            "roles": game.get("roles", []),
            "subclasses": game.get("subclasses", {}),
            "categories": game.get("categories", {}),
            "template_model": game.get("template_model", {}),
            "rsvp_pools": game.get("rsvp_pools", []),
            "squad_types": game.get("squad_types", []),
        })

    return systems


def game_exists(game_id: str) -> bool:
    """
    Returns True if a game system is registered.
    """
    return game_id in GAME_SYSTEMS
