import os
import discord
from discord.ext import commands

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "1425214731140202546"))


class CommandLogger(commands.Cog):
    """Logs prefix and slash command usage to a configured channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        # prefix command invoked
        guild = ctx.guild
        if not guild:
            return
        channel = self._get_log_channel(guild)
        if not channel:
            return
        cmd = ctx.command.qualified_name if ctx.command else "unknown"
        emb = discord.Embed(title="Command Used", color=discord.Color(0x0082FE), timestamp=ctx.message.created_at)
        emb.add_field(name="User", value=f"{ctx.author} ({ctx.author.id})", inline=False)
        emb.add_field(name="Command", value=f"{cmd}", inline=True)
        emb.add_field(name="Channel", value=f"#{ctx.channel} ({ctx.channel.id})", inline=True)
        await channel.send(embed=emb)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # application command invocation
        if not interaction.guild:
            return
        if interaction.type.name != "application_command":
            return
        channel = self._get_log_channel(interaction.guild)
        if not channel:
            return
        name = getattr(interaction.command, 'name', None) or (interaction.data and interaction.data.get('name')) or 'unknown'
        emb = discord.Embed(title="Slash Command Used", color=discord.Color(0x0082FE), timestamp=interaction.created_at)
        emb.add_field(name="User", value=f"{interaction.user} ({interaction.user.id})", inline=False)
        emb.add_field(name="Command", value=f"/{name}", inline=True)
        ch = interaction.channel
        emb.add_field(name="Channel", value=f"#{ch} ({ch.id})" if ch else "DM", inline=True)
        await channel.send(embed=emb)

    def _get_log_channel(self, guild: discord.Guild):
        # prefer configured channel id; fall back to bot cache
        try:
            ch = guild.get_channel(LOG_CHANNEL_ID) or self.bot.get_channel(LOG_CHANNEL_ID)
            return ch
        except Exception:
            return None


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandLogger(bot))
