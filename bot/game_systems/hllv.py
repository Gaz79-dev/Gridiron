"""Hell Let Loose: Vietnam game definition.

This module is the single source of truth for HLLV roles, classes,
squad/template options, class limits, role priority, and default templates.

The hierarchy is intentionally explicit:

Game -> Templates -> Squads -> Classes -> Players

Templates define the squads that exist for an event. Squads draw players from a
role/category RSVP pool. Classes define what a player can actually sign up as
inside that pool.
"""

GAME_ID = "hllv"
DISPLAY_NAME = "Hell Let Loose: Vietnam"

# --- Game hierarchy -------------------------------------------------------
# Keep this as the canonical structure for HLLV. The older ROLES/SUBCLASSES
# exports below are derived-compatible names used by the current signup and UI
# flows, so this can be introduced without breaking existing code.
CATEGORIES = {
    "Commander": {
        "display_name": "Commander",
        "classes": [],
        "squad_type": "Command",
        "default_squad_size": 1,
    },
    "Infantry": {
        "display_name": "Infantry",
        "classes": [
            "Squad Leader (Officer)",
            "Rifleman",
            "Grenadier",
            "Engineer",
            "Medic",
            "Specialist",
            "Machine Gunner",
        ],
        "squad_type": "Infantry",
        "default_squad_size": 6,
    },
    "Armour": {
        "display_name": "Armour",
        "classes": [
            "Commander (Tank)",
            "Crewman",
        ],
        "squad_type": "Armour",
        "default_squad_size": 3,
    },
    "Recon": {
        "display_name": "Recon",
        "classes": [
            "Spotter",
            "Sniper",
        ],
        "squad_type": "Recon",
        "default_squad_size": 2,
    },
    "Helicopter Unit": {
        "display_name": "Helicopter Unit",
        "classes": [
            "Pilot",
            "Helicopter Gunner",
            "Squad Leader (Helicopter)",
        ],
        "squad_type": "Helicopter Unit",
        "default_squad_size": 3,
    },
    "Mortar Squads": {
        "display_name": "Mortar Squads",
        "classes": [
            "Squad Leader (Mortar)",
            "Mortarman",
            "Spotter",
        ],
        "squad_type": "Mortar Squads",
        "default_squad_size": 3,
    },
}

ROLES = list(CATEGORIES.keys())
SUBCLASSES = {
    category_name: category["classes"]
    for category_name, category in CATEGORIES.items()
    if category["classes"]
}

RESTRICTED_ROLES = [
    "Commander",
    "Squad Leader (Officer)",
    "Commander (Tank)",
    "Recon",
    "Spotter",
    "Sniper",
    "Helicopter Unit",
    "Pilot",
    "Squad Leader (Helicopter)",
    "Mortar Squads",
    "Squad Leader (Mortar)",
]

RSVP_POOLS = [*ROLES, "Unassigned"]
SQUAD_TYPES = [
    "Command",
    "Infantry",
    "Armour",
    "Recon",
    "Helicopter Unit",
    "Mortar Squads",
    "Reserves",
]

SQUAD_SIZE_BY_TYPE = {
    "Command": 1,
    "Infantry": 6,
    "Armour": 3,
    "Recon": 2,
    "Helicopter Unit": 3,
    "Mortar Squads": 3,
    "Reserves": 99,
}

CLASS_LIMITS = {
    "Commander": 1,
    "Squad Leader (Officer)": 1,
    "Rifleman": 99,
    "Grenadier": 1,
    "Engineer": 1,
    "Medic": 1,
    "Specialist": 1,
    "Machine Gunner": 1,
    "Commander (Tank)": 1,
    "Crewman": 99,
    "Spotter": 1,
    "Sniper": 1,
    "Pilot": 1,
    "Helicopter Gunner": 1,
    "Squad Leader (Helicopter)": 1,
    "Squad Leader (Mortar)": 1,
    "Mortarman": 1,
}

ROLE_PRIORITY = [
    "Squad Leader (Officer)",
    "Medic",
    "Engineer",
    "Specialist",
    "Machine Gunner",
    "Grenadier",
    "Rifleman",
    "Commander (Tank)",
    "Crewman",
    "Spotter",
    "Sniper",
    "Pilot",
    "Squad Leader (Helicopter)",
    "Helicopter Gunner",
    "Squad Leader (Mortar)",
    "Mortarman",
]

SPECIALIST_ROLES_TO_FILL = {
    "Command": ["Commander"],
    "Armour": ["Commander (Tank)", "Crewman"],
    "Recon": ["Spotter", "Sniper"],
    "Helicopter Unit": ["Pilot", "Squad Leader (Helicopter)", "Helicopter Gunner"],
    "Mortar Squads": ["Squad Leader (Mortar)", "Mortarman", "Spotter"],
}

# Template metadata that the UI/API can expose while the current DB schema still
# stores squad definitions in the existing squad_template_definitions table.
TEMPLATE_MODEL = {
    "game": GAME_ID,
    "display_name": DISPLAY_NAME,
    "hierarchy": "Game -> Templates -> Squads -> Classes -> Players",
    "categories": CATEGORIES,
}

DEFAULT_EMOJI_MAPPING = {
    "Commander": "⭐",
    "Infantry": "💂",
    "Armour": "🛡️",
    "Recon": "👁️",
    "Helicopter Unit": "🚁",
    "Mortar Squads": "💣",
    "Squad Leader (Officer)": "🫡",
    "Rifleman": "👤",
    "Grenadier": "💥",
    "Engineer": "🛠️",
    "Medic": "➕",
    "Specialist": "🔧",
    "Machine Gunner": "🔥",
    "Commander (Tank)": "🧑‍✈️",
    "Crewman": "👨‍🔧",
    "Spotter": "👀",
    "Sniper": "🎯",
    "Pilot": "🚁",
    "Helicopter Gunner": "🔥",
    "Squad Leader (Helicopter)": "🫡",
    "Squad Leader (Mortar)": "🫡",
    "Mortarman": "💣",
    "Unassigned": "❔",
}

EMOJI_SETTING_KEYS = {
    "Commander": "emoji_commander",
    "Infantry": "emoji_infantry",
    "Armour": "emoji_armour",
    "Recon": "emoji_recon",
    "Helicopter Unit": "emoji_helicopter_unit",
    "Mortar Squads": "emoji_mortar_squads",
    "Squad Leader (Officer)": "emoji_squad_leader_officer",
    "Rifleman": "emoji_rifleman",
    "Grenadier": "emoji_grenadier",
    "Engineer": "emoji_engineer",
    "Medic": "emoji_medic",
    "Specialist": "emoji_specialist",
    "Machine Gunner": "emoji_machine_gunner",
    "Commander (Tank)": "emoji_commander_tank",
    "Crewman": "emoji_crewman",
    "Spotter": "emoji_spotter",
    "Sniper": "emoji_sniper",
    "Pilot": "emoji_pilot",
    "Helicopter Gunner": "emoji_helicopter_gunner",
    "Squad Leader (Helicopter)": "emoji_squad_leader_helicopter",
    "Squad Leader (Mortar)": "emoji_squad_leader_mortar",
    "Mortarman": "emoji_mortarman",
}

DEFAULT_TEMPLATES = [
    {
        "template_name": "HLLV Standard 50v50",
        "definitions": [
            {"squad_name": "Command", "default_count": 1, "squad_type": "Command", "naming_convention": "none", "source_rsvp_pool": "Commander"},
            {"squad_name": "Infantry", "default_count": 5, "squad_type": "Infantry", "naming_convention": "numeric", "source_rsvp_pool": "Infantry"},
            {"squad_name": "Armour", "default_count": 2, "squad_type": "Armour", "naming_convention": "alpha", "source_rsvp_pool": "Armour"},
            {"squad_name": "Recon", "default_count": 2, "squad_type": "Recon", "naming_convention": "alpha", "source_rsvp_pool": "Recon"},
            {"squad_name": "Helicopter", "default_count": 2, "squad_type": "Helicopter Unit", "naming_convention": "alpha", "source_rsvp_pool": "Helicopter Unit"},
            {"squad_name": "Mortar", "default_count": 1, "squad_type": "Mortar Squads", "naming_convention": "alpha", "source_rsvp_pool": "Mortar Squads"},
        ],
    },
    {
        "template_name": "HLLV Infantry Focus",
        "definitions": [
            {"squad_name": "Command", "default_count": 1, "squad_type": "Command", "naming_convention": "none", "source_rsvp_pool": "Commander"},
            {"squad_name": "Infantry", "default_count": 6, "squad_type": "Infantry", "naming_convention": "numeric", "source_rsvp_pool": "Infantry"},
            {"squad_name": "Armour", "default_count": 1, "squad_type": "Armour", "naming_convention": "alpha", "source_rsvp_pool": "Armour"},
            {"squad_name": "Recon", "default_count": 2, "squad_type": "Recon", "naming_convention": "alpha", "source_rsvp_pool": "Recon"},
            {"squad_name": "Helicopter", "default_count": 1, "squad_type": "Helicopter Unit", "naming_convention": "alpha", "source_rsvp_pool": "Helicopter Unit"},
            {"squad_name": "Mortar", "default_count": 1, "squad_type": "Mortar Squads", "naming_convention": "alpha", "source_rsvp_pool": "Mortar Squads"},
        ],
    },
]
