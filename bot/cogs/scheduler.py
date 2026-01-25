import discord
from discord.ext import tasks, commands
import datetime
import pytz
import traceback
import os
from dateutil.relativedelta import relativedelta
import traceback

# Use relative import to go up one level to the 'bot' package root
from ..utils.database import Database, RsvpStatus
from .event_management import create_event_embed, PersistentEventView

class Scheduler(commands.Cog):
    """Cog for handling scheduled background tasks."""
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        print("[Scheduler Cog] Initialized. Starting tasks...")
        # --- FIX: Uncommented the self-healing task ---
        self.check_event_messages.start()
        self.create_event_threads.start()
        self.recreate_recurring_events.start()
        self.cleanup_finished_events.start()
        self.purge_deleted_events.start()
        self.sync_event_threads.start()
        self.process_tentatives.start()
        self.update_event_embeds.start()
        self.sync_player_database.start()
        self.cache_player_names.start()

    def cog_unload(self):
        """Cleanly cancels all tasks when the cog is unloaded."""
        # --- FIX: Uncommented the self-healing cancel ---
        self.check_event_messages.cancel()
        self.create_event_threads.cancel()
        self.recreate_recurring_events.cancel()
        self.cleanup_finished_events.cancel()
        self.purge_deleted_events.cancel()
        self.sync_event_threads.cancel()
        self.process_tentatives.cancel()
        self.update_event_embeds.cancel()
        self.sync_player_database.cancel()
        self.cache_player_names.cancel()

    @tasks.loop(minutes=10)
    async def cache_player_names(self):
        """Periodically fetches and caches the display names of all active players."""
        print("\n[Scheduler] Running cache_player_names loop...")
        guild_id_str = os.getenv("GUILD_ID")
        if not guild_id_str:
            print("[Name Cache] GUILD_ID not set. Skipping name cache.")
            return

        guild = self.bot.get_guild(int(guild_id_str))
        if not guild:
            print(f"[Name Cache] Could not find guild with ID {guild_id_str}. Skipping.")
            return

        try:
            active_players = await self.db.get_engagement_stats()
            if not active_players:
                print("[Name Cache] No active players in the database to cache.")
                return

            member_data_to_cache = []
            for player in active_players:
                try:
                    member = guild.get_member(player['user_id']) or await guild.fetch_member(player['user_id'])
                    if member:
                        member_data_to_cache.append({
                            'id': member.id,
                            'name': member.display_name
                        })
                except discord.NotFound:
                    continue
            
            if member_data_to_cache:
                await self.db.cache_player_display_names(member_data_to_cache)
                print(f"[Name Cache] Successfully cached {len(member_data_to_cache)} player names.")

        except Exception as e:
            print(f"[Name Cache] FATAL ERROR during name caching: {e}")
            traceback.print_exc()

    @tasks.loop(minutes=10)
    async def sync_player_database(self):
        """
        Periodically and efficiently syncs the player database with members of a specific role.
        """
        print("\n[Scheduler] Running sync_player_database loop...")
        guild_id_str = os.getenv("GUILD_ID")
        role_id_str = os.getenv("PLAYER_SYNC_ROLE_ID")

        if not guild_id_str or not role_id_str:
            print("[Player Sync] GUILD_ID or PLAYER_SYNC_ROLE_ID not set. Skipping sync.")
            return

        try:
            guild_id, role_id = int(guild_id_str), int(role_id_str)
        except ValueError:
            print("[Player Sync] GUILD_ID or PLAYER_SYNC_ROLE_ID is not a valid integer. Skipping sync.")
            return

        guild = self.bot.get_guild(guild_id)
        role = guild.get_role(role_id) if guild else None
        if not role:
            print(f"[Player Sync] Could not find guild or role. Skipping sync.")
            return

        try:
            member_ids_with_role = {member.id for member in role.members if not member.bot}
            currently_active_players = await self.db.get_engagement_stats()
            currently_active_ids = {int(player['user_id']) for player in currently_active_players}

            ids_to_activate = list(member_ids_with_role - currently_active_ids)
            ids_to_deactivate = list(currently_active_ids - member_ids_with_role)

            if ids_to_activate:
                await self.db.update_member_active_status(ids_to_activate, True)
                print(f"[Player Sync] Activated {len(ids_to_activate)} new member(s).")

            if ids_to_deactivate:
                await self.db.update_member_active_status(ids_to_deactivate, False)
                print(f"[Player Sync] Deactivated {len(ids_to_deactivate)} member(s).")

            if not ids_to_activate and not ids_to_deactivate:
                print("[Player Sync] No changes to player active status needed.")

        except Exception as e:
            print(f"[Player Sync] FATAL ERROR during database sync operation: {e}")
            traceback.print_exc()
    
    @tasks.loop(seconds=15)
    async def update_event_embeds(self):
        """
        Periodically checks for events that need their embed updated due to
        out-of-band changes (e.g., a tentative player being promoted via the web UI).
        """
        try:
            events_to_update = await self.db.get_events_for_embed_update()
            if not events_to_update:
                return

            print(f"[Scheduler] Found {len(events_to_update)} event embed(s) to update.")
            for event in events_to_update:
                event_id = event['event_id']
                try:
                    channel = self.bot.get_channel(event['channel_id']) or await self.bot.fetch_channel(event['channel_id'])
                    message = await channel.fetch_message(event['message_id'])

                    new_embed = await create_event_embed(self.bot, event_id, self.db)

                    await message.edit(embed=new_embed)
                    await self.db.clear_embed_update_flag(event_id)
                    print(f"  [EmbedUpdate] Successfully updated embed for event {event_id}.")
                except discord.NotFound:
                    print(f"  [EmbedUpdate] Message or channel not found for event {event_id}. Clearing flag.")
                    await self.db.clear_embed_update_flag(event_id)
                except Exception as e:
                    print(f"  [EmbedUpdate] FAILED to update embed for event {event_id}: {e}")
        except Exception as e:
            print(f"[Scheduler] FATAL ERROR in update_event_embeds loop: {e}")
            traceback.print_exc()

    # --- FIX: Uncommented the self-healing loop ---
    @tasks.loop(minutes=3)
    async def check_event_messages(self):
        """
        Periodically checks if the message for an active event still exists.
        If not, it re-posts it. This acts as a self-healing mechanism.
        """
        print("\n[Scheduler] Running check_event_messages loop...")
        try:
            active_events = await self.db.get_active_events_with_message_id()
            if not active_events:
                print("[Scheduler] No active events with messages to check.")
                return

            print(f"[Scheduler] Checking {len(active_events)} active event message(s)...")
            for event in active_events:
                try:
                    channel = self.bot.get_channel(event['channel_id']) or await self.bot.fetch_channel(event['channel_id'])
                    await channel.fetch_message(event['message_id'])
                except discord.NotFound:
                    print(f"  [Self-Heal] Message for event {event['event_id']} ('{event['title']}') not found. Re-posting...")
                    try:
                        embed = await create_event_embed(self.bot, event['event_id'], self.db)
                        view = PersistentEventView(self.db)
                        
                        # Fix: Safe handling for roles
                        roles = event.get('mention_role_ids') or []
                        content = " ".join([f"<@&{rid}>" for rid in roles])

                        new_message = await channel.send(content=content, embed=embed, view=view)
                        await self.db.update_event_message_id(event['event_id'], new_message.id)
                        print(f"  [Self-Heal] Successfully re-posted message for event {event['event_id']}.")
                    except Exception as post_error:
                        print(f"  [Self-Heal] FAILED to re-post message for event {event['event_id']}: {post_error}")
                except Exception as e:
                    print(f"  [Self-Heal] Error checking message for event {event['event_id']}: {e}")
        except Exception as e:
            print(f"[Scheduler] FATAL ERROR in check_event_messages loop: {e}")
            traceback.print_exc()

    @tasks.loop(hours=1)
    async def process_tentatives(self):
        """Periodically converts 'Tentative' to 'Declined' for past events."""
        print("\n[Scheduler] Running process_tentatives loop...")
        try:
            tentative_signups = await self.db.get_past_events_with_tentatives()
            if not tentative_signups:
                print("[Scheduler] No tentative signups to process.")
                return

            for signup in tentative_signups:
                await self.db.set_rsvp(signup['event_id'], signup['user_id'], RsvpStatus.DECLINED)
                print(f"  [ProcessTentative] Converted User {signup['user_id']} to Declined for Event {signup['event_id']}.")

            print(f"[Scheduler] Processed {len(tentative_signups)} tentative signups.")
        except Exception as e:
            print(f"[Scheduler] FATAL ERROR in process_tentatives loop: {e}")
            traceback.print_exc()

    @tasks.loop(minutes=5)
    async def sync_event_threads(self):
        """Periodically syncs thread members with the latest accepted signups."""
        print("\n[Scheduler] Running sync_event_threads loop...")
        try:
            active_events = await self.db.get_active_events_with_threads()
            if not active_events:
                print("[Scheduler] No active threads to sync this cycle.")
                return

            for event in active_events:
                guild = self.bot.get_guild(event['guild_id'])
                if not guild: continue

                thread = guild.get_thread(event['thread_id'])
                if not thread: continue

                signups = await self.db.get_signups_for_event(event['event_id'])
                
                user_ids_to_sync = {
                    s['user_id'] for s in signups 
                    if s['rsvp_status'] in [RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE]
                }

                thread_member_ids = {member.id for member in await thread.fetch_members()}

                users_to_add = user_ids_to_sync - thread_member_ids
                users_to_remove = thread_member_ids - user_ids_to_sync

                for user_id in users_to_add:
                    try:
                        member = await guild.fetch_member(user_id)
                        await thread.add_user(member)
                        print(f"  [Sync:{event['event_id']}] Added {member.display_name} to thread.")
                    except Exception as e:
                        print(f"  [Sync:{event['event_id']}] FAILED to add member {user_id}: {e}")

                for user_id in users_to_remove:
                    if user_id == self.bot.user.id:
                        continue
                    try:
                        member = await guild.fetch_member(user_id)
                        await thread.remove_user(member)
                        print(f"  [Sync:{event['event_id']}] Removed {member.display_name} from thread.")
                    except Exception as e:
                        print(f"  [Sync:{event['event_id']}] FAILED to remove member {user_id}: {e}")

        except Exception as e:
            print(f"[Scheduler] FATAL ERROR in sync_event_threads loop: {e}")
            traceback.print_exc()

    @tasks.loop(minutes=1)
    async def create_event_threads(self):
        """Periodically checks for events that need a discussion thread created."""
        print("\n[Scheduler] Running create_event_threads loop...")
        try:
            events_to_process = await self.db.get_events_for_thread_creation()
            print(f"[Scheduler] Found {len(events_to_process)} event(s) awaiting channel creation.")

            if not events_to_process:
                return

            for event in events_to_process:
                print(f"[Scheduler] Processing event ID: {event['event_id']}")
                await self.process_thread_creation(event)

        except Exception as e:
            print(f"[Scheduler] FATAL ERROR in create_event_threads loop: {e}")
            traceback.print_exc()

    async def process_thread_creation(self, event: dict):
        event_id = event['event_id']
        print(f"  [Process:{event_id}] Starting thread creation process.")
        try:
            parent_channel = self.bot.get_channel(event['channel_id']) or await self.bot.fetch_channel(event['channel_id'])
            if not parent_channel:
                print(f"  [Process:{event_id}] FAILED: Could not find parent channel {event['channel_id']}. Will not mark as created.")
                return

            print(f"  [Process:{event_id}] Found parent channel: '{parent_channel.name}'.")

            event_time = event['event_time']
            date_str = event_time.strftime('%b %d')
            thread_name = f"{event['title']} - {date_str}"

            print(f"  [Process:{event_id}] Attempting to create a private thread with name '{thread_name}'...")
            discussion_thread = await parent_channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread
            )
            print(f"  [Process:{event_id}] SUCCESS: Discord API returned a thread object. ID: {discussion_thread.id}")

            signups = await self.db.get_signups_for_event(event_id)
            
            user_ids_to_add = [
                s['user_id'] for s in signups 
                if s['rsvp_status'] in [RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE]
            ]

            print(f"  [Process:{event_id}] Adding {len(user_ids_to_add)} members to the private thread...")
            for user_id in user_ids_to_add:
                try:
                    member = await parent_channel.guild.fetch_member(user_id)
                    if member:
                        await discussion_thread.add_user(member)
                except discord.NotFound:
                    print(f"    - Could not find member with ID {user_id} to add to thread.")
                except Exception as e:
                    print(f"    - Error adding member {user_id} to thread: {e}")
            print(f"  [Process:{event_id}] Finished adding members.")

            event_embed = await create_event_embed(self.bot, event_id, self.db)
            welcome_message = ""
            if user_ids_to_add:
                mentions = ' '.join([f'<@{user_id}>' for user_id in user_ids_to_add])
                welcome_message = f"Welcome, attendees! {mentions}"

            print(f"  [Process:{event_id}] Sending combined welcome message and embed to new thread...")
            await discussion_thread.send(content=welcome_message, embed=event_embed)
            print(f"  [Process:{event_id}] Welcome message and embed sent.")

            print(f"  [Process:{event_id}] Attempting to mark event as created in DB...")
            await self.db.mark_thread_created(event_id, discussion_thread.id)
            print(f"  [Process:{event_id}] SUCCESS: Event marked as created in DB.")

        except discord.Forbidden:
            print(f"  [Process:{event_id}] FAILED: PERMISSION ERROR. The bot is likely missing 'Create Private Threads' permission. The event will be re-attempted later.")
        except Exception as e:
            print(f"  [Process:{event_id}] FAILED: An unexpected error occurred. The event will be re-attempted later.")
            traceback.print_exc()

    @tasks.loop(minutes=5)
    async def recreate_recurring_events(self):
        """Checks if a recurring event's last occurrence has finished and creates the next one."""
        print("\n[Scheduler] Running recreate_recurring_events loop...")
        try:
            parent_events = await self.db.get_events_for_recreation()
            for parent_event in parent_events:
                await self.process_event_recreation(parent_event)
        except Exception as e:
            print(f"Error in recreate_recurring_events loop: {e}")
            traceback.print_exc()

    def calculate_next_occurrence(self, basis_time: datetime.datetime, rule: str) -> datetime.datetime:
        """Calculates the next occurrence strictly based on the previous time and rule."""
        if rule == 'daily':
            return basis_time + relativedelta(days=1)
        elif rule == 'weekly':
            return basis_time + relativedelta(weeks=1)
        elif rule == 'monthly':
            return basis_time + relativedelta(months=1)
        return None

    async def process_event_recreation(self, parent_event: dict):
        """Creates the next occurrence of a recurring event if the conditions are met."""
        now_utc = datetime.datetime.now(pytz.utc)
        parent_id = parent_event['event_id']
        
        latest_child = await self.db.get_latest_child_event(parent_id)
        
        if latest_child:
            basis_time = latest_child['event_time']
            next_start_time = self.calculate_next_occurrence(basis_time, parent_event['recurrence_rule'])
        else:
            basis_time = parent_event['event_time']
            next_start_time = basis_time

        if not next_start_time:
            return

        while next_start_time < now_utc:
            next_start_time = self.calculate_next_occurrence(next_start_time, parent_event['recurrence_rule'])

        if latest_child and latest_child['event_time'] >= next_start_time:
            return
            
        recreation_hours = parent_event.get('recreation_hours', 168)
        creation_window_start = next_start_time - datetime.timedelta(hours=recreation_hours)
        if now_utc < creation_window_start:
            return

        print(f"Recreating event for parent ID {parent_id}.")

        child_data = dict(parent_event)
        duration = parent_event['end_time'] - parent_event['event_time']
        child_data['event_time'] = next_start_time
        child_data['end_time'] = next_start_time + duration
        child_data['is_recurring'] = False
        child_data['parent_event_id'] = parent_id
        
        target_channel_id = latest_child['channel_id'] if latest_child else parent_event['channel_id']
        child_data['channel_id'] = target_channel_id

        # --- FIX START: Atomic creation and safe role handling ---
        child_id = None
        try:
            # 1. Create Event in DB
            child_id = await self.db.create_event(
                parent_event['guild_id'], target_channel_id, parent_event['creator_id'], child_data
            )

            # 2. Attempt to Send Embed
            target_channel = self.bot.get_channel(target_channel_id) or await self.bot.fetch_channel(target_channel_id)

            embed = await create_event_embed(self.bot, child_id, self.db)
            view = PersistentEventView(self.db)
            
            # Safe role handling: Ensure roles is a list, even if DB returns None
            roles = parent_event.get('mention_role_ids') or []
            content = " ".join([f"<@&{rid}>" for rid in roles])

            msg = await target_channel.send(content=content, embed=embed, view=view)
            
            # 3. Update DB with Message ID
            await self.db.update_event_message_id(child_id, msg.id)
            print(f"Successfully created new recurring child event. New child ID: {child_id}")

        except Exception as e:
            print(f"CRITICAL FAILURE during event creation for parent {parent_id}: {e}")
            traceback.print_exc()
            
            # ROLLBACK: If we created the event row but failed to send the message, DELETE the row.
            # This prevents a "Zombie" event and allows the bot to retry next loop.
            if child_id:
                print(f"Rolling back: Deleting corrupted event ID {child_id}...")
                try:
                    await self.db.delete_event(child_id)
                    print("Rollback successful.")
                except Exception as del_e:
                    print(f"Rollback failed: {del_e}")
        # --- FIX END ---

    @tasks.loop(time=datetime.time(hour=0, minute=5, tzinfo=pytz.utc))
    async def purge_deleted_events(self):
        """Runs once daily to permanently delete events marked for deletion over 7 days ago."""
        print("Running daily purge of old soft-deleted events...")
        try:
            events_to_purge = await self.db.get_events_for_purging()
            for event in events_to_purge:
                await self.db.delete_event(event['event_id'])
                print(f"Permanently purged event {event['event_id']} from database.")
            if len(events_to_purge) > 0:
                 print(f"Daily purge finished. Permanently removed {len(events_to_purge)} events.")
        except Exception as e:
            print(f"Error in purge_deleted_events loop: {e}")
            traceback.print_exc()

    @tasks.loop(minutes=1)
    async def cleanup_finished_events(self):
        """
        UPDATED FOR PHASE 1:
        Finds events that have ended, scrapes their thread history for archiving,
        and then permanently deletes them.
        """
        print("Running cleanup of old events...")
        try:
            events_to_delete = await self.db.get_finished_events_for_cleanup()
            for event in events_to_delete:
                event_id = event['event_id']
                print(f"Processing cleanup and archive for event ID: {event_id}")

                # 1. Archive Thread History if it exists
                if event.get('thread_id'):
                    try:
                        thread = self.bot.get_channel(event['thread_id']) or await self.bot.fetch_channel(event['thread_id'])
                        
                        if isinstance(thread, discord.Thread):
                            history_data = []
                            # Iterate through the history (oldest first)
                            async for msg in thread.history(limit=None, oldest_first=True):
                                history_data.append({
                                    'user_name': msg.author.display_name,
                                    'avatar_url': str(msg.author.display_avatar.url),
                                    'content': msg.content,
                                    'timestamp': msg.created_at,
                                    'attachment_urls': [a.url for a in msg.attachments]
                                })
                            
                            # Call database utility to save history & freeze plan
                            # Ensure 'archive_thread_history' exists in your database.py
                            await self.db.archive_thread_history(event_id, history_data)
                            print(f"  - Archived {len(history_data)} messages.")
                            
                            await thread.delete()
                            print(f"  - Thread {event['thread_id']} deleted.")
                    
                    except discord.NotFound: 
                        print(f"  - Thread {event['thread_id']} not found (already deleted?).")
                    except Exception as e: 
                        print(f"  - Error archiving/deleting thread for event {event_id}: {e}")

                # 2. Cleanup Event Message
                if event.get('message_id') and event.get('channel_id'):
                    try:
                        channel = self.bot.get_channel(event['channel_id']) or await self.bot.fetch_channel(event['channel_id'])
                        message = await channel.fetch_message(event['message_id'])
                        await message.delete()
                        print(f"  - Event message {event['message_id']} deleted.")
                    except discord.NotFound: pass
                    except Exception as e: print(f"  - Could not delete event message: {e}")

                # 3. Permanently remove the active event record
                await self.db.delete_event(event_id)
                print(f"  - Event {event_id} removed from active database.")

            if len(events_to_delete) > 0:
                print(f"Cleanup finished. Permanently archived and removed {len(events_to_delete)} old events.")
        except Exception as e:
            print(f"Error in cleanup_finished_events loop: {e}")
            traceback.print_exc()

    @process_tentatives.before_loop
    @sync_event_threads.before_loop
    @create_event_threads.before_loop
    @recreate_recurring_events.before_loop
    @cleanup_finished_events.before_loop
    @purge_deleted_events.before_loop
    @update_event_embeds.before_loop
    @sync_player_database.before_loop
    @cache_player_names.before_loop
    # --- FIX: Added self_check to before_loop wait ---
    @check_event_messages.before_loop
    async def before_tasks(self):
        """Waits until the bot is fully logged in and ready before starting loops."""
        print("[Scheduler Tasks] Waiting for bot to be ready...")
        await self.bot.wait_until_ready()
        print("[Scheduler Tasks] Bot is ready. Loops will now start.")

async def setup(bot: commands.Bot):
    """The setup function to add the cog and its commands."""
    await bot.add_cog(Scheduler(bot, bot.db))
