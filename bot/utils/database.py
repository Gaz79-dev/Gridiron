import asyncpg
import os
import datetime
import json
import httpx
from typing import List, Optional, Dict, Any
import uuid
from collections import defaultdict

# Static Definitions
ROLES = ["Commander", "Infantry", "Armour", "Recon", "Pathfinders", "Artillery"]
SUBCLASSES = {
    "Infantry": ["Anti-Tank", "Assault", "Automatic Rifleman", "Engineer", "Machine Gunner", "Medic", "Officer", "Rifleman", "Support"],
    "Armour": ["Tank Commander", "Crewman"],
    "Recon": ["Spotter", "Sniper"],
    "Pathfinders": ["Anti-Tank", "Assault", "Automatic Rifleman", "Engineer", "Machine Gunner", "Medic", "Officer", "Rifleman", "Support"],
    "Artillery": ["Anti-Tank", "Assault", "Automatic Rifleman", "Engineer", "Machine Gunner", "Medic", "Officer", "Rifleman", "Support"]
}
RESTRICTED_ROLES = ["Commander", "Recon", "Officer", "Tank Commander", "Pathfinders", "Artillery"]

class RsvpStatus:
    ACCEPTED = "Accepted"
    TENTATIVE = "Tentative"
    DECLINED = "Declined"

# --- FIX START: Helper function to safely convert CSV strings to numbers ---
def _safe_int(value: Any) -> Optional[int]:
    """Safely converts a value to an integer, returning None if conversion fails."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def _safe_float(value: Any) -> Optional[float]:
    """Safely converts a value to a float, returning None if conversion fails."""
    if value is None:
        return None
    try:
        # Remove commas that might be in the string (e.g., "1,234.5")
        if isinstance(value, str):
            value = value.replace(',', '')
        return float(value)
    except (ValueError, TypeError):
        return None
# --- FIX END ---


async def _send_rsvp_log_message(user_id: int, event_title: str, old_status: str, new_status: str):
    """(Helper) Sends a log of an RSVP change to a webhook."""
    webhook_url = os.getenv("RSVP_LOG_WEBHOOK")
    if not webhook_url:
        return

    embed = {
        "title": "RSVP Change Detected",
        "color": 0x00FF00 if new_status == RsvpStatus.ACCEPTED else 0xFF0000,
        "fields": [
            {"name": "Event", "value": event_title, "inline": False},
            {"name": "User", "value": f"<@{user_id}>", "inline": True},
            {"name": "Old Status", "value": old_status or "None", "inline": True},
            {"name": "New Status", "value": new_status, "inline": True}
        ],
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    try:
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json={"embeds": [embed]})
    except Exception as e:
        print(f"Failed to send RSVP log webhook: {e}")

class Database:
    """Handles all database operations."""
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Establishes the database connection pool."""
        try:
            # Create the pool without any custom init function
            # asyncpg handles JSON/JSONB automatically
            self.pool = await asyncpg.create_pool(
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
                database=os.getenv("POSTGRES_DB"),
                host=os.getenv("POSTGRES_HOST"),
                port=os.getenv("POSTGRES_PORT")
            )
            
            # Run setup to create tables
            await self._initial_setup()
            print("Database connection pool established and tables ensured.")
        except Exception as e:
            print(f"Failed to connect to database: {e}")

    async def _initial_setup(self):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS guild_settings (
                        guild_id BIGINT PRIMARY KEY,
                        thread_creation_hours INT DEFAULT 24
                    );
                """)
                
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        event_id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        channel_id BIGINT NOT NULL,
                        message_id BIGINT,
                        thread_id BIGINT,
                        creator_id BIGINT NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        event_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        end_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        timezone VARCHAR(100),
                        is_recurring BOOLEAN DEFAULT FALSE,
                        recurrence_rule VARCHAR(50), -- e.g., 'daily', 'weekly', 'monthly'
                        recreation_hours INT DEFAULT 168, -- Default to 1 week
                        parent_event_id INT REFERENCES events(event_id) ON DELETE SET NULL,
                        mention_role_ids BIGINT[],
                        restrict_to_role_ids BIGINT[],
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
                        is_deleted BOOLEAN DEFAULT FALSE,
                        deleted_at TIMESTAMP WITH TIME ZONE,
                        thread_created BOOLEAN DEFAULT FALSE,
                        update_embed BOOLEAN DEFAULT FALSE
                    );
                """)
                
                # These ALTER TABLE commands are still needed to patch the schema
                await connection.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;")
                await connection.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE;")

                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS signups (
                        signup_id SERIAL PRIMARY KEY,
                        event_id INT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
                        user_id BIGINT NOT NULL,
                        rsvp_status VARCHAR(10) NOT NULL, -- Accepted, Declined, Tentative
                        role_name VARCHAR(100), -- Infantry, Armour, Recon
                        subclass_name VARCHAR(100), -- Officer, Medic, etc.
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
                        UNIQUE(event_id, user_id)
                    );
                """)

                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        hashed_password VARCHAR(255) NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        is_admin BOOLEAN DEFAULT FALSE
                    );
                """)

                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS player_stats (
                        user_id BIGINT PRIMARY KEY,
                        accepted_count INT DEFAULT 0,
                        tentative_count INT DEFAULT 0,
                        declined_count INT DEFAULT 0,
                        last_signup_date TIMESTAMP WITH TIME ZONE,
                        rating INT DEFAULT 50,
                        role_affinities JSONB,
                        is_active BOOLEAN DEFAULT TRUE
                    );
                """)
                await connection.execute("ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS display_name VARCHAR(255);")

                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS player_event_history (
                        history_id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        event_id INT NOT NULL,
                        event_title VARCHAR(255) NOT NULL,
                        event_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        role_name VARCHAR(100),
                        subclass_name VARCHAR(100),
                        UNIQUE(user_id, event_id)
                    );
                """)
                await connection.execute("ALTER TABLE player_event_history ADD COLUMN IF NOT EXISTS end_time TIMESTAMP WITH TIME ZONE;")
                await connection.execute("ALTER TABLE player_event_history ADD COLUMN IF NOT EXISTS rsvp_status VARCHAR(10);")
                
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS reminder_jobs (
                        job_id VARCHAR(255) PRIMARY KEY,
                        event_id INT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
                        user_id BIGINT NOT NULL,
                        reminder_time TIMESTAMP WITH TIME ZONE NOT NULL
                    );
                """)
                
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS squad_templates (
                        template_id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        template_name VARCHAR(255) NOT NULL
                    );
                """)

                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS squad_template_definitions (
                        definition_id SERIAL PRIMARY KEY,
                        template_id INT NOT NULL REFERENCES squad_templates(template_id) ON DELETE CASCADE,
                        squad_name VARCHAR(255) NOT NULL,
                        default_count INT DEFAULT 0,
                        squad_type VARCHAR(100) NOT NULL,
                        naming_convention VARCHAR(50) NOT NULL DEFAULT 'numeric',
                        source_rsvp_pool VARCHAR(100) NOT NULL
                    );
                """)
                
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS squads (
                        squad_id SERIAL PRIMARY KEY,
                        event_id INT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
                        name VARCHAR(255) NOT NULL,
                        squad_type VARCHAR(100) NOT NULL
                    );
                """)

                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS squad_members (
                        squad_member_id SERIAL PRIMARY KEY,
                        squad_id INT NOT NULL REFERENCES squads(squad_id) ON DELETE CASCADE,
                        user_id BIGINT NOT NULL,
                        assigned_role_name VARCHAR(100),
                        position INT DEFAULT 0,
                        startup_task TEXT
                    );
                """)
                
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS event_final_rosters (
                        roster_id SERIAL PRIMARY KEY,
                        event_id INT NOT NULL UNIQUE REFERENCES events(event_id) ON DELETE CASCADE,
                        roster_data JSONB NOT NULL,
                        finalized_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    );
                """)
                
                await connection.execute("ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS game_player_id VARCHAR(100);")

                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS match_uploads (
                        match_id VARCHAR(255) PRIMARY KEY, -- e.g., '20240520_MatchName_123456'
                        event_name VARCHAR(255) NOT NULL,
                        event_date DATE NOT NULL,
                        uploaded_by_user_id INT NOT NULL REFERENCES users(id),
                        uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    );
                """)

                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS match_history (
                        match_stat_id SERIAL PRIMARY KEY,
                        match_id VARCHAR(255) NOT NULL REFERENCES match_uploads(match_id) ON DELETE CASCADE,
                        player_name VARCHAR(255) NOT NULL,
                        game_player_id VARCHAR(100) NOT NULL,
                        discord_user_id BIGINT REFERENCES player_stats(user_id), -- Linked via game_player_id
                        kills INT,
                        deaths INT,
                        combat_effectiveness INT,
                        offensive_score INT,
                        defensive_score INT,
                        support_score INT
                    );
                """)
                await connection.execute("CREATE INDEX IF NOT EXISTS idx_match_history_game_player_id ON match_history(game_player_id);")

                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS event_locks (
                        event_id INT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
                        locked_by_user_id INT NOT NULL REFERENCES users(id),
                        locked_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    );
                """)

    # --- Guild Settings ---
    async def set_thread_creation_hours(self, guild_id: int, hours: int):
        query = """
            INSERT INTO guild_settings (guild_id, thread_creation_hours)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET thread_creation_hours = $2;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, guild_id, hours)

    async def get_thread_creation_hours(self, guild_id: int) -> int:
        query = "SELECT thread_creation_hours FROM guild_settings WHERE guild_id = $1;"
        async with self.pool.acquire() as connection:
            hours = await connection.fetchval(query, guild_id)
            return hours if hours is not None else 24

    # --- Event Management ---
    async def create_event(self, guild_id: int, channel_id: int, creator_id: int, event_data: dict) -> int:
        query = """
            INSERT INTO events (
                guild_id, channel_id, creator_id, title, description, event_time, 
                end_time, timezone, is_recurring, recurrence_rule, 
                recreation_hours, parent_event_id, mention_role_ids, restrict_to_role_ids
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING event_id;
        """
        async with self.pool.acquire() as connection:
            event_id = await connection.fetchval(
                query,
                guild_id, channel_id, creator_id,
                event_data['title'], event_data['description'], event_data['event_time'],
                event_data['end_time'], event_data['timezone'], event_data['is_recurring'],
                event_data.get('recurrence_rule'), event_data.get('recreation_hours'),
                event_data.get('parent_event_id'), event_data.get('mention_role_ids', []),
                event_data.get('restrict_to_role_ids', [])
            )
            return event_id

    async def get_event_by_id(self, event_id: int, include_deleted: bool = False) -> Optional[Dict]:
        query = "SELECT * FROM events WHERE event_id = $1"
        if not include_deleted:
            query += " AND is_deleted = FALSE"
        async with self.pool.acquire() as connection:
            record = await connection.fetchrow(query, event_id)
            return dict(record) if record else None

    async def get_active_events_with_message_id(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE message_id IS NOT NULL AND is_deleted = FALSE AND end_time > (NOW() AT TIME ZONE 'utc');"
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query)
            return [dict(record) for record in records]
            
    async def get_active_events_with_threads(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE thread_id IS NOT NULL AND is_deleted = FALSE AND end_time > (NOW() AT TIME ZONE 'utc');"
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query)
            return [dict(record) for record in records]

    async def get_events_for_thread_creation(self) -> List[Dict]:
        query = """
            SELECT e.*
            FROM events e
            JOIN guild_settings gs ON e.guild_id = gs.guild_id
            WHERE e.is_deleted = FALSE
              AND e.thread_created = FALSE
              AND (e.event_time - (gs.thread_creation_hours * INTERVAL '1 hour')) <= (NOW() AT TIME ZONE 'utc')
              AND e.end_time > (NOW() AT TIME ZONE 'utc');
        """
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query)
            return [dict(record) for record in records]

    async def get_events_for_recreation(self) -> List[Dict]:
        query = """
            SELECT * FROM events
            WHERE is_recurring = TRUE 
              AND is_deleted = FALSE
              AND (end_time + INTERVAL '1 hour') <= (NOW() AT TIME ZONE 'utc');
        """
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query)
            return [dict(record) for record in records]
            
    async def get_latest_child_event(self, parent_event_id: int) -> Optional[Dict]:
        query = "SELECT * FROM events WHERE parent_event_id = $1 ORDER BY event_time DESC LIMIT 1;"
        async with self.pool.acquire() as connection:
            record = await connection.fetchrow(query, parent_event_id)
            return dict(record) if record else None

    async def get_finished_events_for_cleanup(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE end_time < (NOW() AT TIME ZONE 'utc') - INTERVAL '2 hours' AND is_recurring = FALSE AND is_deleted = FALSE;"
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query)
            return [dict(record) for record in records]

    async def get_past_events_with_tentatives(self) -> List[Dict]:
        query = """
            SELECT s.*
            FROM signups s
            JOIN events e ON s.event_id = e.event_id
            WHERE e.end_time < (NOW() AT TIME ZONE 'utc')
              AND s.rsvp_status = $1;
        """
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query, RsvpStatus.TENTATIVE)
            return [dict(record) for record in records]

    async def get_events_for_purging(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE is_deleted = TRUE AND deleted_at < (NOW() AT TIME ZONE 'utc') - INTERVAL '7 days';"
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query)
            return [dict(record) for record in records]

    async def get_recurring_parent_events(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE is_recurring = TRUE AND is_deleted = FALSE ORDER BY event_time ASC;"
        async with self.pool.acquire() as connection:
            return [dict(record) for record in await connection.fetch(query)]

    async def get_deleted_events(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE is_deleted = TRUE ORDER BY deleted_at DESC LIMIT 50;"
        async with self.pool.acquire() as connection:
            return [dict(record) for record in await connection.fetch(query)]
            
    async def get_events_for_embed_update(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE update_embed = TRUE AND is_deleted = FALSE;"
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query)
            return [dict(record) for record in records]

    async def flag_event_for_embed_update(self, event_id: int):
        query = "UPDATE events SET update_embed = TRUE WHERE event_id = $1;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, event_id)

    async def clear_embed_update_flag(self, event_id: int):
        query = "UPDATE events SET update_embed = FALSE WHERE event_id = $1;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, event_id)

    async def update_event_message_id(self, event_id: int, message_id: int):
        query = "UPDATE events SET message_id = $1 WHERE event_id = $2;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, message_id, event_id)

    async def mark_thread_created(self, event_id: int, thread_id: int):
        query = "UPDATE events SET thread_created = TRUE, thread_id = $1 WHERE event_id = $2;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, thread_id, event_id)

    async def soft_delete_event(self, event_id: int):
        query = "UPDATE events SET is_deleted = TRUE, deleted_at = (NOW() AT TIME ZONE 'utc') WHERE event_id = $1;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, event_id)
            
    async def delete_event(self, event_id: int):
        query = "DELETE FROM events WHERE event_id = $1;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, event_id)
            
    async def update_event(self, event_id: int, event_data: dict):
        query = """
            UPDATE events SET
                title = $1, description = $2, event_time = $3, end_time = $4,
                timezone = $5, is_recurring = $6, recurrence_rule = $7,
                recreation_hours = $8, mention_role_ids = $9, restrict_to_role_ids = $10,
                is_deleted = FALSE, deleted_at = NULL
            WHERE event_id = $11;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(
                query,
                event_data['title'], event_data['description'], event_data['event_time'],
                event_data['end_time'], event_data['timezone'], event_data['is_recurring'],
                event_data.get('recurrence_rule'), event_data.get('recreation_hours'),
                event_data.get('mention_role_ids', []), event_data.get('restrict_to_role_ids', []),
                event_id
            )
            
    # --- Signup Management ---
    async def get_signup(self, event_id: int, user_id: int) -> Optional[Dict]:
        query = "SELECT * FROM signups WHERE event_id = $1 AND user_id = $2;"
        async with self.pool.acquire() as connection:
            record = await connection.fetchrow(query, event_id, user_id)
            return dict(record) if record else None

    async def get_signups_for_event(self, event_id: int) -> List[Dict]:
        query = "SELECT * FROM signups WHERE event_id = $1;"
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query, event_id)
            return [dict(record) for record in records]
            
    async def get_signups_for_roster_page(self, event_id: int) -> List[Dict]:
        query = """
            SELECT 
                s.user_id::text, 
                COALESCE(ps.display_name, s.user_id::text) AS display_name,
                s.role_name, 
                s.subclass_name, 
                s.rsvp_status,
                ps.rating,
                ps.role_affinities
            FROM signups s
            LEFT JOIN player_stats ps ON s.user_id = ps.user_id
            WHERE s.event_id = $1
            ORDER BY
                CASE s.rsvp_status
                    WHEN 'Accepted' THEN 1
                    WHEN 'Tentative' THEN 2
                    WHEN 'Declined' THEN 3
                    ELSE 4
                END,
                ps.display_name;
        """
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query, event_id)
            return [dict(record) for record in records]

    async def get_signup_counts(self, event_id: int) -> Dict[str, int]:
        query = "SELECT rsvp_status, COUNT(*) FROM signups WHERE event_id = $1 GROUP BY rsvp_status;"
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query, event_id)
            return {r['rsvp_status']: r['count'] for r in records}
            
    async def get_all_roles_and_subclasses(self) -> Dict[str, List[str]]:
        return {"roles": ROLES, "subclasses": SUBCLASSES}

    async def set_rsvp(self, event_id: int, user_id: int, new_status: str):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                event_and_signup_data = await connection.fetchrow(
                    """
                    SELECT e.title, e.event_time, e.end_time, s.rsvp_status, s.role_name, s.subclass_name
                    FROM events e
                    LEFT JOIN signups s ON e.event_id = s.event_id AND s.user_id = $2
                    WHERE e.event_id = $1;
                    """,
                    event_id, user_id
                )
                
                if not event_and_signup_data:
                    return # Event doesn't exist

                old_status = event_and_signup_data['rsvp_status']

                if old_status == new_status:
                    return # No change

                await connection.execute(
                    """
                    INSERT INTO signups (event_id, user_id, rsvp_status, timestamp)
                    VALUES ($1, $2, $3, (NOW() AT TIME ZONE 'utc'))
                    ON CONFLICT (event_id, user_id) DO UPDATE SET
                        rsvp_status = $3,
                        timestamp = (NOW() AT TIME ZONE 'utc');
                    """,
                    event_id, user_id, new_status
                )

                await self.update_player_stats(user_id, old_status, new_status)

                is_log_worthy = old_status is not None and (
                    old_status != new_status or
                    new_status == RsvpStatus.ACCEPTED or
                    new_status == RsvpStatus.DECLINED
                )

                if is_log_worthy:
                    await _send_rsvp_log_message(
                        user_id=user_id,
                        event_title=event_and_signup_data['title'],
                        old_status=old_status,
                        new_status=new_status
                    )

                # --- START: MODIFICATION - Overhaul event history snapshot logic ---
                # We only snapshot the RSVP status if the event has not started yet.
                # This fulfills Requirement #4.
                if event_and_signup_data['event_time'] > datetime.datetime.now(datetime.timezone.utc):
                    if new_status in [RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED]:
                        # Insert or update the player's RSVP status for this event
                        await connection.execute(
                            """
                            INSERT INTO player_event_history (user_id, event_id, event_title, event_time, end_time, role_name, subclass_name, rsvp_status)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (user_id, event_id) DO UPDATE SET
                                rsvp_status = EXCLUDED.rsvp_status,
                                role_name = EXCLUDED.role_name,
                                subclass_name = EXCLUDED.subclass_name,
                                event_title = EXCLUDED.event_title,
                                event_time = EXCLUDED.event_time,
                                end_time = EXCLUDED.end_time;
                            """,
                            user_id,
                            event_id,
                            event_and_signup_data['title'],
                            event_and_signup_data['event_time'],
                            event_and_signup_data['end_time'],
                            event_and_signup_data['role_name'],
                            event_and_signup_data['subclass_name'],
                            new_status
                        )
                    elif old_status in [RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED]:
                        # If they are un-RSVP'ing (e.g. going from Accepted to nothing), remove their history entry
                        await connection.execute(
                            "DELETE FROM player_event_history WHERE user_id = $1 AND event_id = $2;",
                            user_id, event_id
                        )
                # --- END: MODIFICATION ---

                await self.flag_event_for_embed_update(event_id)

    async def get_upcoming_events(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE end_time > (NOW() AT TIME ZONE 'utc') AND is_deleted = FALSE ORDER BY event_time ASC;"
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query)
            return [dict(record) for record in records]

    async def update_signup_role(self, event_id: int, user_id: int, role: str, subclass: Optional[str]):
        query = """
            UPDATE signups
            SET role_name = $1, subclass_name = $2
            WHERE event_id = $3 AND user_id = $4;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, role, subclass, event_id, user_id)
            # --- START: MODIFICATION - Update history snapshot ---
            # Also update the history table if the event hasn't started
            event_time = await connection.fetchval("SELECT event_time FROM events WHERE event_id = $1", event_id)
            if event_time and event_time > datetime.datetime.now(datetime.timezone.utc):
                await connection.execute(
                    """
                    UPDATE player_event_history
                    SET role_name = $1, subclass_name = $2
                    WHERE event_id = $3 AND user_id = $4;
                    """,
                    role, subclass, event_id, user_id
                )
            # --- END: MODIFICATION ---
            await self.flag_event_for_embed_update(event_id)

    async def promote_tentative_player(self, event_id: int, user_id: int, role: str, subclass: Optional[str]):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                signup = await self.get_signup(event_id, user_id)
                if not signup: return

                old_status = signup['rsvp_status']
                if old_status == RsvpStatus.TENTATIVE:
                    await self.set_rsvp(event_id, user_id, RsvpStatus.ACCEPTED)
                    await self.update_signup_role(event_id, user_id, role, subclass)

    async def remove_user_from_all_upcoming_signups(self, user_id: int):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                # Get all upcoming events the user is signed up for
                upcoming_signups = await connection.fetch(
                    """
                    SELECT s.event_id
                    FROM signups s
                    JOIN events e ON s.event_id = e.event_id
                    WHERE s.user_id = $1 AND e.end_time > (NOW() AT TIME ZONE 'utc')
                    """,
                    user_id
                                # Delete the signups
            await connection.execute(
                """
                DELETE FROM signups s
                USING events e
                WHERE s.event_id = e.event_id
                  AND s.user_id = $1 AND e.end_time > (NOW() AT TIME ZONE 'utc');
                """,
                user_id
            )
            
            # Flag all affected events for an embed update
            for signup in upcoming_signups:
                await self.flag_event_for_embed_update(signup['event_id'])
                
async def get_all_rsvpd_user_ids_for_event(self, event_id: int) -> List[int]:
    query = "SELECT user_id FROM signups WHERE event_id = $1;"
    async with self.pool.acquire() as connection:
        records = await connection.fetch(query, event_id)
        return [r['user_id'] for r in records]

# --- User Management ---
async def get_user_by_username(self, username: str) -> Optional[Dict]:
    query = "SELECT * FROM users WHERE username = $1;"
    async with self.pool.acquire() as connection:
        record = await connection.fetchrow(query, username)
        return dict(record) if record else None

async def get_user_by_id(self, user_id: int) -> Optional[Dict]:
    query = "SELECT * FROM users WHERE id = $1;"
    async with self.pool.acquire() as connection:
        record = await connection.fetchrow(query, user_id)
        return dict(record) if record else None
        
async def get_all_users(self) -> List[Dict]:
    query = "SELECT id, username, is_active, is_admin FROM users ORDER BY username;"
    async with self.pool.acquire() as connection:
        records = await connection.fetch(query)
        return [dict(record) for record in records]

async def create_user(self, username: str, hashed_password: str, is_admin: bool = False) -> int:
    query = "INSERT INTO users (username, hashed_password, is_admin) VALUES ($1, $2, $3) RETURNING id;"
    async with self.pool.acquire() as connection:
        user_id = await connection.fetchval(query, username, hashed_password, is_admin)
        return user_id

async def update_user_password(self, user_id: int, new_hashed_password: str):
    query = "UPDATE users SET hashed_password = $1 WHERE id = $2;"
    async with self.pool.acquire() as connection:
        await connection.execute(query, new_hashed_password, user_id)

async def update_user_status(self, user_id: int, is_active: Optional[bool], is_admin: Optional[bool]):
    updates = []
    params = [user_id]
    
    if is_active is not None:
        params.append(is_active)
        updates.append(f"is_active = ${len(params)}")
    if is_admin is not None:
        params.append(is_admin)
        updates.append(f"is_admin = ${len(params)}")
        
    if not updates: return
    
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = $1;"
    async with self.pool.acquire() as connection:
        await connection.execute(query, *params)
        
async def delete_user(self, user_id: int):
    query = "DELETE FROM users WHERE id = $1;"
    async with self.pool.acquire() as connection:
        await connection.execute(query, user_id)

# --- Player Stats & History ---
async def get_engagement_stats(self) -> List[Dict]:
    """
    Calculates engagement stats by aggregating raw signup data and joining it
    to the full list of active players.
    """
    # --- START: MODIFICATION - Read directly from player_stats ---
    # This query no longer calculates from the 'signups' table.
    # It reads the persistent running totals directly from 'player_stats'.
    query = """
        SELECT
            ps.user_id::text AS user_id,
            ps.display_name,
            ps.rating,
            ps.is_active,
            ps.last_signup_date,
            ps.role_affinities,
            ps.game_player_id,
            COALESCE(ps.accepted_count, 0) AS accepted_count,
            COALESCE(ps.tentative_count, 0) AS tentative_count,
            COALESCE(ps.declined_count, 0) AS declined_count,
            CASE
                WHEN ps.last_signup_date IS NOT NULL
                THEN EXTRACT(DAY FROM (NOW() AT TIME ZONE 'utc' - ps.last_signup_date))
                ELSE NULL
            END AS days_since_last_signup
        FROM
            player_stats ps
        WHERE
            ps.is_active = TRUE
        ORDER BY
            ps.display_name;
    """
    # --- END: MODIFICATION ---
    async with self.pool.acquire() as connection:
        records = await connection.fetch(query)
        return [dict(record) for record in records]

async def update_player_stats(self, user_id: int, old_status: Optional[str], new_status: str):
    accepted_delta = 0
    tentative_delta = 0
    declined_delta = 0

    # Calculate deltas for counters
    if new_status == RsvpStatus.ACCEPTED: accepted_delta += 1
    elif new_status == RsvpStatus.TENTATIVE: tentative_delta += 1
    elif new_status == RsvpStatus.DECLINED: declined_delta += 1

    if old_status == RsvpStatus.ACCEPTED: accepted_delta -= 1
    elif old_status == RsvpStatus.TENTATIVE: tentative_delta -= 1
    elif old_status == RsvpStatus.DECLINED: declined_delta -= 1

    last_signup_date_val = None
    # --- START: MODIFICATION - Update last_signup_date for any valid RSVP ---
    if new_status in [RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED]:
        last_signup_date_val = datetime.datetime.now(datetime.timezone.utc)
    # --- END: MODIFICATION ---

    query = """
        INSERT INTO player_stats (user_id, accepted_count, tentative_count, declined_count, last_signup_date)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id) DO UPDATE SET
            accepted_count = player_stats.accepted_count + $2,
            tentative_count = player_stats.tentative_count + $3,
            declined_count = player_stats.declined_count + $4,
            last_signup_date = COALESCE($5, player_stats.last_signup_date);
    """
    async with self.pool.acquire() as connection:
        await connection.execute(
            query,
            user_id,
            accepted_delta,
            tentative_delta,
            declined_delta,
            last_signup_date_val
        )

# --- START: MODIFICATION - Rename function and update query ---
async def get_event_history_for_user(self, user_id: int) -> List[Dict]:
    """
    Retrieves all event history for a specific player from the persistent snapshot table.
    """
    query = """
        SELECT event_title, event_time, end_time, rsvp_status, role_name, subclass_name
        FROM player_event_history
        WHERE user_id = $1 ORDER BY event_time DESC;
    """
    async with self.pool.acquire() as connection:
        return [dict(row) for row in await connection.fetch(query, user_id)]
# --- END: MODIFICATION ---

async def get_all_players_for_admin_panel(self) -> List[Dict]:
    """Gets a simple list of all players, active or inactive."""
    query = "SELECT user_id, display_name, rating, is_active, game_player_id FROM player_stats ORDER BY display_name;"
    async with self.pool.acquire() as connection:
        return [dict(row) for row in await connection.fetch(query)]

async def add_or_update_server_member(self, user_id: int):
    query = """
        INSERT INTO player_stats (user_id, is_active)
        VALUES ($1, TRUE)
        ON CONFLICT (user_id) DO UPDATE SET
            is_active = TRUE;
    """
    async with self.pool.acquire() as connection:
        await connection.execute(query, user_id)
        
async def deactivate_server_member(self, user_id: int):
    query = "UPDATE player_stats SET is_active = FALSE WHERE user_id = $1;"
    async with self.pool.acquire() as connection:
        await connection.execute(query, user_id)
        
async def sync_all_server_members(self, member_ids: List[int]):
    query = """
        INSERT INTO player_stats (user_id)
        SELECT unnest($1::bigint[])
        ON CONFLICT (user_id) DO NOTHING;
    """
    async with self.pool.acquire() as connection:
        await connection.execute(query, member_ids)

async def update_member_active_status(self, user_ids: List[int], is_active: bool):
    query = "UPDATE player_stats SET is_active = $1 WHERE user_id = ANY($2);"
    async with self.pool.acquire() as connection:
        await connection.execute(query, is_active, user_ids)
        
async def cache_player_display_names(self, member_data: List[Dict]):
    """
    Updates the display_name for multiple players at once using
    an INSERT... ON CONFLICT batch operation.
    """
    query = """
        INSERT INTO player_stats (user_id, display_name)
        SELECT (d->>'id')::bigint, d->>'name'
        FROM unnest($1::jsonb[]) AS t(d)
        ON CONFLICT (user_id) DO UPDATE SET
            display_name = EXCLUDED.display_name;
    """
    async with self.pool.acquire() as connection:
        # asyncpg will handle the JSONB array automatically
        await connection.execute(query, member_data)

async def update_player_rating(self, user_id: int, rating: int):
    query = "UPDATE player_stats SET rating = $1 WHERE user_id = $2;"
    async with self.pool.acquire() as connection:
        await connection.execute(query, rating, user_id)

async def update_player_game_id(self, user_id: int, game_player_id: Optional[str]):
    query = "UPDATE player_stats SET game_player_id = $1 WHERE user_id = $2;"
    async with self.pool.acquire() as connection:
        await connection.execute(query, game_player_id, user_id)

async def update_player_affinities(self, squads: List[Dict]):
    """
    Updates the role_affinities for all players in a list of finalized squads.
    This is a complex operation that reads, updates, and writes JSONB data.
    """
    async with self.pool.acquire() as connection:
        async with connection.transaction():
            all_member_ids = [int(m['user_id']) for s in squads for m in s['members']]
            if not all_member_ids: return

            # Step 1: Get existing affinities for all involved players
            existing_data = await connection.fetch("SELECT user_id, role_affinities FROM player_stats WHERE user_id = ANY($1);", all_member_ids)
            player_affinities = {}
            for row in existing_data:
                # asyncpg automatically decodes JSONB to Python dict
                player_affinities[row['user_id']] = row['role_affinities'] or {'roles': {}, 'squad_types': {}}
            
            # Step 2: Update affinities in memory
            for squad in squads:
                squad_type = squad['squad_type']
                if squad_type == "Reserves": continue # Do not track reserves
                
                for member in squad['members']:
                    user_id = int(member['user_id'])
                    role = member['assigned_role_name']
                    
                    if user_id not in player_affinities:
                        player_affinities[user_id] = {'roles': {}, 'squad_types': {}}
                    
                    aff = player_affinities[user_id]
                    aff['roles'][role] = aff['roles'].get(role, 0) + 1
                    aff['squad_types'][squad_type] = aff['squad_types'].get(squad_type, 0) + 1
            
            # Step 3: Batch update back to the database
            update_data = [(user_id, aff) for user_id, aff in player_affinities.items()]
            await connection.executemany(
                "UPDATE player_stats SET role_affinities = $2 WHERE user_id = $1;",
                update_data
            )

# --- Squad Template Management ---
async def create_squad_template(self, guild_id: int, template_name: str, definitions: List[Any]) -> int:
    async with self.pool.acquire() as connection:
        async with connection.transaction():
            template_id = await connection.fetchval(
                "INSERT INTO squad_templates (guild_id, template_name) VALUES ($1, $2) RETURNING template_id;",
                guild_id, template_name
            )
            
            def_data = [(
                template_id, d.squad_name, d.default_count, d.squad_type, 
                d.naming_convention, d.source_rsvp_pool
            ) for d in definitions]
            
            await connection.copy_records_to_table(
                'squad_template_definitions',
                records=def_data,
                columns=[
                    'template_id', 'squad_name', 'default_count', 'squad_type', 
                    'naming_convention', 'source_rsvp_pool'
                ]
            )
            return template_id

async def get_all_squad_templates(self) -> List[Dict]:
    query = """
        SELECT t.template_id, t.template_name, json_agg(
            json_build_object(
                'definition_id', d.definition_id,
                'squad_name', d.squad_name,
                'default_count', d.default_count,
                'squad_type', d.squad_type,
                'naming_convention', d.naming_convention,
                'source_rsvp_pool', d.source_rsvp_pool
            ) ORDER BY d.definition_id
        ) as definitions
        FROM squad_templates t
        LEFT JOIN squad_template_definitions d ON t.template_id = d.template_id
        GROUP BY t.template_id
        ORDER BY t.template_name;
    """
    async with self.pool.acquire() as connection:
        # asyncpg will automatically parse the json_agg
        return [dict(row) for row in await connection.fetch(query)]

async def get_squad_template_by_id(self, template_id: int) -> Optional[Dict]:
    query = """
        SELECT t.template_id, t.template_name, json_agg(
            json_build_object(
                'definition_id', d.definition_id,
                'squad_name', d.squad_name,
                'default_count', d.default_count,
                'squad_type', d.squad_type,
                'naming_convention', d.naming_convention,
                'source_rsvp_pool', d.source_rsvp_pool
            ) ORDER BY d.definition_id
        ) as definitions
        FROM squad_templates t
        LEFT JOIN squad_template_definitions d ON t.template_id = d.template_id
        WHERE t.template_id = $1
        GROUP BY t.template_id;
    """
    async with self.pool.acquire() as connection:
        row = await connection.fetchrow(query, template_id)
        return dict(row) if row else None

async def update_squad_template(self, template_id: int, template_name: str, definitions: List[Any]):
    async with self.pool.acquire() as connection:
        async with connection.transaction():
            # Update the template name
            await connection.execute(
                "UPDATE squad_templates SET template_name = $1 WHERE template_id = $2;",
                template_name, template_id
            )
            # Delete old definitions
            await connection.execute(
                "DELETE FROM squad_template_definitions WHERE template_id = $1;",
                template_id
            )
            # Insert new definitions
            def_data = [(
                template_id, d.squad_name, d.default_count, d.squad_type, 
                d.naming_convention, d.source_rsvp_pool
            ) for d in definitions]
            
            await connection.copy_records_to_table(
                'squad_template_definitions',
                records=def_data,
                columns=[
                    'template_id', 'squad_name', 'default_count', 'squad_type', 
                    'naming_convention', 'source_rsvp_pool'
                ]
            )

async def delete_squad_template(self, template_id: int):
    async with self.pool.acquire() as connection:
        await connection.execute("DELETE FROM squad_templates WHERE template_id = $1;", template_id)

# --- Squad & Roster Management ---
async def create_squad(self, event_id: int, name: str, squad_type: str) -> int:
    query = "INSERT INTO squads (event_id, name, squad_type) VALUES ($1, $2, $3) RETURNING squad_id;"
    async with self.pool.acquire() as connection:
        return await connection.fetchval(query, event_id, name, squad_type)

async def get_squad_by_name(self, event_id: int, name: str) -> Optional[Dict]:
    query = "SELECT * FROM squads WHERE event_id = $1 AND name = $2;"
    async with self.pool.acquire() as connection:
        row = await connection.fetchrow(query, event_id, name)
        return dict(row) if row else None

async def add_squad_member(self, squad_id: int, user_id: int, role_name: str):
    query = "INSERT INTO squad_members (squad_id, user_id, assigned_role_name) VALUES ($1, $2, $3);"
    async with self.pool.acquire() as connection:
        await connection.execute(query, squad_id, user_id, role_name)
        
async def get_squad_member_details(self, squad_member_id: int) -> Optional[Dict]:
    query = "SELECT s.event_id, sm.user_id FROM squad_members sm JOIN squads s ON sm.squad_id = s.squad_id WHERE sm.squad_member_id = $1;"
    async with self.pool.acquire() as connection:
        row = await connection.fetchrow(query, squad_member_id)
        return dict(row) if row else None

async def update_squad_member_role(self, squad_member_id: int, role_name: str):
    query = "UPDATE squad_members SET assigned_role_name = $1 WHERE squad_member_id = $2;"
    async with self.pool.acquire() as connection:
        await connection.execute(query, role_name, squad_member_id)

async def update_squad_member_order(self, squad_id: int, ordered_member_ids: List[int]):
    query = """
        UPDATE squad_members sm
        SET position = new_positions.position
        FROM (SELECT unnest($1::int[]) AS member_id, generate_series(1, array_length($1, 1)) AS position) AS new_positions
        WHERE sm.squad_id = $2 AND sm.squad_member_id = new_positions.member_id;
    """
    async with self.pool.acquire() as connection:
        await connection.execute(query, ordered_member_ids, squad_id)
        
async def move_squad_member(self, squad_member_id: int, new_squad_id: int):
    query = "UPDATE squad_members SET squad_id = $1, position = 0 WHERE squad_member_id = $2;"
    async with self.pool.acquire() as connection:
        await connection.execute(query, new_squad_id, squad_member_id)

async def remove_user_from_all_squads(self, event_id: int, user_id: int):
    query = """
        DELETE FROM squad_members sm
        USING squads s
        WHERE sm.squad_id = s.squad_id
          AND s.event_id = $1 AND sm.user_id = $2;
    """
    async with self.pool.acquire() as connection:
        await connection.execute(query, event_id, user_id)
        
async def update_squad_member_task(self, squad_member_id: int, task: Optional[str]):
    query = "UPDATE squad_members SET startup_task = $1 WHERE squad_member_id = $2;"
    async with self.pool.acquire() as connection:
        await connection.execute(query, task, squad_member_id)
        
async def save_finalized_roster(self, event_id: int, roster_data: List[Dict]):
    query = """
        INSERT INTO event_final_rosters (event_id, roster_data)
        VALUES ($1, $2)
        ON CONFLICT (event_id) DO UPDATE SET
            roster_data = EXCLUDED.roster_data,
            finalized_at = (NOW() AT TIME ZONE 'utc');
    """
    async with self.pool.acquire() as connection:
        # asyncpg will handle the List[Dict] to JSONB conversion automatically
        await connection.execute(query, event_id, roster_data)

# --- Match Stats Management ---
async def check_match_exists(self, match_id: str) -> bool:
    query = "SELECT 1 FROM match_uploads WHERE match_id = $1;"
    async with self.pool.acquire() as connection:
        return await connection.fetchval(query, match_id) is not None

async def insert_match_data(self, match_id: str, event_name: str, event_date: datetime.date, uploaded_by_user_id: int, match_stats: List[Dict]):
    async with self.pool.acquire() as connection:
        async with connection.transaction():
            # Step 1: Create the parent match record
            await connection.execute(
                """
                INSERT INTO match_uploads (match_id, event_name, event_date, uploaded_by_user_id)
                VALUES ($1, $2, $3, $4);
                """,
                match_id, event_name, event_date, uploaded_by_user_id
            )

            # Step 2: Get all known game_player_ids from player_stats
            player_id_map_rows = await connection.fetch("SELECT game_player_id, user_id FROM player_stats WHERE game_player_id IS NOT NULL;")
            player_id_map = {row['game_player_id']: row['user_id'] for row in player_id_map_rows}

            # Step 3: Prepare the match history records
            records_to_insert = []
            for row in match_stats:
                game_player_id = row.get('PlayerID')
                if not game_player_id: continue # Skip rows without a PlayerID
                
                discord_user_id = player_id_map.get(game_player_id)
                
                records_to_insert.append((
                    match_id,
                    row.get('PlayerName', 'Unknown'),
                    game_player_id,
                    discord_user_id,
                    _safe_int(row.get('Kills')),
                    _safe_int(row.get('Deaths')),
                    _safe_int(row.get('CombatEffectiveness')),
                    _safe_int(row.get('OffensiveScore')),
                    _safe_int(row.get('DefensiveScore')),
                    _safe_int(row.get('SupportScore'))
                ))

            # Step 4: Batch insert all records
            await connection.copy_records_to_table(
                'match_history',
                records=records_to_insert,
                columns=[
                    'match_id', 'player_name', 'game_player_id', 'discord_user_id',
                    'kills', 'deaths', 'combat_effectiveness', 'offensive_score',
                    'defensive_score', 'support_score'
                ]
            )

async def calculate_leaderboards(self) -> Dict[str, List[Dict]]:
    # Define the metrics we want to sum
    metrics = ["kills", "combat_effectiveness", "support_score", "offensive_score", "defensive_score"]
    leaderboards = {}

    base_query = """
        SELECT
            COALESCE(ps.display_name, mh.player_name) AS player_name,
            mh.discord_user_id::text,
            SUM(mh.{metric}) AS total_value
        FROM match_history mh
        LEFT JOIN player_stats ps ON mh.discord_user_id = ps.user_id
        WHERE mh.{metric} IS NOT NULL
        GROUP BY COALESCE(ps.display_name, mh.player_name), mh.discord_user_id
        HAVING SUM(mh.{metric}) > 0
        ORDER BY total_value DESC
        LIMIT 10;
    """
    async with self.pool.acquire() as connection:
        for metric in metrics:
            query = base_query.format(metric=metric)
            rows = await connection.fetch(query)
            leaderboards[metric] = [dict(row) for row in rows]
    
    return leaderboards
    
async def get_full_player_export_data(self) -> List[Dict]:
    """
    Gets a comprehensive dataset of all players, their stats, and their entire
    event history from the snapshot table for CSV export.
    """
    query = """
        SELECT
            ps.user_id::text,
            ps.display_name,
            ps.accepted_count,
            ps.tentative_count,
            ps.declined_count,
            ps.last_signup_date,
            ps.rating,
            COALESCE(
                (SELECT json_agg(
                    json_build_object(
                        'event_title', peh.event_title,
                        'event_time', peh.event_time,
                        'role_name', peh.role_name,
                        'subclass_name', peh.subclass_name
                    ) ORDER BY peh.event_time DESC
                )
                FROM player_event_history peh
                WHERE peh.user_id = ps.user_id
                ),
                '[]'::json
            ) AS event_history
        FROM player_stats ps
        WHERE ps.is_active = TRUE;
    """
    async with self.pool.acquire() as connection:
        return [dict(row) for row in await connection.fetch(query)]

# --- Event Lock Management ---
async def lock_event(self, event_id: int, user_id: int):
    query = """
        INSERT INTO event_locks (event_id, locked_by_user_id, locked_at)
        VALUES ($1, $2, (NOW() AT TIME ZONE 'utc'))
        ON CONFLICT (event_id) DO UPDATE SET
            locked_by_user_id = $2,
            locked_at = (NOW() AT TIME ZONE 'utc');
    """
    async with self.pool.acquire() as connection:
        await connection.execute(query, event_id, user_id)

async def unlock_event(self, event_id: int):
    query = "DELETE FROM event_locks WHERE event_id = $1;"
    async with self.pool.acquire() as connection:
        await connection.execute(query, event_id)

async def get_event_lock_status(self, event_id: int) -> Optional[Dict]:
    query = """
        SELECT el.locked_by_user_id, el.locked_at, u.username AS locked_by_username
        FROM event_locks el
        JOIN users u ON el.locked_by_user_id = u.id
        WHERE el.event_id = $1;
    """
    async with self.pool.acquire() as connection:
        row = await connection.fetchrow(query, event_id)
        return dict(row) if row else None
        
async def force_unlock_all_events(self):
    query = "DELETE FROM event_locks;"
    async with self.pool.acquire() as connection:
        await connection.execute(query)

# --- Final Roster & Squad Management ---
async def get_squads_with_members(self, event_id: int) -> List[Dict]:
    """
    Retrieves all squads for an event and aggregates their members
    into a JSON array, ordered by their position.
    """
    async with self.pool.acquire() as connection:
        query = """
            SELECT 
                s.squad_id, 
                s.name, 
                s.squad_type,
                COALESCE(
                    json_agg(
                        json_build_object(
                           'squad_member_id', sm.squad_member_id,
                           'user_id', sm.user_id::text,
                           'assigned_role_name', sm.assigned_role_name,
                           'startup_task', sm.startup_task,
                           'display_name', COALESCE(ps.display_name, sm.user_id::text)
                        ) ORDER BY sm.position, sm.squad_member_id
                    ) FILTER (WHERE sm.squad_member_id IS NOT NULL),
                    '[]'
                ) as members
            FROM squads s
            LEFT JOIN squad_members sm ON s.squad_id = sm.squad_id
            LEFT JOIN player_stats ps ON sm.user_id = ps.user_id
            WHERE s.event_id = $1
            GROUP BY s.squad_id
            ORDER BY
                CASE WHEN s.name = 'Reserves' THEN 1 ELSE 0 END, -- Ensure Reserves is last
                s.squad_id;
        """
        records = await connection.fetch(query, event_id)
        return [dict(record) for record in records]

async def delete_squads_for_event(self, event_id: int):
    async with self.pool.acquire() as connection:
        await connection.execute("DELETE FROM squads WHERE event_id = $1;", event_id)

async def close(self):
    if self.pool: await self.pool.close(); print("Database connection pool closed.")
