from fastapi import APIRouter, Depends
from typing import Dict, Optional

from bot.api import auth
from bot.api.dependencies import get_db
from bot.utils.database import Database
from bot.game_systems.registry import get_all_game_systems, get_game_system
from bot.game_systems.hll import DEFAULT_EMOJI_MAPPING, EMOJI_SETTING_KEYS, ROLES, SUBCLASSES
from bot.api.models import RoleUpdateRequest, SquadMoveRequest, StartupTaskUpdateRequest, SquadReorderRequest

router = APIRouter(prefix="/api/squads", tags=["squads"], dependencies=[Depends(auth.get_current_active_user)])


def _roles_payload_for_game(game_id: str = "hll") -> Dict:
    game = get_game_system(game_id or "hll")
    return {
        "game_id": game.get("game_id", game_id or "hll"),
        "display_name": game.get("display_name", "Hell Let Loose"),
        "roles": getattr(game, "ROLES", game.get("roles", ROLES)),
        "subclasses": getattr(game, "SUBCLASSES", game.get("subclasses", SUBCLASSES)),
    }


@router.get("/roles", response_model=Dict)
async def get_all_roles(
    game_id: Optional[str] = None,
    event_id: Optional[int] = None,
    db: Database = Depends(get_db),
):
    if event_id is not None:
        event = await db.get_event_by_id(event_id, include_deleted=True)
        game_id = (event or {}).get("game_id", game_id or "hll")
    return _roles_payload_for_game(game_id or "hll")


@router.get("/emojis", response_model=Dict[str, str])
async def get_emojis(db: Database = Depends(get_db)):
    mapping = {}
    setting_keys = {}
    for game in get_all_game_systems():
        mapping.update(game.get('default_emoji_mapping', {}))
        setting_keys.update(game.get('emoji_setting_keys', {}))
    if not mapping:
        mapping = DEFAULT_EMOJI_MAPPING.copy()
    if not setting_keys:
        setting_keys = EMOJI_SETTING_KEYS.copy()

    for name, key in setting_keys.items():
        value = await db.get_system_setting_value(key)
        if value:
            mapping[name] = value

    return mapping


@router.put("/members/{squad_member_id}/role", status_code=204)
async def update_member_role(squad_member_id: int, request: RoleUpdateRequest, db: Database = Depends(get_db)):
    await db.update_squad_member_role(squad_member_id, request.new_role_name)
    member_details = await db.get_squad_member_details(squad_member_id)
    if not member_details:
        return

    event = await db.get_event_by_id(request.event_id, include_deleted=True)
    roles_payload = _roles_payload_for_game((event or {}).get("game_id", "hll"))
    roles = roles_payload["roles"]
    subclasses_by_role = roles_payload["subclasses"]

    user_id, new_primary_role, new_subclass_name = member_details['user_id'], None, None
    for role, subclasses in subclasses_by_role.items():
        if request.new_role_name in subclasses:
            new_primary_role, new_subclass_name = role, request.new_role_name
            break
    if not new_primary_role and request.new_role_name in roles:
        new_primary_role = request.new_role_name

    if new_primary_role:
        await db.update_signup_role(request.event_id, user_id, new_primary_role, new_subclass_name)

    await db.flag_event_for_embed_update(request.event_id)


@router.put("/members/{squad_member_id}/move", status_code=204)
async def move_member_to_squad(squad_member_id: int, request: SquadMoveRequest, db: Database = Depends(get_db)):
    await db.move_squad_member(squad_member_id, request.new_squad_id)


@router.put("/{squad_id}/reorder", status_code=204)
async def reorder_squad_members(
    squad_id: int,
    request: SquadReorderRequest,
    db: Database = Depends(get_db)
):
    await db.update_squad_member_order(squad_id, request.ordered_member_ids)


@router.put("/members/{squad_member_id}/task", status_code=204)
async def update_member_startup_task(
    squad_member_id: int,
    request: StartupTaskUpdateRequest,
    db: Database = Depends(get_db)
):
    task_to_store = request.task if request.task else None
    await db.update_squad_member_task(squad_member_id, task_to_store)
