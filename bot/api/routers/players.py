import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
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

# --- FIX START: Define the long-running sync logic in its own function ---
async def _run_member_sync(db: Database):
    """
    This function contains the actual logic for fetching members and updating the DB.
    It's designed to be run in the background.
    """
    print("Starting background member sync...")
    if not all([GUILD_ID, BOT_TOKEN, PLAYER_SYNC_ROLE_ID]):
        print("Sync failed: Missing required environment variables.")
        return

    all_member_ids_with_role = []
    last_member_id = '0'
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    
    try:
        sync_role_id_int = int(PLAYER_SYNC_ROLE_ID)
    except (ValueError, TypeError):
        print(f"Sync failed: PLAYER_SYNC_ROLE_ID '{PLAYER_SYNC_ROLE_ID}' is not a valid ID.")
        return

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
                        role_ids = [int(role_id) for role_id in member.get('roles', [])]
                        if sync_role_id_int in role_ids:
                            all_member_ids_with_role.append(int(member['user']['id']))
                
                last_member_id = members_chunk[-1]['user']['id']

            except Exception as e:
                print(f"Error during member sync from Discord API: {e}")
                # Stop the sync on API error
                return

    await db.sync_all_server_members(all_member_ids_with_role)
    print(f"Background member sync complete. Processed {len(all_member_ids_with_role)} members.")
# --- FIX END ---


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

# --- FIX START: Convert the sync endpoint to a background task ---
@router.post("/sync", status_code=202) # Use 202 Accepted to indicate background processing
async def sync_server_members(background_tasks: BackgroundTasks, db: Database = Depends(get_db)):
    """
    Triggers a full sync of the server's member list in the background.
    """
    background_tasks.add_task(_run_member_sync, db)
    return {"message": "Member sync started in the background. The page will refresh with new data shortly."}
# --- FIX END ---
