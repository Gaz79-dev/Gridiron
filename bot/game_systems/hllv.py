"""Hell Let Loose: Vietnam game definition.

This module is the single source of truth for HLLV roles, subclasses,
squad/template options, class limits, role priority, and default templates.
"""

GAME_ID = "hllv"
DISPLAY_NAME = "Hell Let Loose: Vietnam"

INFANTRY_SUBCLASSES = [
    "Assault",
    "Automatic Rifleman",
    "Engineer",
    "Heavy Machine Gunner",
    "Medic",
    "Rifleman",
    "Squad Leader",
]

ROLES = ["Commander", "Infantry", "Armour", "Helicopter", "Mortar", "Recon"]

SUBCLASSES = {
    "Infantry": INFANTRY_SUBCLASSES,
    "Armour": ["Tank Commander", "Crewman"],
    "Helicopter": [
        "Helicopter Pilot",
        "Helicopter Flight Engineer",
        "Helicopter Logistics Officer",
        "Helicopter Medic",
    ],
    "Mortar": ["Mortar Observer", "Mortar Support", "Mortar Gunner"],
    "Recon": ["Spotter", "Sniper"],
}

RESTRICTED_ROLES = [
    "Commander",
    "Recon",
    "Spotter",
    "Sniper",
    "Squad Leader",
    "Tank Commander",
    "Helicopter",
    "Helicopter Pilot",
    "Helicopter Logistics Officer",
    "Mortar",
    "Mortar Observer",
]

RSVP_POOLS = ["Commander", "Infantry", "Armour", "Helicopter", "Mortar", "Recon", "Unassigned"]
SQUAD_TYPES = ["Command", "Infantry", "Armour", "Helicopter", "Mortar", "Recon", "Reserves"]

SQUAD_SIZE_BY_TYPE = {
    "Command": 1,
    "Infantry": 6,
    "Armour": 3,
    "Helicopter": 4,
    "Mortar": 3,
    "Recon": 2,
    "Reserves": 99,
}

CLASS_LIMITS = {
    "Commander": 1,
    "Squad Leader": 1,
    "Medic": 1,
    "Engineer": 1,
    "Heavy Machine Gunner": 1,
    "Automatic Rifleman": 1,
    "Assault": 1,
    "Rifleman": 99,
    "Tank Commander": 1,
    "Crewman": 99,
    "Helicopter Pilot": 1,
    "Helicopter Flight Engineer": 1,
    "Helicopter Logistics Officer": 1,
    "Helicopter Medic": 1,
    "Mortar Observer": 1,
    "Mortar Support": 1,
    "Mortar Gunner": 1,
    "Spotter": 1,
    "Sniper": 1,
}

ROLE_PRIORITY = [
    "Squad Leader",
    "Engineer",
    "Medic",
    "Heavy Machine Gunner",
    "Automatic Rifleman",
    "Assault",
    "Rifleman",
    "Tank Commander",
    "Crewman",
    "Helicopter Pilot",
    "Helicopter Logistics Officer",
    "Helicopter Flight Engineer",
    "Helicopter Medic",
    "Mortar Observer",
    "Mortar Support",
    "Mortar Gunner",
    "Spotter",
    "Sniper",
]

SPECIALIST_ROLES_TO_FILL = {
    "Armour": ["Tank Commander", "Crewman"],
    "Helicopter": [
        "Helicopter Pilot",
        "Helicopter Logistics Officer",
        "Helicopter Flight Engineer",
        "Helicopter Medic",
    ],
    "Mortar": ["Mortar Observer", "Mortar Support", "Mortar Gunner"],
    "Recon": ["Spotter", "Sniper"],
}

DEFAULT_EMOJI_MAPPING = {
    "Commander": "⭐",
    "Infantry": "💂",
    "Armour": "🛡️",
    "Helicopter": "🚁",
    "Mortar": "💣",
    "Recon": "👁️",
    "Assault": "💥",
    "Automatic Rifleman": "🔥",
    "Engineer": "🛠️",
    "Heavy Machine Gunner": "💥",
    "Medic": "➕",
    "Rifleman": "👤",
    "Squad Leader": "🫡",
    "Tank Commander": "🧑‍✈️",
    "Crewman": "👨‍🔧",
    "Helicopter Pilot": "🚁",
    "Helicopter Flight Engineer": "🔧",
    "Helicopter Logistics Officer": "📦",
    "Helicopter Medic": "➕",
    "Mortar Observer": "🎯",
    "Mortar Support": "📦",
    "Mortar Gunner": "💣",
    "Spotter": "👀",
    "Sniper": "🎯",
    "Unassigned": "❔",
}

EMOJI_SETTING_KEYS = {
    "Commander": "emoji_commander",
    "Infantry": "emoji_infantry",
    "Armour": "emoji_armour",
    "Helicopter": "emoji_helicopter",
    "Mortar": "emoji_mortar",
    "Recon": "emoji_recon",
    "Assault": "emoji_assault",
    "Automatic Rifleman": "emoji_automatic_rifleman",
    "Engineer": "emoji_engineer",
    "Heavy Machine Gunner": "emoji_heavy_machine_gunner",
    "Medic": "emoji_medic",
    "Rifleman": "emoji_rifleman",
    "Squad Leader": "emoji_squad_leader",
    "Tank Commander": "emoji_tank_commander",
    "Crewman": "emoji_crewman",
    "Helicopter Pilot": "emoji_helicopter_pilot",
    "Helicopter Flight Engineer": "emoji_helicopter_flight_engineer",
    "Helicopter Logistics Officer": "emoji_helicopter_logistics_officer",
    "Helicopter Medic": "emoji_helicopter_medic",
    "Mortar Observer": "emoji_mortar_observer",
    "Mortar Support": "emoji_mortar_support",
    "Mortar Gunner": "emoji_mortar_gunner",
    "Spotter": "emoji_spotter",
    "Sniper": "emoji_sniper",
}

DEFAULT_TEMPLATES = [
    {
        "template_name": "HLLV Standard 50v50",
        "definitions": [
            {"squad_name": "Command", "default_count": 1, "squad_type": "Command", "naming_convention": "none", "source_rsvp_pool": "Commander"},
            {"squad_name": "Infantry", "default_count": 5, "squad_type": "Infantry", "naming_convention": "numeric", "source_rsvp_pool": "Infantry"},
            {"squad_name": "Armour", "default_count": 2, "squad_type": "Armour", "naming_convention": "alpha", "source_rsvp_pool": "Armour"},
            {"squad_name": "Helicopter", "default_count": 2, "squad_type": "Helicopter", "naming_convention": "alpha", "source_rsvp_pool": "Helicopter"},
            {"squad_name": "Mortar", "default_count": 1, "squad_type": "Mortar", "naming_convention": "alpha", "source_rsvp_pool": "Mortar"},
            {"squad_name": "Recon", "default_count": 2, "squad_type": "Recon", "naming_convention": "alpha", "source_rsvp_pool": "Recon"},
        ],
    },
    {
        "template_name": "HLLV Infantry Focus",
        "definitions": [
            {"squad_name": "Command", "default_count": 1, "squad_type": "Command", "naming_convention": "none", "source_rsvp_pool": "Commander"},
            {"squad_name": "Infantry", "default_count": 7, "squad_type": "Infantry", "naming_convention": "numeric", "source_rsvp_pool": "Infantry"},
            {"squad_name": "Armour", "default_count": 1, "squad_type": "Armour", "naming_convention": "alpha", "source_rsvp_pool": "Armour"},
            {"squad_name": "Helicopter", "default_count": 1, "squad_type": "Helicopter", "naming_convention": "alpha", "source_rsvp_pool": "Helicopter"},
            {"squad_name": "Mortar", "default_count": 1, "squad_type": "Mortar", "naming_convention": "alpha", "source_rsvp_pool": "Mortar"},
            {"squad_name": "Recon", "default_count": 2, "squad_type": "Recon", "naming_convention": "alpha", "source_rsvp_pool": "Recon"},
        ],
    },
]
