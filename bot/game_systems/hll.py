"""Hell Let Loose game definition.

This module is the single source of truth for HLL roles, subclasses,
squad/template options, class limits, role priority, and default emoji settings.
"""

GAME_ID = "hll"
DISPLAY_NAME = "Hell Let Loose"

INFANTRY_SUBCLASSES = [
    "Anti-Tank",
    "Assault",
    "Automatic Rifleman",
    "Engineer",
    "Machine Gunner",
    "Medic",
    "Officer",
    "Rifleman",
    "Support",
]

ROLES = ["Commander", "Infantry", "Armour", "SPA", "Recon", "Pathfinders", "Artillery"]

SUBCLASSES = {
    "Infantry": INFANTRY_SUBCLASSES,
    "Armour": ["Tank Commander", "Crewman"],
    "SPA": ["Artillery Observer", "Artillery Support", "Artillery Engineer"],
    "Recon": ["Spotter", "Sniper"],
    "Pathfinders": INFANTRY_SUBCLASSES,
    "Artillery": INFANTRY_SUBCLASSES,
}

# --- Game hierarchy -------------------------------------------------------
# HLL now follows the same Game -> Templates -> Squads -> Classes -> Players
# shape as HLLV. The older ROLES/SUBCLASSES exports remain for compatibility
# with the current Discord signup and admin UI flows.
CATEGORIES = {
    "Commander": {
        "display_name": "Commander",
        "classes": [],
        "squad_type": "Command",
        "default_squad_size": 1,
    },
    "Infantry": {
        "display_name": "Infantry",
        "classes": INFANTRY_SUBCLASSES,
        "squad_type": "Infantry",
        "default_squad_size": 6,
    },
    "Armour": {
        "display_name": "Armour",
        "classes": ["Tank Commander", "Crewman"],
        "squad_type": "Armour",
        "default_squad_size": 3,
    },
    "SPA": {
        "display_name": "SPA",
        "classes": ["Artillery Observer", "Artillery Support", "Artillery Engineer"],
        "squad_type": "SPA",
        "default_squad_size": 3,
    },
    "Recon": {
        "display_name": "Recon",
        "classes": ["Spotter", "Sniper"],
        "squad_type": "Recon",
        "default_squad_size": 2,
    },
    "Pathfinders": {
        "display_name": "Pathfinders",
        "classes": INFANTRY_SUBCLASSES,
        "squad_type": "Infantry",
        "default_squad_size": 6,
    },
    "Artillery": {
        "display_name": "Artillery",
        "classes": INFANTRY_SUBCLASSES,
        "squad_type": "Artillery",
        "default_squad_size": 2,
    },
}

TEMPLATE_MODEL = {
    "game": GAME_ID,
    "display_name": DISPLAY_NAME,
    "hierarchy": "Game -> Templates -> Squads -> Classes -> Players",
    "categories": CATEGORIES,
}

RESTRICTED_ROLES = [
    "Commander",
    "Recon",
    "Officer",
    "Tank Commander",
    "SPA",
    "Artillery Observer",
    "Pathfinders",
    "Artillery",
]

RSVP_POOLS = ["Commander", "Infantry", "Armour", "SPA", "Recon", "Pathfinders", "Artillery", "Unassigned"]
SQUAD_TYPES = ["Command", "Infantry", "Armour", "SPA", "Recon", "Artillery", "Reserves"]

SQUAD_SIZE_BY_TYPE = {
    "Command": 1,
    "Infantry": 6,
    "Armour": 3,
    "SPA": 3,
    "Recon": 2,
    "Artillery": 2,
    "Reserves": 99,
}

CLASS_LIMITS = {
    "Officer": 1,
    "Medic": 1,
    "Support": 1,
    "Anti-Tank": 1,
    "Machine Gunner": 1,
    "Automatic Rifleman": 1,
    "Assault": 1,
    "Engineer": 1,
    "Spotter": 1,
    "Sniper": 1,
    "Tank Commander": 1,
    "Commander": 1,
    "Artillery Observer": 1,
    "Artillery Support": 1,
    "Artillery Engineer": 1,
    "Rifleman": 99,
    "Crewman": 99,
}

ROLE_PRIORITY = [
    "Officer",
    "Support",
    "Medic",
    "Anti-Tank",
    "Machine Gunner",
    "Automatic Rifleman",
    "Engineer",
    "Assault",
    "Rifleman",
    "Tank Commander",
    "Crewman",
    "Artillery Observer",
    "Artillery Support",
    "Artillery Engineer",
    "Spotter",
    "Sniper",
]

SPA_ROLES_TO_FILL = ["Artillery Observer", "Artillery Support", "Artillery Engineer"]

DEFAULT_EMOJI_MAPPING = {
    "Commander": "⭐",
    "Infantry": "💂",
    "Armour": "🛡️",
    "Recon": "👁️",
    "Pathfinders": "🧭",
    "Artillery": "💣",
    "SPA": "🚚",
    "Anti-Tank": "🚀",
    "Assault": "💥",
    "Automatic Rifleman": "🔥",
    "Engineer": "🛠️",
    "Machine Gunner": "💥",
    "Medic": "➕",
    "Officer": "🫡",
    "Rifleman": "👤",
    "Support": "🔧",
    "Tank Commander": "🧑‍✈️",
    "Crewman": "👨‍🔧",
    "Artillery Observer": "🎯",
    "Artillery Support": "💥",
    "Artillery Engineer": "🛠️",
    "Spotter": "👀",
    "Sniper": "🎯",
    "Unassigned": "❔",
}

EMOJI_SETTING_KEYS = {
    "Commander": "emoji_commander",
    "Infantry": "emoji_infantry",
    "Armour": "emoji_armour",
    "Recon": "emoji_recon",
    "Pathfinders": "emoji_pathfinders",
    "Artillery": "emoji_artillery",
    "SPA": "emoji_spa",
    "Anti-Tank": "emoji_anti_tank",
    "Assault": "emoji_assault",
    "Automatic Rifleman": "emoji_automatic_rifleman",
    "Engineer": "emoji_engineer",
    "Machine Gunner": "emoji_machine_gunner",
    "Medic": "emoji_medic",
    "Officer": "emoji_officer",
    "Rifleman": "emoji_rifleman",
    "Support": "emoji_support",
    "Tank Commander": "emoji_tank_commander",
    "Crewman": "emoji_crewman",
    "Artillery Observer": "emoji_artillery_observer",
    "Artillery Support": "emoji_artillery_support",
    "Artillery Engineer": "emoji_artillery_engineer",
    "Spotter": "emoji_spotter",
    "Sniper": "emoji_sniper",
}


DEFAULT_TEMPLATES = [
    {
        "template_name": "HLL Standard 50v50",
        "definitions": [
            {"squad_name": "Command", "default_count": 1, "squad_type": "Command", "naming_convention": "none", "source_rsvp_pool": "Commander"},
            {"squad_name": "Infantry", "default_count": 6, "squad_type": "Infantry", "naming_convention": "numeric", "source_rsvp_pool": "Infantry"},
            {"squad_name": "Armour", "default_count": 2, "squad_type": "Armour", "naming_convention": "alpha", "source_rsvp_pool": "Armour"},
            {"squad_name": "SPA", "default_count": 1, "squad_type": "SPA", "naming_convention": "alpha", "source_rsvp_pool": "SPA"},
            {"squad_name": "Recon", "default_count": 2, "squad_type": "Recon", "naming_convention": "alpha", "source_rsvp_pool": "Recon"},
        ],
    },
]
