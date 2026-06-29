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
    ("role_id_attack", os.getenv("ROLE_ID_ATTACK", ""), "string", "Restricted Roles", "Attack role ID"),
    ("role_id_defence", os.getenv("ROLE_ID_DEFENCE", ""), "string", "Restricted Roles", "Defence role ID"),

    ("domain", os.getenv("DOMAIN", "gridironbot.co.uk"), "string", "Web", "Public web UI domain"),
]


async def main():
    db = Database()
    await db.connect()

    for key, value, value_type, category, description in DEFAULT_SETTINGS:
        await db.upsert_system_setting(
            key=key,
            value=value,
            value_type=value_type,
            category=category,
            description=description,
            editable=True,
        )
        print(f"Seeded setting: {key}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
