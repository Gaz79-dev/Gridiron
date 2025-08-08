from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

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
    model_config = ConfigDict(from_attributes=True)
    event_id: int
    title: str
    event_time: datetime
    end_time: Optional[datetime] = None

class Signup(BaseModel):
    # --- FIX: user_id is now a string to preserve precision ---
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
    # --- FIX: user_id is now a string to preserve precision ---
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
    # This model is now dynamic, so we expect a dictionary
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
    # --- FIX: user_id is now a string to preserve precision ---
    user_id: str
    new_role_name: str

# --- NEW: Squad Template Models ---
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
    template_name: str
    definitions: List[SquadTemplateDefinition]

class SquadTemplateCreate(BaseModel):
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
    is_recurring: bool
    recurrence_rule: Optional[str] = None
    recreation_hours: Optional[int] = None
    mention_role_ids: List[int] = []
    restrict_to_role_ids: List[int] = []
