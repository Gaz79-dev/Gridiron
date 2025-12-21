import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Body, status
from typing import List, Dict, Any

from bot.api import auth
from bot.api.dependencies import get_db
from bot.utils.database import Database
from bot.api.models import WhiteChat, WhiteChatCreateRequest, WhiteChatMemberRequest

router = APIRouter(
    prefix="/api/white-chats",
    tags=["white-chats"],
    dependencies=[Depends(auth.get_current_active_user)],
)

# Load Bot Token
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

@router.get("/event/{event_id}", response_model=List[WhiteChat])
async def get_white_chats(event_id: int, db: Database = Depends(get_db)):
    """
    Retrieves all white chat groups and their members for a specific event.
    """
    return await db.get_white_chats_with_members(event_id)

@router.post("/event/{event_id}/create", status_code=status.HTTP_201_CREATED)
async def create_white_chats(
    event_id: int, 
    request: WhiteChatCreateRequest, 
    db: Database = Depends(get_db)
):
    """
    Creates N new white chat groups for an event.
    WARNING: This will delete any existing white chats for this event.
    """
    # 1. Clear existing groups to avoid duplicates/confusion
    await db.delete_white_chats_for_event(event_id)
    
    # 2. Create new groups
    created_ids = []
    for i in range(1, request.count + 1):
        # Naming convention: "Party 1", "Party 2", etc.
        name = f"Party {i}"
        new_id = await db.create_white_chat_group(event_id, name)
        created_ids.append(new_id)
        
    return {"message": f"Successfully created {len(created_ids)} white chat groups.", "ids": created_ids}

@router.post("/{white_chat_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    white_chat_id: int, 
    request: WhiteChatMemberRequest, 
    db: Database = Depends(get_db)
):
    """
    Adds a user to a white chat group.
    Ensures the user is removed from any other white chat in the same event first.
    """
    # Efficient approach: Fetch the white chat to get the event_id
    async with db.pool.acquire() as conn:
        event_id = await conn.fetchval("SELECT event_id FROM white_chats WHERE id = $1", white_chat_id)
    
    if not event_id:
        raise HTTPException(status_code=404, detail="White chat group not found.")

    user_id_int = int(request.user_id)

    # 2. Remove user from ANY white chat associated with this event
    await db.remove_user_from_all_white_chats(event_id, user_id_int)

    # 3. Add to the new white chat
    await db.add_white_chat_member(white_chat_id, user_id_int)
    
    return {"message": "Member added successfully"}

@router.delete("/{white_chat_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    white_chat_id: int, 
    user_id: str, 
    db: Database = Depends(get_db)
):
    """
    Removes a user from a white chat group.
    """
    await db.remove_white_chat_member(white_chat_id, int(user_id))
    return

@router.post("/event/{event_id}/notify", status_code=status.HTTP_200_OK)
async def send_white_chat_notification(
    event_id: int,
    channel_id_payload: Dict[str, str] = Body(...),
    db: Database = Depends(get_db)
):
    """
    Generates a Discord Embed listing all white chats and members, and sends it to the specified channel.
    Uses HTTP requests to Discord API to avoid needing a Bot instance in the Web process.
    """
    channel_id_str = channel_id_payload.get("channel_id")
    if not channel_id_str:
        raise HTTPException(status_code=400, detail="channel_id is required")
    
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Bot token not configured on server.")

    # 1. Fetch Data
    event = await db.get_event_by_id(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    parties = await db.get_white_chats_with_members(event_id)
    if not parties:
        raise HTTPException(status_code=400, detail="No white chats created for this event.")

    # 2. Build Embed Dictionary (Raw JSON for Discord API)
    fields = []
    for party in parties:
        member_list = party.get("members", [])
        if not member_list:
            content = "*Empty*"
        else:
            lines = []
            for m in member_list:
                lines.append(f"• {m['display_name']}")
            content = "\n".join(lines)
        
        fields.append({
            "name": f"⚪ {party['name']}",
            "value": content,
            "inline": True
        })

    embed = {
        "title": f"Competitive Voice Channels - {event['title']}",
        "description": "Please join your assigned white chat/party voice channel.",
        "color": 16777215, # White color (0xFFFFFF)
        "fields": fields
    }

    payload = {
        "embeds": [embed]
    }

    # 3. Send Message via HTTP
    url = f"https://discord.com/api/v10/channels/{channel_id_str}/messages"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"Error sending white chat embed to Discord: {e}")
            print(f"Response: {e.response.text}")
            raise HTTPException(status_code=502, detail=f"Failed to send Discord message: {e.response.text}")
        except Exception as e:
            print(f"Unexpected error sending white chat embed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error sending message.")

    return {"message": "White chat notification sent successfully."}
