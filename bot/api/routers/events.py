import os
import httpx
import datetime
import asyncio
import re
from fastapi import APIRouter, Depends, HTTPException, Body, status
from typing import List, Optional, Dict

# Use absolute imports from the 'bot' package root
from bot.ai import squad_optimizer
from bot.utils.database import Database, RsvpStatus
from bot.game_systems.hll import ROLES, SUBCLASSES
from bot.api import auth
from bot.api.dependencies import get_db
from bot.api.models import (
    Event, Signup, Squad, SquadBuildRequest, RosterUpdateRequest, 
    SendEmbedRequest, Channel, User, EventLockStatus, EventUpdate, PromoteRequest, SquadReorderRequest,
    TransportEmbedRequest, TransportAssignments  # <--- Added TransportAssignments here
)
from bot.cogs.event_management import EMOJI_MAPPING

router = APIRouter(
    prefix="/api/events",
    tags=["events"],
    dependencies=[Depends(auth.get_current_active_user)],
)

# Load secret-only constants from environment variables.
# Guild/server configuration is read from system_settings inside request handlers.
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
LOCK_TIMEOUT_MINUTES = 15


# --- HELPER FUNCTIONS ---
def _create_team_sheet_embeds(request: SendEmbedRequest, event_details: Optional[Dict], is_draft: bool) -> List[Dict]:
    """
    Builds the main team embed and a separate reserves embed, using an efficient layout.
    """
    title_str = "Team Composition"
    event_time_str = ""
    if event_details:
        event_timestamp = int(event_details['event_time'].timestamp())
        event_time_str = f" - <t:{event_timestamp}:F>"
        title_str = f"{'DRAFT' if is_draft else 'Team Composition'} - {event_details['title']}"

    # --- Main Team Embed ---
    main_embed = {
        "title": f"{title_str}{event_time_str}",
        "description": "The following squads have been prepared for the event.",
        "color": 3447003 if is_draft else 3066993,  # Blue for draft, Green for final
        "fields": []
    }

    squads_for_display = [s for s in request.squads if s.squad_type != "Reserves"]
    
    # Efficient 2-column layout logic
    for i in range(0, len(squads_for_display), 2):
        # First squad in the pair
        squad1 = squads_for_display[i]
        member_lines1 = []
        for m in squad1.members:
            emoji = EMOJI_MAPPING.get(m.assigned_role_name, "❔")
            member_line = f"{emoji} {m.display_name}"
            if m.startup_task:
                member_line += f" - **{m.startup_task}**"
            member_lines1.append(member_line)
        value1 = "\n".join(member_lines1) or "Empty"
        main_embed["fields"].append({"name": f"__**{squad1.name}**__", "value": value1, "inline": True})

        # Second squad in the pair (if it exists)
        if (i + 1) < len(squads_for_display):
            squad2 = squads_for_display[i+1]
            member_lines2 = []
            for m in squad2.members:
                emoji = EMOJI_MAPPING.get(m.assigned_role_name, "❔")
                member_line = f"{emoji} {m.display_name}"
                if m.startup_task:
                    member_line += f" - **{m.startup_task}**"
                member_lines2.append(member_line)
            value2 = "\n".join(member_lines2) or "Empty"
            main_embed["fields"].append({"name": f"__**{squad2.name}**__", "value": value2, "inline": True})
        else:
            # If there's an odd number of squads, add a blank field to keep alignment.
            main_embed["fields"].append({"name": "\u200b", "value": "\u200b", "inline": True})

    # --- Reserves Embed ---
    reserves_embed = None
    reserves_list = []
    for squad in request.squads:
        if squad.squad_type == "Reserves":
            reserves_list = [m.display_name for m in squad.members]
            break

    if reserves_list:
        reserves_embed = {
            "title": "Reserves",
            "color": 9807270, # Grey
            "fields": []
        }
        
        # Dynamic Splitting for reserves list
        parts = []
        current_part = ""
        for name in reserves_list:
            if len(current_part) + len(name) + 2 > 1024: # +2 for ", "
                parts.append(current_part)
                current_part = name
            else:
                current_part += f", {name}" if current_part else name
        parts.append(current_part)

        for i, part in enumerate(parts):
            field_name = f"Reserves ({i+1}/{len(parts)})" if len(parts) > 1 else "Reserves"
            reserves_embed["fields"].append({"name": field_name, "value": part, "inline": False})

    final_embeds = [main_embed]
    if reserves_embed:
        final_embeds.append(reserves_embed)
        
    return final_embeds


async def _send_embed_to_discord(event_id: int, request: SendEmbedRequest, db: Database, is_draft: bool):
    """
    Handles the logic for sending embeds to Discord.
    """
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Bot token not configured on server.")
    
    url = f"https://discord.com/api/v10/channels/{request.channel_id}/messages"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    
    event_details = await db.get_event_by_id(event_id)
    
    content_str = ""
    allowed_mentions = {"parse": ["users", "roles"]}
    if request.mention_accepted and event_id:
        signups = await db.get_signups_for_roster_page(event_id)
        accepted_ids = [s['user_id'] for s in signups if s['rsvp_status'] == RsvpStatus.ACCEPTED]
        if accepted_ids:
            content_str = ' '.join([f'<@{uid}>' for uid in accepted_ids])
            allowed_mentions = {"users": [str(uid) for uid in accepted_ids]}

    embeds_to_send = _create_team_sheet_embeds(request, event_details, is_draft)

    payload = {
        "content": content_str,
        "embeds": embeds_to_send,
        "allowed_mentions": allowed_mentions
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"Error sending embed to Discord API: {e}")
            print(f"Response body: {e.response.text}")
            raise HTTPException(status_code=502, detail=f"Failed to send embed to Discord: {e.response.text}")

def _create_nodes_embed(event_details: Dict, members: List[Dict]) -> Dict:
    """
    Creates a specialized embed for Node building tasks.
    """
    nodes_data = {"HQ1": [], "HQ2": [], "HQ3": []}
    
    for m in members:
        task = m.get('startup_task')
        if not task:
            continue
            
        match = re.match(r'HQ([1-3])\s+(.*)', task, re.IGNORECASE)
        if match:
            hq_num = f"HQ{match.group(1)}"
            rest_of_task = match.group(2).lower()
            if "supplies" in rest_of_task or "engineer" in rest_of_task or "nodes" in rest_of_task:
                nodes_data[hq_num].append(f"• {m['display_name']} ({m.get('startup_task')})")

    embed = {
        "title": f"Nodes Building Plan - {event_details['title']}",
        "description": "Assignments for building 3 sets of nodes at start of match.",
        "color": 15105570, # Orange-ish
        "fields": []
    }
    
    for hq in ["HQ1", "HQ2", "HQ3"]:
        assignments = nodes_data.get(hq, [])
        value = "\n".join(assignments) if assignments else "*No assignments*"
        embed["fields"].append({
            "name": f"__**{hq} Nodes**__", 
            "value": value, 
            "inline": True 
        })
        
    return embed

def _create_transport_embed(event_details: Dict, members: List[Dict], squad_assignments: Dict[str, List[str]]) -> Dict:
    """
    Creates an embed showing Drivers and Squad Deployments per HQ.
    """
    drivers_map = {"HQ1": [], "HQ2": [], "HQ3": []}
    
    # 1. Find Drivers
    for m in members:
        task = m.get('startup_task')
        if not task: continue
        
        # Regex to find 'HQx ... Driver'
        match = re.match(r'HQ([1-3])\s+(.*)', task, re.IGNORECASE)
        if match:
            hq_num = f"HQ{match.group(1)}"
            rest_of_task = match.group(2).lower()
            if "driver" in rest_of_task or "transport" in rest_of_task:
                 drivers_map[hq_num].append(m['display_name'])

    embed = {
        "title": f"Transport & Deployment - {event_details['title']}",
        "description": "Transport assignments and squad deployment locations.",
        "color": 3066993, # Green
        "fields": []
    }
    
    for hq in ["HQ1", "HQ2", "HQ3"]:
        # Drivers
        drivers = drivers_map.get(hq, [])
        driver_text = ", ".join(drivers) if drivers else "*None assigned*"
        
        # Squads
        squads = squad_assignments.get(hq, [])
        squad_text = "\n".join([f"• {s}" for s in squads]) if squads else "*None*"
        
        content = f"**Drivers:** {driver_text}\n\n**Squads:**\n{squad_text}"
        
        embed["fields"].append({
            "name": f"__**{hq} Location**__",
            "value": content,
            "inline": True
        })
        
    return embed

# --- Locking Dependency ---
async def check_event_lock(event_id: int, current_user: User = Depends(auth.get_current_admin_user), db: Database = Depends(get_db)):
    lock_status = await db.get_event_lock_status(event_id)
    if not lock_status or lock_status.get('locked_by_user_id') is None: return
    if lock_status.get('locked_by_user_id') == current_user.id: return
    if lock_status.get('locked_by_username') is None:
        await db.unlock_event(event_id)
        return
    if lock_status.get('locked_at'):
        lock_age = datetime.datetime.now(datetime.timezone.utc) - lock_status['locked_at']
        if lock_age.total_seconds() > LOCK_TIMEOUT_MINUTES * 60: return
    raise HTTPException(
        status_code=status.HTTP_423_LOCKED,
        detail=f"Event is locked for editing by {lock_status.get('locked_by_username', 'another user')}.",
    )

# --- API Routes ---

@router.post("/{event_id}/promote-tentative", response_model=List[Squad], dependencies=[Depends(check_event_lock)])
async def promote_tentative_player(event_id: int, request: PromoteRequest, db: Database = Depends(get_db)):
    primary_role, subclass_name = None, None
    for role, subclasses in SUBCLASSES.items():
        if request.new_role_name in subclasses:
            primary_role, subclass_name = role, request.new_role_name
            break
    if not primary_role and request.new_role_name in ROLES:
        primary_role = request.new_role_name
    if not primary_role: primary_role = "Unassigned"

    try:
        user_id_int = int(request.user_id)
        await db.promote_tentative_player(event_id, user_id_int, primary_role, subclass_name)
        reserves_squad = await db.get_squad_by_name(event_id, "Reserves")
        if reserves_squad:
            await db.add_squad_member(reserves_squad['squad_id'], user_id_int, request.new_role_name)
        await db.flag_event_for_embed_update(event_id)
        return await db.get_squads_with_members(event_id)
    except Exception as e:
        print(f"Error promoting tentative player: {e}")
        raise HTTPException(status_code=500, detail="Failed to update player status in the database.")

@router.get("", response_model=List[Event])
async def get_events(db: Database = Depends(get_db)):
    return await db.get_upcoming_events()

@router.get("/recurring", response_model=List[Event], dependencies=[Depends(auth.get_current_admin_user)])
async def get_recurring_events(db: Database = Depends(get_db)):
    return await db.get_recurring_parent_events()

@router.get("/deleted", response_model=List[Event], dependencies=[Depends(auth.get_current_admin_user)])
async def get_deleted_events_for_restore(db: Database = Depends(get_db)):
    return await db.get_deleted_events()

@router.get("/channels")
async def get_guild_channels(db: Database = Depends(get_db)):
    guild_id = await db.get_system_setting_value("guild_id")

    if not BOT_TOKEN or not guild_id:
        raise HTTPException(status_code=500, detail="Bot token or Guild ID not configured on server.")
    url_channels = f"https://discord.com/api/v10/guilds/{guild_id}/channels"
    url_threads = f"https://discord.com/api/v10/guilds/{guild_id}/threads/active"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    async with httpx.AsyncClient() as client:
        try:
            res_channels_task = client.get(url_channels, headers=headers)
            res_threads_task = client.get(url_threads, headers=headers)
            res_channels, res_threads = await asyncio.gather(res_channels_task, res_threads_task)
            res_channels.raise_for_status()
            res_threads.raise_for_status()
            all_channels, active_threads = res_channels.json(), res_threads.json().get('threads', [])
            categories = {c['id']: c['name'] for c in all_channels if c['type'] == 4}
            processed_list = []
            for c in all_channels:
                if c['type'] == 0:
                    category_name = categories.get(c.get('parent_id'))
                    processed_list.append({"id": str(c['id']), "name": c['name'], "category": category_name})
            for t in active_threads:
                if t['type'] in [11, 12]:
                    category_name = categories.get(t.get('parent_id'))
                    thread_name = f"└ Thread: {t['name']}"
                    processed_list.append({"id": str(t['id']), "name": thread_name, "category": category_name})
            return sorted(processed_list, key=lambda c: (c.get('category') or ' ', c.get('name')))
        except Exception as e:
            print(f"Error fetching channels from Discord API: {e}")
            raise HTTPException(status_code=502, detail="Failed to fetch channels from Discord.")

@router.get("/{event_id}", response_model=Event, dependencies=[Depends(auth.get_current_admin_user)])
async def get_event_details(event_id: int, db: Database = Depends(get_db)):
    event = await db.get_event_by_id(event_id, include_deleted=True)
    if not event: raise HTTPException(status_code=404, detail="Event not found")
    return event

@router.put("/{event_id}", response_model=Event, dependencies=[Depends(auth.get_current_admin_user)])
async def update_event_details(event_id: int, event_data: EventUpdate, db: Database = Depends(get_db)):
    await db.update_event(event_id, event_data.model_dump())
    return await get_event_details(event_id, db)

@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(auth.get_current_admin_user)])
async def delete_event(event_id: int, db: Database = Depends(get_db)):
    event_to_delete = await db.get_event_by_id(event_id, include_deleted=True)
    if not event_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    await db.delete_event(event_id)
    return

@router.get("/{event_id}/lock-status", response_model=EventLockStatus)
async def get_lock_status(event_id: int, db: Database = Depends(get_db)):
    lock_info = await db.get_event_lock_status(event_id)
    if not lock_info or not lock_info.get('locked_by_user_id') or not lock_info.get('locked_at'):
        return EventLockStatus(is_locked=False)
    lock_age = datetime.datetime.now(datetime.timezone.utc) - lock_info['locked_at']
    if lock_age.total_seconds() > LOCK_TIMEOUT_MINUTES * 60:
        return EventLockStatus(is_locked=False)
    return EventLockStatus(is_locked=True, locked_by_user_id=lock_info['locked_by_user_id'], locked_by_username=lock_info.get('locked_by_username'))

@router.post("/{event_id}/lock", status_code=204, dependencies=[Depends(check_event_lock)])
async def lock_event(event_id: int, current_user: User = Depends(auth.get_current_admin_user), db: Database = Depends(get_db)):
    await db.lock_event(event_id, current_user.id)

@router.post("/{event_id}/unlock", status_code=204)
async def unlock_event(event_id: int, current_user: User = Depends(auth.get_current_admin_user), db: Database = Depends(get_db)):
    lock_status = await db.get_event_lock_status(event_id)
    if lock_status and lock_status.get('locked_by_user_id') == current_user.id:
        await db.unlock_event(event_id)

@router.post("/force-unlock-all", status_code=204, dependencies=[Depends(auth.get_current_admin_user)])
async def force_unlock_all_events_endpoint(db: Database = Depends(get_db)):
    await db.force_unlock_all_events()
    print("ADMIN ACTION: All events were force-unlocked.")
    return

@router.get("/{event_id}/squads", response_model=List[Squad])
async def get_event_squads(event_id: int, db: Database = Depends(get_db)):
    return await db.get_squads_with_members(event_id)

@router.get("/{event_id}/roster", response_model=List[Signup])
async def get_event_roster_for_web(event_id: int, db: Database = Depends(get_db)):
    return await db.get_signups_for_roster_page(event_id)
    
@router.post("/{event_id}/build-squads", response_model=List[Squad], dependencies=[Depends(check_event_lock)])
async def build_squads_for_event(event_id: int, request: SquadBuildRequest, db: Database = Depends(get_db)):
    try:
        return await squad_optimizer.run_ai_draft(db, event_id, request)
    except Exception as e:
        print(f"Error during AI squad build process: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred during AI squad drafting.")

@router.post("/{event_id}/refresh-roster", response_model=List[Squad], dependencies=[Depends(check_event_lock)])
async def refresh_event_roster(event_id: int, request: RosterUpdateRequest, db: Database = Depends(get_db)):
    current_member_ids = {int(member.user_id) for squad in request.squads for member in squad.members}
    latest_signups = await db.get_signups_for_roster_page(event_id)
    accepted_user_ids = {int(s['user_id']) for s in latest_signups if s['rsvp_status'] == RsvpStatus.ACCEPTED}
    users_to_remove = current_member_ids - accepted_user_ids
    for user_id in users_to_remove:
        await db.remove_user_from_all_squads(event_id, user_id)
    
    # Cleanup White Chats
    await db.cleanup_white_chat_memberships(event_id)

    squads_with_members = await db.get_squads_with_members(event_id)
    all_current_db_member_ids = {int(member['user_id']) for squad in squads_with_members for member in squad.get('members', [])}
    new_users = accepted_user_ids - all_current_db_member_ids
    if new_users:
        reserves_squad = await db.get_squad_by_name(event_id, "Reserves")
        if reserves_squad:
            for user_id in new_users:
                signup = await db.get_signup(event_id, user_id)
                if signup:
                    role_name = signup.get('subclass_name') or signup.get('role_name', 'Unassigned') or 'Unassigned'
                    await db.add_squad_member(reserves_squad['squad_id'], user_id, role_name)
        await db.flag_event_for_embed_update(event_id)
    return await db.get_squads_with_members(event_id)

@router.post("/{event_id}/finalize-squads", status_code=204)
async def finalize_squads_and_learn(
    event_id: int,
    request: SendEmbedRequest,
    db: Database = Depends(get_db),
    lock_check: None = Depends(check_event_lock)
):
    await _send_embed_to_discord(event_id, request, db, is_draft=False)
    
    try:
        squads_for_learning = [s.model_dump() for s in request.squads]
        await db.update_player_affinities(squads_for_learning)
        # Save the finalized roster snapshot
        await db.save_finalized_roster(event_id, squads_for_learning)
        print(f"AI learning and roster snapshot triggered for event {event_id}.")
    except Exception as e:
        print(f"Error during AI learning/snapshot process for event {event_id}: {e}")

@router.post("/send-draft-embed", status_code=204)
async def send_draft_embed(
    event_id: int,
    request: SendEmbedRequest,
    db: Database = Depends(get_db),
    lock_check: None = Depends(check_event_lock)
):
    await _send_embed_to_discord(event_id, request, db, is_draft=True)
    
@router.post("/{event_id}/send-nodes-embed", status_code=204)
async def send_nodes_embed(
    event_id: int,
    channel_payload: Dict[str, str] = Body(...),
    db: Database = Depends(get_db)
):
    """
    Generates and sends the 'Nodes Building Plan' embed based on existing task assignments.
    """
    channel_id = channel_payload.get('channel_id')
    if not channel_id:
         raise HTTPException(status_code=400, detail="channel_id is required")
         
    event_details = await db.get_event_by_id(event_id)
    if not event_details:
        raise HTTPException(status_code=404, detail="Event not found")
        
    squads = await db.get_squads_with_members(event_id)
    all_members = [m for s in squads for m in s.get('members', [])]
    
    nodes_embed = _create_nodes_embed(event_details, all_members)
    
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    payload = {"embeds": [nodes_embed]}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"Error sending nodes embed: {e}")
            raise HTTPException(status_code=502, detail=f"Failed to send nodes embed to Discord: {e.response.text}")
            
    return

# --- NEW: Transport Assignments Endpoints (Persistence) ---

@router.get("/{event_id}/transport", response_model=TransportAssignments)
async def get_transport_assignments(event_id: int, db: Database = Depends(get_db)):
    """
    Retrieves the saved transport assignments for an event.
    """
    assignments = await db.get_transport_assignments(event_id)
    return TransportAssignments(assignments=assignments)

@router.post("/{event_id}/transport", status_code=204)
async def save_transport_assignments(
    event_id: int,
    request: TransportAssignments,
    db: Database = Depends(get_db)
):
    """
    Saves the transport assignments to the database.
    """
    await db.save_transport_assignments(event_id, request.assignments)
    return

@router.post("/{event_id}/send-transport-embed", status_code=204)
async def send_transport_embed(
    event_id: int,
    request: TransportEmbedRequest,
    db: Database = Depends(get_db)
):
    """
    Generates and sends the 'Transport & Deployment' embed based on task assignments and user input.
    Also saves the current assignments to the database.
    """
    event_details = await db.get_event_by_id(event_id)
    if not event_details:
        raise HTTPException(status_code=404, detail="Event not found")
        
    # 1. SAVE to Database first
    await db.save_transport_assignments(event_id, request.assignments)

    # 2. Get data for embed
    squads = await db.get_squads_with_members(event_id)
    all_members = [m for s in squads for m in s.get('members', [])]
    
    transport_embed = _create_transport_embed(event_details, all_members, request.assignments)
    
    url = f"https://discord.com/api/v10/channels/{request.channel_id}/messages"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    payload = {"embeds": [transport_embed]}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"Error sending transport embed: {e}")
            raise HTTPException(status_code=502, detail=f"Failed to send transport embed to Discord: {e.response.text}")
            
    return
