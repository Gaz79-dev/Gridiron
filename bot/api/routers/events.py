import os
import httpx
import datetime
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

# Use absolute imports from the 'bot' package root
from bot.utils.database import Database, RsvpStatus, ROLES, SUBCLASSES
from bot.api import auth
from bot.ai import squad_optimizer
from bot.api.dependencies import get_db
from bot.api.models import (
    Event, Signup, Squad, SquadBuildRequest, RosterUpdateRequest, 
    SendEmbedRequest, Channel, User, EventLockStatus, EventUpdate, PromoteRequest
)
from bot.cogs.event_management import EMOJI_MAPPING

router = APIRouter(
    prefix="/api/events",
    tags=["events"],
    dependencies=[Depends(auth.get_current_active_user)],
)

# Load constants from environment variables
GUILD_ID = os.getenv("GUILD_ID")
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
LOCK_TIMEOUT_MINUTES = 15

# --- FIX START: New dedicated function for sending the FINAL embed ---
async def _send_finalized_embed(event_id: int, request: SendEmbedRequest, db: Database):
    """
    Sends the FINALIZED squad composition embed to a Discord channel.
    """
    BOT_TOKEN = os.getenv("DISCORD_TOKEN")
    if not BOT_TOKEN: raise HTTPException(status_code=500, detail="Bot token not configured on server.")
    url = f"https://discord.com/api/v10/channels/{request.channel_id}/messages"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}

    event_details = await db.get_event_by_id(event_id) if event_id else None
    title_str, event_time_str = "Team Composition", ""
    if event_details:
        event_timestamp = int(event_details['event_time'].timestamp())
        event_time_str = f" - <t:{event_timestamp}:F>"
        # Use a non-draft title
        title_str = f"Team Composition - {event_details['title']}"
    
    content_str, allowed_mentions = "", {"parse": ["users", "roles"]}
    if request.mention_accepted and event_id:
        signups = await db.get_signups_for_event(event_id)
        accepted_ids = [s['user_id'] for s in signups if s['rsvp_status'] == RsvpStatus.ACCEPTED]
        if accepted_ids:
            content_str = ' '.join([f'<@{uid}>' for uid in accepted_ids])
            allowed_mentions = {"users": [str(uid) for uid in accepted_ids]}

    reserves_list = []
    for squad in request.squads:
        if squad.squad_type == "Reserves":
            reserves_list = [m.display_name for m in squad.members]
            break
            
    fields = []
    for squad in request.squads:
        if squad.squad_type == "Reserves": continue
        member_list = []
        for m in squad.members:
            emoji = EMOJI_MAPPING.get(m.assigned_role_name, "❔")
            member_line = f"{emoji} {m.display_name}"
            if m.startup_task: member_line += f" - **{m.startup_task}**"
            member_list.append(member_line)
        value = "\n".join(member_list) or "Empty"
        fields.append({"name": f"__**{squad.name}**__", "value": value, "inline": True})

    embed_payload = {
        "content": content_str,
        "embeds": [{
            "title": f"{title_str}{event_time_str}",
            # Use a non-draft description
            "description": "The following squads have been finalized for the event.",
            "color": 15844367, 
            "fields": fields, 
            "footer": {"text": f"Reserves: {', '.join(reserves_list) if reserves_list else 'None'}"}
        }],
        "allowed_mentions": allowed_mentions
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=embed_payload)
            response.raise_for_status()
        except Exception as e:
            print(f"Error sending finalized embed to Discord API: {e}")
            raise HTTPException(status_code=502, detail="Failed to send finalized embed to Discord.")
# --- FIX END ---


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
async def get_guild_channels():
    if not BOT_TOKEN or not GUILD_ID:
        raise HTTPException(status_code=500, detail="Bot token or Guild ID not configured on server.")
    url_channels = f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels"
    url_threads = f"https://discord.com/api/v10/guilds/{GUILD_ID}/threads/active"
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

@router.get("/{event_id}/signups", response_model=List[Signup])
async def get_event_signups(event_id: int, db: Database = Depends(get_db)):
    if not BOT_TOKEN or not GUILD_ID:
        raise HTTPException(status_code=500, detail="Bot token or Guild ID not configured on server.")
    signups_records = await db.get_signups_for_event(event_id)
    roster, headers = [], {"Authorization": f"Bot {BOT_TOKEN}"}
    async with httpx.AsyncClient() as client:
        for record in signups_records:
            user_id = record['user_id']
            display_name = f"User ID: {user_id}"
            url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{user_id}"
            try:
                response = await client.get(url, headers=headers)
                if response.is_success:
                    member_data = response.json()
                    display_name = member_data.get('nick') or member_data['user'].get('global_name') or member_data['user']['username']
                elif response.status_code == 404:
                    display_name = f"Left Server ({user_id})"
            except Exception as e:
                print(f"Error fetching member {user_id}: {e}")

            roster.append(Signup(
                user_id=str(user_id),
                display_name=display_name,
                role_name=record.get('role_name'),
                subclass_name=record.get('subclass_name'),
                rsvp_status=record['rsvp_status']
            ))
    return roster

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
    latest_signups = await db.get_signups_for_event(event_id)
    accepted_user_ids = {s['user_id'] for s in latest_signups if s['rsvp_status'] == RsvpStatus.ACCEPTED}
    users_to_remove = current_member_ids - accepted_user_ids
    for user_id in users_to_remove:
        await db.remove_user_from_all_squads(event_id, user_id)
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

# --- FIX START: Update endpoint to call the new finalized embed function ---
@router.post("/{event_id}/finalize-squads", status_code=204)
async def finalize_squads_and_learn(
    event_id: int,
    request: SendEmbedRequest,
    db: Database = Depends(get_db),
    lock_check: None = Depends(check_event_lock)
):
    """
    Sends the final squad embed and triggers the AI learning process.
    """
    await _send_finalized_embed(event_id, request, db)
    
    try:
        squads_for_learning = [s.model_dump() for s in request.squads]
        await db.update_player_affinities(squads_for_learning)
        print(f"AI learning process triggered for event {event_id}.")
    except Exception as e:
        print(f"Error during AI learning process for event {event_id}: {e}")
# --- FIX END ---

@router.post("/send-draft-embed", status_code=204)
async def send_draft_embed(
    event_id: int,
    request: SendEmbedRequest,
    db: Database = Depends(get_db),
    lock_check: None = Depends(check_event_lock)
):
    """
    Sends a squad composition embed to a Discord channel without triggering any learning.
    """
    BOT_TOKEN = os.getenv("DISCORD_TOKEN")
    if not BOT_TOKEN: raise HTTPException(status_code=500, detail="Bot token not configured on server.")
    url = f"https://discord.com/api/v10/channels/{request.channel_id}/messages"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}

    event_details = await db.get_event_by_id(event_id) if event_id else None
    title_str, event_time_str = "Team Composition", ""
    if event_details:
        event_timestamp = int(event_details['event_time'].timestamp())
        event_time_str = f" - <t:{event_timestamp}:F>"
        # Use a DRAFT title
        title_str = f"DRAFT - {event_details['title']}"
    
    content_str, allowed_mentions = "", {"parse": ["users", "roles"]}
    if request.mention_accepted and event_id:
        signups = await db.get_signups_for_event(event_id)
        accepted_ids = [s['user_id'] for s in signups if s['rsvp_status'] == RsvpStatus.ACCEPTED]
        if accepted_ids:
            content_str = ' '.join([f'<@{uid}>' for uid in accepted_ids])
            allowed_mentions = {"users": [str(uid) for uid in accepted_ids]}

    reserves_list = []
    for squad in request.squads:
        if squad.squad_type == "Reserves":
            reserves_list = [m.display_name for m in squad.members]
            break
            
    fields = []
    for squad in request.squads:
        if squad.squad_type == "Reserves": continue
        member_list = []
        for m in squad.members:
            emoji = EMOJI_MAPPING.get(m.assigned_role_name, "❔")
            member_line = f"{emoji} {m.display_name}"
            if m.startup_task: member_line += f" - **{m.startup_task}**"
            member_list.append(member_line)
        value = "\n".join(member_list) or "Empty"
        fields.append({"name": f"__**{squad.name}**__", "value": value, "inline": True})

    embed_payload = {
        "content": content_str,
        "embeds": [{
            "title": f"{title_str}{event_time_str}",
            # Use a DRAFT description
            "description": "The following draft has been prepared for feedback.",
            "color": 15844367, 
            "fields": fields, 
            "footer": {"text": f"Reserves: {', '.join(reserves_list) if reserves_list else 'None'}"}
        }],
        "allowed_mentions": allowed_mentions
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=embed_payload)
            response.raise_for_status()
        except Exception as e:
            print(f"Error sending draft embed to Discord API: {e}")
            raise HTTPException(status_code=502, detail="Failed to send draft embed to Discord.")
