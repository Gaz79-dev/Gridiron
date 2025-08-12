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
        return float(value)
    except (ValueError, TypeError):
        return None
# --- FIX END ---


async def _send_rsvp_log_message(user_id: int, event_title: str, old_status: str, new_status: str):
    log_channel_id = os.getenv("EVENT_LOG_CHANNEL_ID")
    bot_token = os.getenv("DISCORD_TOKEN")
    guild_id = os.getenv("GUILD_ID")

    if not all([log_channel_id, bot_token, guild_id]):
        print("Log channel, bot token, or guild ID not configured. Skipping log message.")
        return

    headers = {"Authorization": f"Bot {bot_token}"}
    member_name = f"ID: {user_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}"
            response = await client.get(url, headers=headers)
            if response.is_success:
                member_data = response.json()
                member_name = member_data.get('nick') or member_data['user'].get('global_name') or member_data['user']['username']
        except Exception as e:
            print(f"Could not fetch member name for logging: {e}")

    color = 0
    if new_status == RsvpStatus.ACCEPTED:
        color = 3066993  # Green
    elif new_status in [RsvpStatus.TENTATIVE, RsvpStatus.DECLINED]:
        color = 15158332 # Red

    embed = {
        "title": "RSVP Status Change",
        "color": color,
        "fields": [
            {"name": "Player", "value": member_name, "inline": True},
            {"name": "Event", "value": event_title, "inline": True},
            {"name": "Status Change", "value": f"**{old_status or 'None'}** → **{new_status}**", "inline": False},
        ],
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    try:
        url = f"https://discord.com/api/v10/channels/{log_channel_id}/messages"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json={"embeds": [embed]})
            response.raise_for_status()
    except Exception as e:
        print(f"Failed to send log message to Discord: {e}")

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        async def init_connection(conn):
            await conn.set_type_codec('json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
            await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
        try:
            self.pool = await asyncpg.create_pool(
                user=os.getenv("POSTGRES_USER"), password=os.getenv("POSTGRES_PASSWORD"),
                database=os.getenv("POSTGRES_DB"), host=os.getenv("POSTGRES_HOST", "db"),
                port=os.getenv("POSTGRES_PORT", 5432),
                init=init_connection
            )
            print("Successfully connected to the PostgreSQL database.")
            await self._initial_setup()
        except Exception as e:
            print(f"Error: Could not connect to the PostgreSQL database. {e}")
            raise

    async def _initial_setup(self):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username VARCHAR(50) UNIQUE NOT NULL, hashed_password VARCHAR(255) NOT NULL, is_active BOOLEAN DEFAULT TRUE, is_admin BOOLEAN DEFAULT FALSE);")
                await connection.execute("CREATE TABLE IF NOT EXISTS guilds (guild_id BIGINT PRIMARY KEY, event_manager_role_ids BIGINT[], thread_creation_hours INT DEFAULT 24);")
                await connection.execute("""CREATE TABLE IF NOT EXISTS events (event_id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        creator_id BIGINT NOT NULL,
                        message_id BIGINT UNIQUE,
                        channel_id BIGINT NOT NULL,
                        thread_id BIGINT,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        event_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        end_time TIMESTAMP WITH TIME ZONE,
                        timezone VARCHAR(100),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
                        thread_created BOOLEAN DEFAULT FALSE,
                        is_recurring BOOLEAN DEFAULT FALSE,
                        recurrence_rule VARCHAR(50),
                        mention_role_ids BIGINT[],
                        restrict_to_role_ids BIGINT[],
                        recreation_hours INT,
                        parent_event_id INT REFERENCES events(event_id) ON DELETE SET NULL,
                        last_recreated_at TIMESTAMP WITH TIME ZONE,
                        deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                        locked_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
                        locked_at TIMESTAMP WITH TIME ZONE
                    );
                """)
                await connection.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS needs_embed_update BOOLEAN DEFAULT FALSE;")

                await connection.execute("CREATE TABLE IF NOT EXISTS signups (signup_id SERIAL PRIMARY KEY, event_id INT REFERENCES events(event_id) ON DELETE CASCADE, user_id BIGINT NOT NULL, role_name VARCHAR(100), subclass_name VARCHAR(100), rsvp_status VARCHAR(10) NOT NULL, UNIQUE(event_id, user_id));")
                await connection.execute("CREATE TABLE IF NOT EXISTS squads (squad_id SERIAL PRIMARY KEY, event_id INT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE, name VARCHAR(100) NOT NULL, squad_type VARCHAR(50) NOT NULL);")
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS squad_members (
                        squad_member_id SERIAL PRIMARY KEY,
                        squad_id INT NOT NULL REFERENCES squads(squad_id) ON DELETE CASCADE,
                        user_id BIGINT NOT NULL,
                        assigned_role_name VARCHAR(100) NOT NULL,
                        startup_task VARCHAR(100),
                        UNIQUE(squad_id, user_id)
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
                        is_active BOOLEAN DEFAULT TRUE,
                        role_affinities JSONB DEFAULT '{}'::jsonb
                    );
                """)
                await connection.execute("ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS rating INT DEFAULT 50;")
                await connection.execute("ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")
                await connection.execute("ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS role_affinities JSONB DEFAULT '{}'::jsonb;")
                await connection.execute("ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS game_player_id TEXT;")
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
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS reminder_jobs (
                        job_id UUID PRIMARY KEY,
                        user_ids BIGINT[] NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    );
                """)
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS squad_templates (
                        template_id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        template_name VARCHAR(100) NOT NULL UNIQUE
                    );
                """)
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS squad_template_definitions (
                        definition_id SERIAL PRIMARY KEY,
                        template_id INT NOT NULL REFERENCES squad_templates(template_id) ON DELETE CASCADE,
                        squad_name VARCHAR(100) NOT NULL,
                        default_count INT NOT NULL DEFAULT 1,
                        squad_type VARCHAR(50) NOT NULL,
                        naming_convention VARCHAR(20) NOT NULL DEFAULT 'alpha',
                        source_rsvp_pool VARCHAR(50) NOT NULL
                    );
                """)
                
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS match_uploads (
                        match_id VARCHAR(255) PRIMARY KEY,
                        event_name VARCHAR(255) NOT NULL,
                        event_date DATE NOT NULL,
                        uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
                        uploaded_by_user_id INT REFERENCES users(id) ON DELETE SET NULL
                    );
                """)
                
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS match_history (
                        match_history_id SERIAL PRIMARY KEY,
                        match_id VARCHAR(255) REFERENCES match_uploads(match_id) ON DELETE CASCADE,
                        game_player_id TEXT NOT NULL,
                        discord_user_id BIGINT,
                        player_name VARCHAR(255),
                        kills INT,
                        deaths INT,
                        kd FLOAT,
                        combat_effectiveness INT,
                        support_score INT,
                        defensive_score INT,
                        offensive_score INT
                    );
                """)
                
                print("Database setup is complete.")

    # --- New function to calculate leaderboards from match history ---
    async def calculate_leaderboards(self) -> Dict[str, List[Dict]]:
        """
        Calculates leaderboards by finding the top 10 clan players within each match
        and counting their appearances.
        """
        async with self.pool.acquire() as conn:
            
            # This query filters for clan players first, then ranks them.
            # The final "LIMIT 10" has been removed to show all ranked players.
            base_query = """
                WITH ClanPlayerStats AS (
                    SELECT
                        mh.match_id,
                        ps.display_name,
                        ps.user_id,
                        mh.{stat_column},
                        RANK() OVER (PARTITION BY mh.match_id ORDER BY mh.{stat_column} DESC) as rank
                    FROM
                        match_history mh
                    INNER JOIN
                        player_stats ps ON mh.game_player_id = ps.game_player_id
                    WHERE
                        mh.{stat_column} IS NOT NULL
                )
                SELECT
                    cps.display_name AS player_name,
                    cps.user_id::text AS discord_user_id,
                    COUNT(cps.match_id) AS total_value
                FROM
                    ClanPlayerStats cps
                WHERE
                    cps.rank <= 10
                GROUP BY
                    cps.display_name, cps.user_id
                ORDER BY
                    total_value DESC;
            """
            
            # Execute the query for each leaderboard category
            kills_records = await conn.fetch(base_query.format(stat_column='kills'))
            combat_records = await conn.fetch(base_query.format(stat_column='combat_effectiveness'))
            support_records = await conn.fetch(base_query.format(stat_column='support_score'))
            offensive_records = await conn.fetch(base_query.format(stat_column='offensive_score'))
            defensive_records = await conn.fetch(base_query.format(stat_column='defensive_score'))
    
            return {
                "kills": [dict(r) for r in kills_records],
                "combat_effectiveness": [dict(r) for r in combat_records],
                "support_score": [dict(r) for r in support_records],
                "offensive_score": [dict(r) for r in offensive_records],
                "defensive_score": [dict(r) for r in defensive_records]
            }

    async def get_full_player_export_data(self) -> List[Dict]:
        """Gathers all active player stats and their complete event history for CSV export."""
        query = """
            SELECT
                ps.user_id,
                ps.display_name,
                ps.accepted_count,
                ps.tentative_count,
                ps.declined_count,
                ps.last_signup_date,
                ps.rating,
                COALESCE(
                    (SELECT jsonb_agg(peh.* ORDER BY peh.event_time DESC)
                     FROM player_event_history peh
                     WHERE peh.user_id = ps.user_id),
                    '[]'::jsonb
                ) as event_history
            FROM player_stats ps
            WHERE ps.is_active = TRUE;
        """
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query)
            return [dict(row) for row in records]

    async def update_player_game_id(self, user_id: int, game_player_id: str):
        """Updates a player's in-game ID for linking stats."""
        async with self.pool.acquire() as connection:
            await connection.execute(
                "UPDATE player_stats SET game_player_id = $1 WHERE user_id = $2;",
                game_player_id, user_id
            )

    async def cache_player_display_names(self, member_data: List[Dict]):
        """Updates the cached display names for a list of members."""
        async with self.pool.acquire() as connection:
            await connection.executemany(
                "UPDATE player_stats SET display_name = $1 WHERE user_id = $2;",
                [(m['name'], m['id']) for m in member_data]
            )

    async def check_match_exists(self, match_id: str) -> bool:
        """Checks if a match with the given signature has already been uploaded."""
        async with self.pool.acquire() as connection:
            return await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM match_uploads WHERE match_id = $1);", match_id
            )

    async def insert_match_data(self, match_id: str, event_name: str, event_date: datetime.date, uploader_id: int, match_stats: List[Dict]):
        """Inserts a new match and all its player stats into the database."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Link Discord IDs where possible
                game_id_to_discord_id = {
                    row['game_player_id']: row['user_id']
                    for row in await conn.fetch("SELECT user_id, game_player_id FROM player_stats WHERE game_player_id IS NOT NULL;")
                }

                # Create the main upload record
                await conn.execute(
                    "INSERT INTO match_uploads (match_id, event_name, event_date, uploaded_by_user_id) VALUES ($1, $2, $3, $4);",
                    match_id, event_name, event_date, uploader_id
                )

                # Prepare the data for insertion
                records_to_insert = []
                for row in match_stats:
                    game_player_id = row.get("Player ID")
                    # --- FIX: Convert all numeric string values from CSV to their correct types ---
                    records_to_insert.append((
                        match_id,
                        game_player_id,
                        game_id_to_discord_id.get(game_player_id),
                        row.get("Name"),
                        _safe_int(row.get("Kills")),
                        _safe_int(row.get("Deaths")),
                        _safe_float(row.get("K/D")),
                        _safe_int(row.get("Combat Effectiveness")),
                        _safe_int(row.get("Support Points")),
                        _safe_int(row.get("Defensive Points")),
                        _safe_int(row.get("Offensive Points"))
                    ))

                # Insert all player stats for this match
                await conn.copy_records_to_table(
                    'match_history',
                    records=records_to_insert,
                    columns=[
                        'match_id', 'game_player_id', 'discord_user_id', 'player_name',
                        'kills', 'deaths', 'kd', 'combat_effectiveness', 'support_score',
                        'defensive_score', 'offensive_score'
                    ]
                )
    
    async def add_or_update_server_member(self, user_id: int):
        query = """
            INSERT INTO player_stats (user_id, is_active) VALUES ($1, TRUE)
            ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, user_id)

    async def deactivate_server_member(self, user_id: int):
        async with self.pool.acquire() as connection:
            await connection.execute("UPDATE player_stats SET is_active = FALSE WHERE user_id = $1;", user_id)

    async def sync_all_server_members(self, member_ids_with_role: List[int]):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("UPDATE player_stats SET is_active = FALSE;")
                
                stmt = await connection.prepare("""
                    INSERT INTO player_stats (user_id, is_active) VALUES ($1, TRUE)
                    ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE;
                """)
                
                await stmt.executemany([(user_id,) for user_id in member_ids_with_role])

    async def get_all_player_stats(self, include_inactive: bool = False) -> List[Dict]:
        """
        Fetches all player stats. If include_inactive is False, only gets active players.
        Calculates days_since_last_signup directly in the database for performance.
        """
        # Dynamically add the WHERE clause unless we want to include inactive players
        where_clause = "" if include_inactive else "WHERE is_active = TRUE"

        query = f"""
            SELECT
                *,
                CASE
                    WHEN last_signup_date IS NOT NULL
                    THEN EXTRACT(DAY FROM (NOW() AT TIME ZONE 'utc' - last_signup_date))
                    ELSE NULL
                END AS days_since_last_signup
            FROM
                player_stats
            {where_clause};
        """
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def update_player_rating(self, user_id: int, rating: int):
        query = "UPDATE player_stats SET rating = $1 WHERE user_id = $2;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, rating, user_id)

    async def update_player_affinities(self, finalized_squads: List[Dict]):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for squad in finalized_squads:
                    squad_type = squad['squad_type']
                    for member in squad['members']:
                        user_id = int(member['user_id'])
                        role_name = member['assigned_role_name']

                        current_affinities_raw = await conn.fetchval(
                            "SELECT role_affinities FROM player_stats WHERE user_id = $1", user_id
                        )
                        current_affinities = json.loads(current_affinities_raw or '{}')

                        squad_counts = defaultdict(int, current_affinities.get('squad_types', {}))
                        role_counts = defaultdict(int, current_affinities.get('roles', {}))

                        squad_counts[squad_type] += 1
                        role_counts[role_name] += 1

                        new_affinities = {
                            'squad_types': squad_counts,
                            'roles': role_counts
                        }

                        await conn.execute(
                            "UPDATE player_stats SET role_affinities = $1 WHERE user_id = $2",
                            json.dumps(new_affinities), user_id
                        )
    
    async def create_squad_template(self, guild_id: int, template_name: str, definitions: List[Dict]) -> int:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                template_id = await conn.fetchval(
                    "INSERT INTO squad_templates (guild_id, template_name) VALUES ($1, $2) RETURNING template_id",
                    guild_id, template_name
                )
                for defi in definitions:
                    await conn.execute(
                        """
                        INSERT INTO squad_template_definitions
                        (template_id, squad_name, default_count, squad_type, naming_convention, source_rsvp_pool)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        template_id, defi['squad_name'], defi['default_count'], defi['squad_type'],
                        defi['naming_convention'], defi['source_rsvp_pool']
                    )
                return template_id

    async def update_squad_template(self, template_id: int, template_name: str, definitions: List[Dict]):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE squad_templates SET template_name = $1 WHERE template_id = $2",
                    template_name, template_id
                )
                await conn.execute("DELETE FROM squad_template_definitions WHERE template_id = $1", template_id)
                for defi in definitions:
                    await conn.execute(
                        """
                        INSERT INTO squad_template_definitions
                        (template_id, squad_name, default_count, squad_type, naming_convention, source_rsvp_pool)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        template_id, defi['squad_name'], defi['default_count'], defi['squad_type'],
                        defi['naming_convention'], defi['source_rsvp_pool']
                    )

    async def get_squad_template_by_id(self, template_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            template_row = await conn.fetchrow("SELECT * FROM squad_templates WHERE template_id = $1", template_id)
            if not template_row:
                return None
            definitions = await conn.fetch(
                "SELECT * FROM squad_template_definitions WHERE template_id = $1 ORDER BY definition_id", template_id
            )
            template = dict(template_row)
            template['definitions'] = [dict(d) for d in definitions]
            return template

    async def get_all_squad_templates(self) -> List[Dict]:
        async with self.pool.acquire() as conn:
            templates = await conn.fetch("SELECT * FROM squad_templates ORDER BY template_name")
            result = []
            for t in templates:
                template_with_defs = await self.get_squad_template_by_id(t['template_id'])
                if template_with_defs:
                    result.append(template_with_defs)
            return result

    async def delete_squad_template(self, template_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM squad_templates WHERE template_id = $1", template_id)

    async def promote_tentative_player(self, event_id: int, user_id: int, role_name: Optional[str], subclass_name: Optional[str]):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await self.set_rsvp(event_id, user_id, RsvpStatus.ACCEPTED)
                await self.update_signup_role(event_id, user_id, role_name, subclass_name)

    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE username = $1", username)
            return dict(row) if row else None

    async def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
            return dict(row) if row else None

    async def get_all_users(self) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM users ORDER BY username;")
            return [dict(row) for row in rows]

    async def create_user(self, username: str, hashed_password: str, is_admin: bool = False) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "INSERT INTO users (username, hashed_password, is_admin) VALUES ($1, $2, $3) RETURNING id",
                username, hashed_password, is_admin
            )

    async def update_user_password(self, user_id: int, new_hashed_password: str):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET hashed_password = $1 WHERE id = $2", new_hashed_password, user_id)

    async def update_user_status(self, user_id: int, is_active: Optional[bool], is_admin: Optional[bool]):
        query_parts, params = [], []
        if is_active is not None: params.append(is_active); query_parts.append(f"is_active = ${len(params)}")
        if is_admin is not None: params.append(is_admin); query_parts.append(f"is_admin = ${len(params)}")
        if not query_parts: return
        params.append(user_id)
        query = f"UPDATE users SET {', '.join(query_parts)} WHERE id = ${len(params)}"
        async with self.pool.acquire() as conn: await conn.execute(query, *params)

    async def delete_user(self, user_id: int):
        async with self.pool.acquire() as conn: await conn.execute("DELETE FROM users WHERE id = $1", user_id)

    async def create_event(self, guild_id: int, channel_id: int, creator_id: int, data: Dict) -> int:
        query = """
            INSERT INTO events (guild_id, channel_id, creator_id, title, description, event_time, end_time, timezone, is_recurring, recurrence_rule, mention_role_ids, restrict_to_role_ids, recreation_hours, parent_event_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14) RETURNING event_id;
        """
        async with self.pool.acquire() as connection:
            return await connection.fetchval(
                query, guild_id, channel_id, creator_id,
                data.get('title'),
                data.get('description'),
                data.get('event_time'),
                data.get('end_time'),
                data.get('timezone'),
                data.get('is_recurring'),
                data.get('recurrence_rule'),
                data.get('mention_role_ids', []),
                data.get('restrict_to_role_ids', []),
                data.get('recreation_hours'),
                data.get('parent_event_id')
            )

    async def update_event(self, event_id: int, data: Dict):
        query = """
            UPDATE events SET
                title = $1, description = $2, event_time = $3, end_time = $4, timezone = $5,
                is_recurring = $6, recurrence_rule = $7, mention_role_ids = $8,
                restrict_to_role_ids = $9, recreation_hours = $10
            WHERE event_id = $11;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(
                query, data.get('title'), data.get('description'),
                data.get('event_time'), data.get('end_time'), data.get('timezone'),
                data.get('is_recurring'), data.get('recurrence_rule'),
                data.get('mention_role_ids', []),
                data.get('restrict_to_role_ids', []),
                data.get('recreation_hours'), event_id
            )

    async def update_event_message_id(self, event_id: int, message_id: int):
        async with self.pool.acquire() as connection:
            await connection.execute("UPDATE events SET message_id = $1 WHERE event_id = $2;", message_id, event_id)

    async def get_event_by_message_id(self, message_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM events WHERE message_id = $1;", message_id)
            return dict(row) if row else None

    async def set_rsvp(self, event_id: int, user_id: int, new_status: str):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                event_and_signup_data = await connection.fetchrow(
                    """
                    SELECT e.title, e.event_time, s.rsvp_status, s.role_name, s.subclass_name
                    FROM events e
                    LEFT JOIN signups s ON e.event_id = s.event_id AND s.user_id = $2
                    WHERE e.event_id = $1
                    """,
                    event_id, user_id
                )

                if not event_and_signup_data:
                    return

                old_status = event_and_signup_data['rsvp_status']

                if old_status == new_status:
                    return

                if new_status != RsvpStatus.ACCEPTED:
                    await self.remove_user_from_all_squads(event_id, user_id)
                    await self.update_signup_role(event_id, user_id, None, None)

                await connection.execute(
                    """
                    INSERT INTO signups (event_id, user_id, rsvp_status) VALUES ($1, $2, $3)
                    ON CONFLICT (event_id, user_id) DO UPDATE SET rsvp_status = EXCLUDED.rsvp_status;
                    """,
                    event_id, user_id, new_status
                )

                await self.update_player_stats(user_id, old_status, new_status)

                is_log_worthy = old_status is not None and (
                    (old_status == RsvpStatus.ACCEPTED and new_status in [RsvpStatus.TENTATIVE, RsvpStatus.DECLINED]) or
                    (old_status in [RsvpStatus.TENTATIVE, RsvpStatus.DECLINED] and new_status == RsvpStatus.ACCEPTED)
                )

                if is_log_worthy:
                    await _send_rsvp_log_message(
                        user_id=user_id,
                        event_title=event_and_signup_data['title'],
                        old_status=old_status,
                        new_status=new_status
                    )

                if new_status == RsvpStatus.ACCEPTED:
                    await connection.execute(
                        """
                        INSERT INTO player_event_history (user_id, event_id, event_title, event_time, role_name, subclass_name)
                        VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (user_id, event_id) DO NOTHING;
                        """,
                        user_id,
                        event_id,
                        event_and_signup_data['title'],
                        event_and_signup_data['event_time'],
                        event_and_signup_data['role_name'],
                        event_and_signup_data['subclass_name']
                    )
                elif old_status == RsvpStatus.ACCEPTED:
                    await connection.execute(
                        "DELETE FROM player_event_history WHERE user_id = $1 AND event_id = $2;",
                        user_id, event_id
                    )

                await self.flag_event_for_embed_update(event_id)

    async def get_upcoming_events(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE deleted_at IS NULL AND (is_recurring = FALSE OR parent_event_id IS NOT NULL) AND COALESCE(end_time, event_time + INTERVAL '2 hours') > (NOW() AT TIME ZONE 'utc' - INTERVAL '12 hours');"
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def get_signups_for_event(self, event_id: int) -> List[Dict]:
        query = "SELECT * FROM signups WHERE event_id = $1 ORDER BY role_name, subclass_name;"
        async with self.pool.acquire() as conn:
            return [dict(row) for row in await conn.fetch(query, event_id)]

    async def get_signup(self, event_id: int, user_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM signups WHERE event_id = $1 AND user_id = $2", event_id, user_id)
            return dict(row) if row else None

    async def get_event_by_id(self, event_id: int, include_deleted: bool = False) -> Optional[Dict]:
        query = "SELECT * FROM events WHERE event_id = $1"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        query += ";"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, event_id)
            return dict(row) if row else None

    async def update_signup_role(self, event_id: int, user_id: int, role_name: Optional[str], subclass_name: Optional[str]):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE signups SET role_name = $1, subclass_name = $2 WHERE event_id = $3 AND user_id = $4;",
                    role_name, subclass_name, event_id, user_id
                )
                await connection.execute(
                    """
                    UPDATE player_event_history
                    SET role_name = $1, subclass_name = $2
                    WHERE user_id = $3 AND event_id = $4;
                    """,
                    role_name, subclass_name, user_id, event_id
                )

    async def get_recurring_parent_events(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE is_recurring = TRUE AND parent_event_id IS NULL AND deleted_at IS NULL ORDER BY event_time DESC;"
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def get_deleted_events(self) -> List[Dict]:
        query = "SELECT * FROM events WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC;"
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def get_latest_child_event(self, parent_event_id: int) -> Optional[Dict]:
        query = "SELECT * FROM events WHERE parent_event_id = $1 AND deleted_at IS NULL ORDER BY event_time DESC LIMIT 1;"
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(query, parent_event_id)
            return dict(row) if row else None

    async def update_player_stats(self, user_id: int, old_status: Optional[str], new_status: str):
        accepted_delta = 0
        tentative_delta = 0
        declined_delta = 0

        if new_status == RsvpStatus.ACCEPTED: accepted_delta += 1
        elif new_status == RsvpStatus.TENTATIVE: tentative_delta += 1
        elif new_status == RsvpStatus.DECLINED: declined_delta += 1

        if old_status == RsvpStatus.ACCEPTED: accepted_delta -= 1
        elif old_status == RsvpStatus.TENTATIVE: tentative_delta -= 1
        elif old_status == RsvpStatus.DECLINED: declined_delta -= 1

        last_signup_date_val = None
        if new_status == RsvpStatus.ACCEPTED:
            last_signup_date_val = datetime.datetime.now(datetime.timezone.utc)

        query = """
            INSERT INTO player_stats (user_id, accepted_count, tentative_count, declined_count, last_signup_date)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id) DO UPDATE SET
                accepted_count = GREATEST(0, player_stats.accepted_count + EXCLUDED.accepted_count),
                tentative_count = GREATEST(0, player_stats.tentative_count + EXCLUDED.tentative_count),
                declined_count = GREATEST(0, player_stats.declined_count + EXCLUDED.declined_count),
                last_signup_date = CASE
                                    WHEN EXCLUDED.last_signup_date IS NOT NULL THEN EXCLUDED.last_signup_date
                                    ELSE player_stats.last_signup_date
                                   END;
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

    async def get_accepted_events_for_user(self, user_id: int) -> List[Dict]:
        query = """
            SELECT event_title, event_time, role_name, subclass_name
            FROM player_event_history
            WHERE user_id = $1 ORDER BY event_time DESC;
        """
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query, user_id)]

    async def get_all_rsvpd_user_ids_for_event(self, event_id: int) -> List[int]:
        query = "SELECT user_id FROM signups WHERE event_id = $1;"
        async with self.pool.acquire() as connection:
            records = await connection.fetch(query, event_id)
            return [record['user_id'] for record in records]

    async def create_reminder_job(self, job_id: uuid.UUID, user_ids: List[int]) -> None:
        query = "INSERT INTO reminder_jobs (job_id, user_ids) VALUES ($1, $2);"
        async with self.pool.acquire() as connection:
            await connection.execute(query, job_id, user_ids)

    async def get_reminder_job(self, job_id: uuid.UUID) -> Optional[List[int]]:
        query = "SELECT user_ids FROM reminder_jobs WHERE job_id = $1;"
        async with self.pool.acquire() as connection:
            record = await connection.fetchrow(query, job_id)
            return record['user_ids'] if record else None

    async def delete_reminder_job(self, job_id: uuid.UUID) -> None:
        query = "DELETE FROM reminder_jobs WHERE job_id = $1;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, job_id)

    async def force_unlock_all_events(self):
        query = "UPDATE events SET locked_by_user_id = NULL, locked_at = NULL WHERE locked_by_user_id IS NOT NULL;"
        async with self.pool.acquire() as connection:
            await connection.execute(query)

    async def get_all_roles_and_subclasses(self) -> Dict:
        return {"roles": ROLES, "subclasses": SUBCLASSES}

    async def create_squad(self, event_id: int, name: str, squad_type: str) -> int:
        async with self.pool.acquire() as connection:
            return await connection.fetchval("INSERT INTO squads (event_id, name, squad_type) VALUES ($1, $2, $3) RETURNING squad_id;", event_id, name, squad_type)

    async def add_squad_member(self, squad_id: int, user_id: int, assigned_role: str):
        async with self.pool.acquire() as connection:
            await connection.execute("INSERT INTO squad_members (squad_id, user_id, assigned_role_name) VALUES ($1, $2, $3) ON CONFLICT (squad_id, user_id) DO UPDATE SET assigned_role_name = EXCLUDED.assigned_role_name;", squad_id, user_id, assigned_role)

    async def update_squad_member_role(self, squad_member_id: int, new_role: str):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE squad_members SET assigned_role_name = $1 WHERE squad_member_id = $2", new_role, squad_member_id)

    async def move_squad_member(self, squad_member_id: int, new_squad_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE squad_members SET squad_id = $1 WHERE squad_member_id = $2", new_squad_id, squad_member_id)

    async def get_squad_by_name(self, event_id: int, squad_name: str) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM squads WHERE event_id = $1 AND name = $2", event_id, squad_name)
            return dict(row) if row else None

    async def update_squad_member_task(self, squad_member_id: int, task: Optional[str]):
        query = "UPDATE squad_members SET startup_task = $1 WHERE squad_member_id = $2;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, task, squad_member_id)

    async def get_event_lock_status(self, event_id: int) -> Optional[Dict]:
        query = "SELECT e.locked_by_user_id, e.locked_at, u.username as locked_by_username FROM events e LEFT JOIN users u ON e.locked_by_user_id = u.id WHERE e.event_id = $1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, event_id)
            return dict(row) if row else None

    async def lock_event(self, event_id: int, user_id: int):
        query = "UPDATE events SET locked_by_user_id = $1, locked_at = (NOW() AT TIME ZONE 'utc') WHERE event_id = $2;"
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, event_id)

    async def unlock_event(self, event_id: int):
        query = "UPDATE events SET locked_by_user_id = NULL, locked_at = NULL WHERE event_id = $1;"
        async with self.pool.acquire() as conn:
            await conn.execute(query, event_id)

    async def get_active_events_with_threads(self) -> List[Dict]:
        query = """
            SELECT event_id, guild_id, thread_id FROM events
            WHERE thread_created = TRUE
              AND thread_id IS NOT NULL
              AND deleted_at IS NULL
              AND event_time > (NOW() AT TIME ZONE 'utc');
        """
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def get_active_events_with_message_id(self) -> List[Dict]:
        query = """
            SELECT event_id, title, channel_id, message_id, mention_role_ids
            FROM events
            WHERE deleted_at IS NULL
              AND message_id IS NOT NULL
              AND event_time > (NOW() AT TIME ZONE 'utc' - INTERVAL '2 hours');
        """
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def get_past_events_with_tentatives(self) -> List[Dict]:
        query = """
            SELECT s.event_id, s.user_id FROM signups s
            JOIN events e ON s.event_id = e.event_id
            WHERE s.rsvp_status = 'Tentative' AND e.end_time < (NOW() AT TIME ZONE 'utc');
        """
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def set_thread_creation_hours(self, guild_id: int, hours: int):
        query = """
            INSERT INTO guilds (guild_id, thread_creation_hours) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET thread_creation_hours = EXCLUDED.thread_creation_hours;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, guild_id, hours)

    async def get_events_for_thread_creation(self) -> List[dict]:
        query = "SELECT e.event_id, e.guild_id, e.channel_id, e.message_id, e.title, e.event_time FROM events e JOIN guilds g ON e.guild_id = g.guild_id WHERE e.thread_created = FALSE AND e.deleted_at IS NULL AND (NOW() AT TIME ZONE 'utc') >= (e.event_time - (g.thread_creation_hours * INTERVAL '1 hour'));"
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def mark_thread_created(self, event_id: int, thread_id: int):
        query = "UPDATE events SET thread_created = TRUE, thread_id = $1 WHERE event_id = $2;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, thread_id, event_id)

    async def get_finished_events_for_cleanup(self) -> List[dict]:
        query = """
            SELECT event_id, thread_id, message_id, channel_id
            FROM events
            WHERE
                COALESCE(end_time, event_time + INTERVAL '2 hours') < (NOW() AT TIME ZONE 'utc' - INTERVAL '2 hours')
            AND (
                is_recurring = FALSE
                OR
                parent_event_id IS NOT NULL
            );
        """
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def soft_delete_event(self, event_id: int):
        query = "UPDATE events SET deleted_at = (NOW() AT TIME ZONE 'utc') WHERE event_id = $1;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, event_id)

    async def restore_event(self, event_id: int):
        query = "UPDATE events SET deleted_at = NULL WHERE event_id = $1;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, event_id)

    async def get_events_for_purging(self) -> List[Dict]:
        query = "SELECT event_id FROM events WHERE deleted_at IS NOT NULL AND deleted_at <= (NOW() AT TIME ZONE 'utc' - INTERVAL '7 days');"
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def delete_event(self, event_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM events WHERE event_id = $1", event_id)

    async def get_events_for_recreation(self) -> List[dict]:
        query = "SELECT * FROM events WHERE is_recurring = TRUE AND parent_event_id IS NULL AND deleted_at IS NULL;"
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def update_last_recreated_at(self, event_id: int):
        query = "UPDATE events SET last_recreated_at = (NOW() AT TIME ZONE 'utc') WHERE event_id = $1;"
        async with self.pool.acquire() as connection:
            await connection.execute(query, event_id)

    async def get_squad_by_id(self, squad_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM squads WHERE squad_id = $1", squad_id)
            return dict(row) if row else None

    async def remove_user_from_all_squads(self, event_id: int, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM squad_members WHERE user_id = $1 AND squad_id IN (SELECT squad_id FROM squads WHERE event_id = $2)", user_id, event_id)

    async def get_squad_member_details(self, squad_member_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT sm.user_id, s.event_id FROM squad_members sm JOIN squads s ON sm.squad_id = s.squad_id WHERE sm.squad_member_id = $1", squad_member_id)
            return dict(row) if row else None

    async def flag_event_for_embed_update(self, event_id: int):
        await self.pool.execute("UPDATE events SET needs_embed_update = TRUE WHERE event_id = $1;", event_id)

    async def get_events_for_embed_update(self) -> List[Dict]:
        query = "SELECT event_id, channel_id, message_id FROM events WHERE needs_embed_update = TRUE AND message_id IS NOT NULL AND deleted_at IS NULL;"
        async with self.pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(query)]

    async def clear_embed_update_flag(self, event_id: int):
        await self.pool.execute("UPDATE events SET needs_embed_update = FALSE WHERE event_id = $1;", event_id)

    async def get_squads_with_members(self, event_id: int) -> List[Dict]:
        GUILD_ID, BOT_TOKEN = os.getenv("GUILD_ID"), os.getenv("DISCORD_TOKEN")
        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        
        query = """
            SELECT s.squad_id, s.name, s.squad_type, 
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'squad_member_id', sm.squad_member_id,
                               'user_id', sm.user_id::text,
                               'assigned_role_name', sm.assigned_role_name,
                               'startup_task', sm.startup_task
                           )
                       ) FILTER (WHERE sm.squad_member_id IS NOT NULL), 
                       '[]'
                   ) as members
            FROM squads s
            LEFT JOIN squad_members sm ON s.squad_id = sm.squad_id
            WHERE s.event_id = $1
            GROUP BY s.squad_id
            ORDER BY s.squad_id;
        """

        async with self.pool.acquire() as connection:
            records = await connection.fetch(query, event_id)

        if not GUILD_ID or not BOT_TOKEN:
            return [dict(record) for record in records]

        processed_squads = []
        async with httpx.AsyncClient() as client:
            for record in records:
                squad = dict(record)
                processed_members = []
                for member_data in squad.get('members', []):
                    user_id = member_data['user_id']
                    display_name = f"User ID: {user_id}"
                    url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{user_id}"
                    try:
                        response = await client.get(url, headers=headers)
                        if response.is_success:
                            api_member_data = response.json()
                            display_name = api_member_data.get('nick') or api_member_data['user'].get('global_name') or api_member_data['user']['username']
                        elif response.status_code == 404:
                            display_name = f"Left Server ({user_id})"
                    except Exception as e:
                        print(f"Exception while fetching member {user_id}: {e}")

                    member_data['display_name'] = display_name
                    processed_members.append(member_data)
                
                squad['members'] = processed_members
                processed_squads.append(squad)
        return processed_squads

    async def delete_squads_for_event(self, event_id: int):
        async with self.pool.acquire() as connection:
            await connection.execute("DELETE FROM squads WHERE event_id = $1;", event_id)

    async def close(self):
        if self.pool: await self.pool.close(); print("Database connection pool closed.")
