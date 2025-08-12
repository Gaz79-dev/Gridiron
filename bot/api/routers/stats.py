import os
import httpx
import datetime
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from typing import List

from bot.utils.database import Database
from bot.api import auth
from bot.api.dependencies import get_db
from bot.api.models import PlayerStats, AcceptedEvent, MatchUpload, Leaderboard, LeaderboardPlayer, User
from dateutil.parser import parse as parse_datetime

router = APIRouter(
    prefix="/api/stats",
    tags=["stats"],
    dependencies=[Depends(auth.get_current_admin_user)],
)

GUILD_ID = os.getenv("GUILD_ID")
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

# --- FIX START: Re-added endpoints for the engagement page ---

@router.get("/engagement", response_model=List[PlayerStats])
async def get_engagement_stats(db: Database = Depends(get_db)):
    """
    Retrieves player engagement statistics, with calculations
    already performed by the database.
    """
    # The Python loop is no longer needed, as the DB handles the calculation.
    return await db.get_all_player_stats()

@router.get("/player/{user_id}/accepted-events", response_model=List[AcceptedEvent])
async def get_player_accepted_events(user_id: int, db: Database = Depends(get_db)):
    """
    Retrieves all accepted events for a specific player.
    """
    return await db.get_accepted_events_for_user(user_id)

# --- FIX END ---


@router.post("/upload", status_code=201)
async def upload_match_stats(
    event_name: str = Form(...),
    event_date: datetime.date = Form(...),
    file: UploadFile = File(...),
    db: Database = Depends(get_db),
    current_user: User = Depends(auth.get_current_admin_user)
):
    """
    Uploads a match stats CSV, processes it, and stores it in the database.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a CSV.")

    # Create a unique signature for the match to prevent duplicates
    try:
        # Extracts timestamp like "20250809-2039" from the filename
        file_timestamp = file.filename.split('_')[1]
        match_id = f"{event_date.strftime('%Y%m%d')}_{event_name.replace(' ', '-')}_{file_timestamp}"
    except IndexError:
        raise HTTPException(status_code=400, detail="Invalid filename format. Expected 'game-table-ID_TIMESTAMP_SERVER.csv'")

    if await db.check_match_exists(match_id):
        raise HTTPException(status_code=409, detail="A match with this name, date, and timestamp has already been uploaded.")

    # Read and parse the CSV content
    try:
        contents = await file.read()
        decoded_content = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(decoded_content))
        match_stats = list(csv_reader)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV file: {e}")

    # Insert the data into the database
    await db.insert_match_data(match_id, event_name, event_date, current_user.id, match_stats)

    return {"message": "Match stats uploaded successfully.", "match_id": match_id}

@router.get("/leaderboards", response_model=Leaderboard)
async def get_leaderboards(db: Database = Depends(get_db)):
    """
    Calculates and returns the Top 10 leaderboards for various stats.
    """
    # This now correctly calls the database function.
    leaderboard_data = await db.calculate_leaderboards()
    return Leaderboard(**leaderboard_data)

@router.get("/export")
async def export_player_stats_to_csv(db: Database = Depends(get_db)):
    """
    Generates and returns a CSV file containing all player stats and their event history.
    """
    player_data = await db.get_full_player_export_data()

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "Discord User ID", "Player Name", "Accepted Events", "Tentative Events", 
        "Declined Events", "Last Signup Date", "AI Rating", 
        "Event History (Title)", "Event History (Date)", 
        "Event History (Role)", "Event History (Class)"
    ])

    # Write data
    for player in player_data:
        base_row = [
            player['user_id'],
            player.get('display_name', 'N/A'),
            player.get('accepted_count', 0),
            player.get('tentative_count', 0),
            player.get('declined_count', 0),
            player.get('last_signup_date').strftime('%Y-%m-%d %H:%M:%S') if player.get('last_signup_date') else 'N/A',
            player.get('rating', 50)
        ]
        
        if player['event_history']:
            for event in player['event_history']:
                # This is the line we are fixing
                event_time_str = parse_datetime(event.get('event_time')).strftime('%Y-%m-%d %H:%M:%S') if event.get('event_time') else 'N/A'
                
                event_row = base_row + [
                    event.get('event_title', 'N/A'),
                    event_time_str,
                    event.get('role_name', 'N/A'),
                    event.get('subclass_name', 'N/A')
                ]
                writer.writerow(event_row)
        else:
            # If no event history, write the base row with empty event details
            writer.writerow(base_row + ['', '', '', ''])

    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=player_stats_export_{datetime.date.today()}.csv"}
    )
