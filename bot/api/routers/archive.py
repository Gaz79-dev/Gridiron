import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# Use absolute imports matching your project structure
from bot.api import auth
from bot.api.dependencies import get_db
from bot.utils.database import Database

# --- Pydantic Models for Archive Responses ---
# We define them here to keep the archive logic self-contained, 
# but they can be moved to bot/api/models.py if you prefer.

class ArchivedEventSummary(BaseModel):
    event_id: int
    title: str
    event_time: datetime
    archived_at: Optional[datetime] = None

class ChatMessage(BaseModel):
    user_name: str
    avatar_url: Optional[str] = None
    content: str
    timestamp: datetime
    attachment_urls: List[str] = []

class ArchivedEventDetails(BaseModel):
    event_id: int
    title: str
    description: Optional[str] = None
    event_time: datetime
    archived_at: Optional[datetime] = None
    
    # Frozen Snapshots (stored as JSON in DB)
    roster_snapshot: Dict[str, Any] = {}
    transport_snapshot: Dict[str, Any] = {}
    nodes_snapshot: Dict[str, Any] = {}
    white_chats_snapshot: List[Dict[str, Any]] = []

# --- Router Definition ---
router = APIRouter(
    prefix="/api/archive",
    tags=["archive"],
    dependencies=[Depends(auth.get_current_active_user)],
)

logger = logging.getLogger(__name__)

@router.get("/events", response_model=List[ArchivedEventSummary])
async def get_archived_events_list(db: Database = Depends(get_db)):
    """
    Retrieves a list of all past events that have been archived.
    """
    try:
        # You will need to ensure this method exists in your Database class
        return await db.get_archived_events_index()
    except Exception as e:
        logger.error(f"Error fetching archived events index: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch archive index.")

@router.get("/events/{event_id}", response_model=ArchivedEventDetails)
async def get_archived_event_snapshot(event_id: int, db: Database = Depends(get_db)):
    """
    Retrieves the full read-only snapshot of a specific event.
    Includes the final roster, transport plan, and node assignments.
    """
    try:
        # You will need to ensure this method exists in your Database class
        event_data = await db.get_archived_event_details(event_id)
        if not event_data:
            raise HTTPException(status_code=404, detail="Archived event not found.")
        return event_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching details for archived event {event_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch event archive.")

@router.get("/events/{event_id}/chat", response_model=List[ChatMessage])
async def get_archived_event_chat(event_id: int, db: Database = Depends(get_db)):
    """
    Retrieves the preserved Discord chat history for the event.
    """
    try:
        # You will need to ensure this method exists in your Database class
        return await db.get_archived_chat_history(event_id)
    except Exception as e:
        logger.error(f"Error fetching chat history for event {event_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load chat history.")
