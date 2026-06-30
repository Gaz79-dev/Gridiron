from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict
from datetime import datetime, date

# --- Token Models ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- User Models ---
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    is_admin: bool = False

class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

class AdminPasswordChange(BaseModel):
    new_password: str = Field(..., min_length=8)

class User(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    is_admin: bool

class UserInDB(User):
    hashed_password: str

# --- Event & Squad Models ---
class Event(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra='ignore')
    event_id: int
    title: str
    description: Optional[str] = None
    event_time: datetime
    end_time: Optional[datetime] = None
    timezone: Optional[str] = None
    channel_id: Optional[int] = None
    game_id: str = "hll"
    template_id: Optional[int] = None
    is_recurring: Optional[bool] = False
    recurrence_rule: Optional[str] = None
    recreation_hours: Optional[int] = None
    mention_role_ids: List[int] = []
    restrict_to_role_ids: List[int] = []

class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    event_time: datetime
    end_time: datetime
    timezone: str = "UTC"
    channel_id: int
    game_id: str = "hll"
    template_id: Optional[int] = None
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None
    recreation_hours: Optional[int] = None
    mention_role_ids: List[int] = []
    restrict_to_role_ids: List[int] = []
    post_to_discord: bool = True

class Signup(BaseModel):
    user_id: str
    display_name: str
    role_name: Optional[str] = "Unassigned"
    subclass_name: Optional[str] = "N/A"
    rsvp_status: str

class Channel(BaseModel):
    id: str
    name: str
    category: Optional[str] = None

class SquadMember(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra='ignore')
    squad_member_id: int
    user_id: str
    assigned_role_name: str
    display_name: Optional[str] = None
    startup_task: Optional[str] = None

class Squad(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    squad_id: int
    name: str
    squad_type: str
    members: List[SquadMember]
    
class EventLockStatus(BaseModel):
    is_locked: bool
    locked_by_user_id: Optional[int] = None
    locked_by_username: Optional[str] = None

class SquadBuildRequest(BaseModel):
    squad_counts: dict[str, int]
    template_id: int

class SendEmbedRequest(BaseModel):
    channel_id: str
    squads: List[Squad]
    mention_accepted: bool = False

class RoleUpdateRequest(BaseModel):
    new_role_name: str
    event_id: int

class SquadMoveRequest(BaseModel):
    new_squad_id: int

class RosterUpdateRequest(BaseModel):
    squads: List[Squad]

class StartupTaskUpdateRequest(BaseModel):
    task: Optional[str] = None

class PromoteRequest(BaseModel):
    user_id: str
    new_role_name: str

class SquadTemplateDefinition(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    definition_id: Optional[int] = None
    squad_name: str
    default_count: int
    squad_type: str
    naming_convention: str
    source_rsvp_pool: str

class SquadTemplate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    template_id: int
    game_id: str = "hll"
    template_name: str
    definitions: List[SquadTemplateDefinition]

class SquadTemplateCreate(BaseModel):
    game_id: str = "hll"
    template_name: str
    definitions: List[SquadTemplateDefinition]

# --- Player Statistics Models ---

class PlayerStats(BaseModel):
    user_id: str
    display_name: str
    accepted_count: int
    tentative_count: int
    declined_count: int
    last_signup_date: Optional[datetime] = None
    days_since_last_signup: Optional[int] = None
    rating: int
    is_active: bool
    role_affinities: Optional[Dict] = None
    game_player_id: Optional[str] = None

class AcceptedEvent(BaseModel):
    event_title: str
    event_time: datetime
    role_name: Optional[str] = None
    subclass_name: Optional[str] = None

class EventUpdate(BaseModel):
    title: str
    description: Optional[str] = None
    event_time: datetime
    end_time: datetime
    timezone: str
    game_id: str = "hll"
    template_id: Optional[int] = None
    is_recurring: bool
    recurrence_rule: Optional[str] = None
    recreation_hours: Optional[int] = None
    mention_role_ids: List[int] = []
    restrict_to_role_ids: List[int] = []

class PlayerRatingUpdate(BaseModel):
    user_id: str
    rating: int = Field(..., ge=0, le=100)

class PlayerAdminInfo(BaseModel):
    """Model for displaying players in the admin rating panel."""
    user_id: str
    display_name: str
    rating: int
    is_active: bool
    game_player_id: Optional[str] = None

class PlayerGameIdUpdate(BaseModel):
    user_id: str
    game_player_id: Optional[str] = None

class MatchUpload(BaseModel):
    event_name: str
    event_date: date
    file_timestamp: str

class LeaderboardPlayer(BaseModel):
    player_name: str
    discord_user_id: Optional[str] = None
    total_value: int

class Leaderboard(BaseModel):
    kills: List[LeaderboardPlayer]
    combat_effectiveness: List[LeaderboardPlayer]
    support_score: List[LeaderboardPlayer]
    offensive_score: List[LeaderboardPlayer]
    defensive_score: List[LeaderboardPlayer]

class SquadReorderRequest(BaseModel):
    ordered_member_ids: List[int]

class PlayerEventHistoryEntry(BaseModel):
    event_title: str
    event_time: datetime
    end_time: Optional[datetime] = None
    rsvp_status: Optional[str] = None
    role_name: Optional[str] = None
    subclass_name: Optional[str] = None

# --- White Chat (Party) Models ---
class WhiteChatMember(BaseModel):
    user_id: str
    display_name: str
    game_player_id: Optional[str] = None

class WhiteChat(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    members: List[WhiteChatMember] = []

class WhiteChatCreateRequest(BaseModel):
    count: int

class WhiteChatMemberRequest(BaseModel):
    user_id: str

# --- Transport Models ---
class TransportEmbedRequest(BaseModel):
    channel_id: str
    # Map of HQ Name (e.g. "HQ1") to list of Squad Names assigned to it
    assignments: Dict[str, List[str]]

class TransportAssignments(BaseModel):
    # Dictionary mapping 'HQ1' -> ['Squad 1', 'Squad 2']
    assignments: Dict[str, List[str]]

class TransportEmbedRequest(BaseModel):
    channel_id: str
    assignments: Dict[str, List[str]]

class TransportAssignments(BaseModel):
    assignments: Dict[str, List[str]]
