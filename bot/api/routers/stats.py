import os
import datetime
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from typing import List

from bot.utils.database import Database
from bot.api import auth
from bot.api.dependencies import get_db
# --- START: MODIFICATION - Update imported model name ---
from bot.api.models import PlayerStats, PlayerEventHistoryEntry, MatchUpload, Leaderboard, User
# --- END: MODIFICATION ---
from dateutil.parser import parse as parse_datetime

router = APIRouter(
    prefix="/api/stats",
    tags=["stats"],
    dependencies=[Depends(auth.get_current_admin_user)],
)

@router.get("/engagement", response_model=List[PlayerStats])
async def get_engagement_stats(db: Database = Depends(get_db)):
    """
    Retrieves player engagement statistics by reading the persistent,
    running totals from the player_stats table.
    """
    return await db.get_engagement_stats()

# --- START: MODIFICATION - Update endpoint, function, and response model ---
@router.get("/player/{user_id}/event-history", response_model=List[PlayerEventHistoryEntry])
async def get_player_event_history(user_id: int, db: Database = Depends(get_db)):
    """
    Retrieves all snapshotted event history for a specific player.
    """
    return await db.get_event_history_for_user(user_id)
# --- END: MODIFICATION ---

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

    try:
        file_timestamp = file.filename.split('_')[1]
        match_id = f"{event_date.strftime('%Y%m%d')}_{event_name.replace(' ', '-')}_{file_timestamp}"
    except IndexError:
        raise HTTPException(status_code=400, detail="Invalid filename format. Expected 'game-table-ID_TIMESTAMP_SERVER.csv'")

    if await db.check_match_exists(match_id):
        raise HTTPException(status_code=409, detail="A match with this name, date, and timestamp has already been uploaded.")

    try:
        contents = await file.read()
        decoded_content = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(decoded_content))
        match_stats = list(csv_reader)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV file: {e}")

    await db.insert_match_data(match_id, event_name, event_date, current_user.id, match_stats)
    return {"message": "Match stats uploaded successfully.", "match_id": match_id}

@router.get("/leaderboards", response_model=Leaderboard)
async def get_leaderboards(db: Database = Depends(get_db)):
    """
    Calculates and returns the leaderboards for various stats.
    """
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

    writer.writerow([
        "Discord User ID", "Player Name", "Accepted Events", "Tentative Events",
        "Declined Events", "Last Signup Date", "AI Rating",
        "Event History (Title)", "Event History (Date)",
        "Event History (Role)", "Event History (Class)"
    ])

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
                event_time_str = parse_datetime(event.get('event_time')).strftime('%Y-%m-%d %H:%M:%S') if event.get('event_time') else 'N/A'
                event_row = base_row + [
                    event.get('event_title', 'N/A'),
                    event_time_str,
                    event.get('role_name', 'N/A'),
                    event.get('subclass_name', 'N/A')
                ]
                writer.writerow(event_row)
        else:
            writer.writerow(base_row + ['', '', '', ''])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=player_stats_export_{datetime.date.today()}.csv"}
    )
