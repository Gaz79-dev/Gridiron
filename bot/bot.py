import discord
from discord.ext import commands
import os
import asyncio
import traceback
from dotenv import load_dotenv

# Use absolute imports from the 'bot' package root
from bot.utils.database import Database
from bot.utils.permissions import get_allowed_role_ids, is_authorized_interaction

# Load environment variables from .env file
load_dotenv()

class EventBot(commands.Bot):
    """A custom Bot class to hold the database connection."""
    def __init__(self, db: Database, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = db

    async def setup_hook(self):
        """The setup_hook is called when the bot logs in."""
        print("Bot setup hook running...")
        
        # --- FIX: Add the new admin cog to the list ---
        cogs_to_load = [
            'bot.cogs.event_management',
            'bot.cogs.scheduler',
            'bot.cogs.setup',
            'bot.cogs.sort',
            'bot.cogs.admin',
            'bot.cogs.match_stats'  # Match stats + player linking
        ]

        # Load each cog
        for cog_path in cogs_to_load:
            try:
                await self.load_extension(cog_path)
                print(f"Successfully loaded cog: {cog_path}")
            except Exception as e:
                print(f"Failed to load cog {cog_path}:")
                traceback.print_exc()
        
        # Sync commands
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} command(s) to guild {guild_id}.")
        else:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s) globally.")

async def main():
    """Main function to connect to the database and run the bot."""
    db = Database()
    await db.connect()
    
    intents = discord.Intents.default()
    intents.members = True  # Ensure the members intent is enabled
    intents.message_content = True
    
    bot = EventBot(db=db, command_prefix="!", intents=intents)

    # --- FIX START: Add event listeners for member join/leave ---
    @bot.event
    async def on_member_join(member: discord.Member):
        """Automatically adds new members to the player database."""
        if not member.bot:
            try:
                await db.add_or_update_server_member(member.id)
                print(f"Added new member to database: {member.display_name} (ID: {member.id})")
            except Exception as e:
                print(f"Error adding member {member.id} to database: {e}")

    @bot.event
    async def on_member_remove(member: discord.Member):
        """
        Handles a member leaving the server. It marks them as inactive,
        removes them from all upcoming event signups, and flags those events for an update.
        """
        if member.bot:
            return
            
        try:
            # Mark the player as inactive in the player_stats table
            await db.deactivate_server_member(member.id)
            print(f"Deactivated member in database: {member.display_name} (ID: {member.id})")
    
            # NEW: Remove them from all upcoming event signups
            await db.remove_user_from_all_upcoming_signups(member.id)
    
        except Exception as e:
            print(f"Error during on_member_remove for {member.id}: {e}")
            traceback.print_exc() # Use traceback for more detailed errors

    @bot.check
    async def global_role_check(interaction: discord.Interaction):
        allowed_role_ids = get_allowed_role_ids()
        if not allowed_role_ids:
            return True

        if is_authorized_interaction(interaction):
            return True

        try:
            await interaction.response.send_message(
                "You do not have the required role to use bot commands.",
                ephemeral=True,
                delete_after=15
            )
        except discord.InteractionResponded:
            pass

        return False
            
        user_role_ids = {role.id for role in interaction.user.roles}
        if user_role_ids.intersection(allowed_role_ids):
            return True
        
        try:
            await interaction.response.send_message(
                "You do not have the required role to use bot commands.", 
                ephemeral=True,
                delete_after=15
            )
        except discord.InteractionResponded:
            pass
            
        return False

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN not found in .env file.")
        return
        
    try:
        print("Bot is starting...")
        await bot.start(token)
    except KeyboardInterrupt:
        print("Bot shutting down...")
    finally:
        await db.close()
        await bot.close()
        print("Bot cleanup complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted by user.")
