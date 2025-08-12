import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

# Use absolute imports from the 'bot' package root
from bot.utils.database import Database
from bot.api import auth
from bot.api.dependencies import get_db
from bot.api.models import PlayerAdminInfo, PlayerGameIdUpdate, PlayerRatingUpdate

router = APIRouter(
    prefix="/api/players",
    tags=["players"],
    dependencies=[Depends(auth.get_current_admin_user)],
)

@router.get("", response_model=List[PlayerAdminInfo])
async def get_all_players_for_admin(db: Database = Depends(get_db)):
    """
    Retrieves all players for the admin rating panel, using cached display names
    for fast loading.
    """
    # This line is the only one that changes in this file
    player_stats = await db.get_all_player_stats(include_inactive=True)
    
    player_list = []

    for stats in player_stats:
        display_name = stats.get('display_name') or f"User ID: {stats['user_id']}"
        if not stats.get('is_active'):
            display_name = f"[Inactive] {display_name}"

        player_list.append(PlayerAdminInfo(
            user_id=str(stats['user_id']),
            display_name=display_name,
            rating=stats.get('rating', 50),
            is_active=stats.get('is_active', True),
            game_player_id=stats.get('game_player_id')
        ))
            
    return player_list

# --- FIX START: Added the missing endpoint for updating player ratings ---
@router.put("/rating", status_code=204)
async def update_player_rating(update_data: PlayerRatingUpdate, db: Database = Depends(get_db)):
    """
    Updates a player's skill rating.
    """
    try:
        user_id_int = int(update_data.user_id)
        await db.update_player_rating(user_id_int, update_data.rating)
    except Exception as e:
        print(f"Error updating player rating: {e}")
        raise HTTPException(status_code=500, detail="Failed to update rating in database.")
# --- FIX END ---

@router.put("/game-id", status_code=204)
async def update_player_game_id(update_data: PlayerGameIdUpdate, db: Database = Depends(get_db)):
    """
    Updates a player's in-game ID to link their Discord account to match stats.
    """
    try:
        user_id_int = int(update_data.user_id)
        await db.update_player_game_id(user_id_int, update_data.game_player_id)
    except Exception as e:
        print(f"Error updating player game ID: {e}")
        raise HTTPException(status_code=500, detail="Failed to update game ID in database.")

