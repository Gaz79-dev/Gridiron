import os
from typing import Set


async def get_allowed_role_ids(db=None) -> Set[int]:
    raw_value = None

    if db:
        try:
            raw_value = await db.get_system_setting_value("allowed_role_ids")
        except Exception as exc:
            print(f"[permissions] Could not read allowed_role_ids from system_settings: {exc}")

    if not raw_value:
        values = []
        for i in range(1, 6):
            value = os.getenv(f"ALLOWED_ROLE_ID_{i}")
            if value:
                values.append(value)
        raw_value = ",".join(values)

    role_ids = set()
    for part in str(raw_value or "").split(","):
        part = part.strip()
        if part.isdigit():
            role_ids.add(int(part))

    return role_ids


async def is_authorized_interaction(interaction, db=None) -> bool:
    allowed_role_ids = await get_allowed_role_ids(db)

    if not allowed_role_ids:
        return True

    user_role_ids = {role.id for role in getattr(interaction.user, "roles", [])}
    return bool(user_role_ids.intersection(allowed_role_ids))
