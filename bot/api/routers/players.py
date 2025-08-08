import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

# Use absolute imports from the 'bot' package root
from bot.utils.database import Database
from bot.api import auth
from bot.api.dependencies import get_db
from bot.api.models import PlayerAdminInfo, PlayerRatingUpdate

router = APIRouter(
    prefix="/api/players",
    tags=["players"],
    dependencies=[Depends(auth.get_current_admin_user)],
)

GUILD_ID = os.getenv("GUILD_ID")
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
PLAYER_SYNC_ROLE_ID = os.getenv("PLAYER_SYNC_ROLE_ID")

@router.get("", response_model=List[PlayerAdminInfo])
async def get_all_players_for_admin(db: Database = Depends(get_db)):
    """
    Retrieves all players (active and inactive) for the admin rating panel.
    """
    if not GUILD_ID or not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Bot token or Guild ID not configured on server.")

    player_stats = await db.get_all_player_stats_for_admin()
    player_list = []
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}

    async with httpx.AsyncClient() as client:
        for stats in player_stats:
            user_id = stats['user_id']
            display_name = f"User ID: {user_id}"
            
            if stats.get('is_active', False):
                url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{user_id}"
                try:
                    response = await client.get(url, headers=headers)
                    if response.is_success:
                        member_data = response.json()
                        display_name = member_data.get('nick') or member_data['user'].get('global_name') or member_data['user']['username']
                    elif response.status_code == 404:
                        display_name = f"Left Server ({user_id})"
                except Exception as e:
                    print(f"Error fetching member {user_id} for admin panel: {e}")
            else:
                display_name = f"Inactive User ({user_id})"

            player_list.append(PlayerAdminInfo(
                user_id=str(user_id),
                display_name=display_name,
                rating=stats.get('rating', 50),
                is_active=stats.get('is_active', False)
            ))
            
    return player_list

@router.put("/rating", status_code=204)
async def update_player_rating(update_data: PlayerRatingUpdate, db: Database = Depends(get_db)):
    """
    Updates a single player's skill rating.
    """
    try:
        user_id_int = int(update_data.user_id)
        await db.update_player_rating(user_id_int, update_data.rating)
    except Exception as e:
        print(f"Error updating player rating: {e}")
        raise HTTPException(status_code=500, detail="Failed to update rating in database.")

@router.post("/sync", status_code=200)
async def sync_server_members(db: Database = Depends(get_db)):
    """
    Triggers a full sync of the server's member list with the database,
    filtered by the PLAYER_SYNC_ROLE_ID.
    """
    if not all([GUILD_ID, BOT_TOKEN, PLAYER_SYNC_ROLE_ID]):
        raise HTTPException(status_code=500, detail="Bot token, Guild ID, or Player Sync Role ID not configured on server.")

    all_member_ids_with_role = []
    last_member_id = '0'
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    
    # --- FIX: Convert the role ID to an integer once for reliable comparison ---
    try:
        sync_role_id_int = int(PLAYER_SYNC_ROLE_ID)
    except (ValueError, TypeError):
        raise HTTPException(status_code=500, detail="PLAYER_SYNC_ROLE_ID in .env is not a valid ID.")

    async with httpx.AsyncClient() as client:
        while True:
            try:
                url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/members?limit=1000&after={last_member_id}"
                response = await client.get(url, headers=headers, timeout=30.0)
                response.raise_for_status()
                members_chunk = response.json()
                
                if not members_chunk:
                    break
                
                for member in members_chunk:
                    if not member['user'].get('bot', False):
                        # --- FIX: Compare integer IDs for robustness ---
                        role_ids = [int(role_id) for role_id in member.get('roles', [])]
                        if sync_role_id_int in role_ids:
                            all_member_ids_with_role.append(int(member['user']['id']))
                
                last_member_id = members_chunk[-1]['user']['id']

            except Exception as e:
                print(f"Error during member sync from Discord API: {e}")
                raise HTTPException(status_code=502, detail="Failed to fetch full member list from Discord.")

    await db.sync_all_server_members(all_member_ids_with_role)
    return {"message": f"Sync complete. {len(all_member_ids_with_role)} members with the specified role processed."}
