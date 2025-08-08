import discord
from discord.ext import commands
from discord import app_commands
import os
from typing import List

# Use absolute imports from the 'bot' package root
from bot.utils.database import Database

# Ensure the GUILD_ID is set, as this is a guild-specific command
GUILD_ID = os.getenv("GUILD_ID")
if not GUILD_ID:
    raise ValueError("GUILD_ID not set in the environment, which is required for admin commands.")

# Define the command group and tie it to your specific guild
admin_group = app_commands.Group(
    name="admin", 
    description="Administrative commands for the bot.", 
    guild_ids=[int(GUILD_ID)]
)

class AdminCog(commands.Cog):
    """A cog for containing administrative commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db

    @admin_group.command(name="sync_members", description="Sync all server members to the player database.")
    @app_commands.default_permissions(administrator=True)
    async def sync_members(self, interaction: discord.Interaction):
        """
        Fetches all members from the server and syncs them with the player_stats table.
        This populates the database for the first time and can be run to update the list.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.")
            return

        all_member_ids = []
        try:
            # Fetch all members from the guild. This can be slow for large servers.
            async for member in guild.fetch_members(limit=None):
                if not member.bot:
                    all_member_ids.append(member.id)
            
            # Call the database function to perform the sync
            await self.db.sync_all_server_members(all_member_ids)
            
            await interaction.followup.send(
                f"✅ Member sync complete. Processed {len(all_member_ids)} members. "
                f"They are now available in the 'Player Ratings' panel in the web UI."
            )
        except discord.Forbidden:
            await interaction.followup.send("Error: The bot is missing the 'Server Members Intent' or required permissions to fetch all members.")
        except Exception as e:
            print(f"An error occurred during member sync: {e}")
            await interaction.followup.send(f"An unexpected error occurred. Please check the bot's logs.")

async def setup(bot: commands.Bot):
    """The setup function to add the cog and its commands."""
    await bot.add_cog(AdminCog(bot))
    # Add the command group to the bot's command tree
    bot.tree.add_command(admin_group)
