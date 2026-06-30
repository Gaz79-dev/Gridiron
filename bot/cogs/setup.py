import discord
from discord.ext import commands
from discord import app_commands

# This command group is registered globally.
# Do not read GUILD_ID at import time; guild/server configuration now lives in system_settings.
setup_group = app_commands.Group(
    name="setup",
    description="Commands for setting up the bot.",
)


@setup_group.command(name="thread_hours", description="Set hours before an event to open its discussion thread.")
@app_commands.describe(hours="e.g., 24 for one day")
async def set_thread_hours(interaction: discord.Interaction, hours: int):
    if not 1 <= hours <= 336:  # 2 weeks
        return await interaction.response.send_message(
            "Hours must be between 1 and 336.",
            ephemeral=True,
        )

    db = interaction.client.db
    await db.set_thread_creation_hours(interaction.guild.id, hours)
    await interaction.response.send_message(
        f"Event discussion threads will now be created {hours} hours before an event starts.",
        ephemeral=True,
    )


class SetupCog(commands.Cog):
    """A cog for containing setup commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    """The setup function to add the cog and its commands."""
    await bot.add_cog(SetupCog(bot))
    bot.tree.add_command(setup_group)
