import asyncio
import os
from dotenv import load_dotenv

from bot.utils.database import Database

load_dotenv()


DEFAULT_SETTINGS = [
    ("guild_id", os.getenv("GUILD_ID", ""), "string", "Discord", "Discord server ID"),
    ("player_sync_role_id", os.getenv("PLAYER_SYNC_ROLE_ID", ""), "string", "Discord", "Role used to sync eligible players"),
    ("event_log_channel_id", os.getenv("EVENT_LOG_CHANNEL_ID", ""), "string", "Discord", "Channel used for RSVP audit messages"),
    ("allowed_role_ids", ",".join([os.getenv(f"ALLOWED_ROLE_ID_{i}", "") for i in range(1, 6) if os.getenv(f"ALLOWED_ROLE_ID_{i}", "")]), "csv", "Discord", "Comma-separated admin role IDs"),

    ("role_id_commander", os.getenv("ROLE_ID_COMMANDER", ""), "string", "Restricted Roles", "Role required to sign up as Commander"),
    ("role_id_officer", os.getenv("ROLE_ID_OFFICER", ""), "string", "Restricted Roles", "Role required to sign up as Officer"),
    ("role_id_tank_commander", os.getenv("ROLE_ID_TANK_COMMANDER", ""), "string", "Restricted Roles", "Role required to sign up as Tank Commander"),
    ("role_id_recon", os.getenv("ROLE_ID_RECON", ""), "string", "Restricted Roles", "Role required to sign up for Recon"),
    ("role_id_pathfinder", os.getenv("ROLE_ID_PATHFINDER", ""), "string", "Restricted Roles", "Role required to sign up for Pathfinders"),
    ("role_id_arty", os.getenv("ROLE_ID_ARTY", ""), "string", "Restricted Roles", "Role required to sign up for Artillery"),
    ("role_id_spa", os.getenv("ROLE_ID_SPA", ""), "string", "Restricted Roles", "Role required to sign up for SPA"),
    ("role_id_spa_commander", os.getenv("ROLE_ID_SPA_COMMANDER", ""), "string", "Restricted Roles", "Role required to sign up as SPA Commander"),
    ("role_id_attack", os.getenv("ROLE_ID_ATTACK", ""), "string", "Restricted Roles", "Attack role ID"),
    ("role_id_defence", os.getenv("ROLE_ID_DEFENCE", ""), "string", "Restricted Roles", "Defence role ID"),

    ("domain", os.getenv("DOMAIN", "gridironbot.co.uk"), "string", "Web", "Public web UI domain"),

    ("emoji_commander", "", "string", "Emoji", "Discord emoji for Commander role", True),
    ("emoji_infantry", "", "string", "Emoji", "Discord emoji for Infantry role", True),
    ("emoji_armour", "", "string", "Emoji", "Discord emoji for Armour role", True),
    ("emoji_recon", "", "string", "Emoji", "Discord emoji for Recon role", True),
    ("emoji_pathfinders", "", "string", "Emoji", "Discord emoji for Pathfinders role", True),
    ("emoji_artillery", "", "string", "Emoji", "Discord emoji for Artillery role", True),
    ("emoji_spa", "", "string", "Emoji", "Discord emoji for SPA role", True),
    ("emoji_anti_tank", "", "string", "Emoji", "Discord emoji for Anti-Tank subclass", True),
    ("emoji_assault", "", "string", "Emoji", "Discord emoji for Assault subclass", True),
    ("emoji_automatic_rifleman", "", "string", "Emoji", "Discord emoji for Automatic Rifleman subclass", True),
    ("emoji_engineer", "", "string", "Emoji", "Discord emoji for Engineer subclass", True),
    ("emoji_machine_gunner", "", "string", "Emoji", "Discord emoji for Machine Gunner subclass", True),
    ("emoji_medic", "", "string", "Emoji", "Discord emoji for Medic subclass", True),
    ("emoji_officer", "", "string", "Emoji", "Discord emoji for Officer subclass", True),
    ("emoji_rifleman", "", "string", "Emoji", "Discord emoji for Rifleman subclass", True),
    ("emoji_support", "", "string", "Emoji", "Discord emoji for Support subclass", True),
    ("emoji_tank_commander", "", "string", "Emoji", "Discord emoji for Tank Commander subclass", True),
    ("emoji_crewman", "", "string", "Emoji", "Discord emoji for Crewman subclass", True),
    ("emoji_spa_commander", "", "string", "Emoji", "Discord emoji for SPA Commander subclass", True),
    ("emoji_spa_crewman", "", "string", "Emoji", "Discord emoji for SPA Crewman subclass", True),
    ("emoji_spotter", "", "string", "Emoji", "Discord emoji for Spotter subclass", True),
    ("emoji_sniper", "", "string", "Emoji", "Discord emoji for Sniper subclass", True),
]


async def main():
    db = Database()
    await db.connect()

    for setting in DEFAULT_SETTINGS:
        key, value, value_type, category, description, *rest = setting
        editable = rest[0] if rest else True
        await db.upsert_system_setting(
            key=key,
            value=value,
            value_type=value_type,
            category=category,
            description=description,
            editable=editable,
        )
        print(f"Seeded setting: {key}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
