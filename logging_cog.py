import os
import discord
from discord.ext import commands
from datetime import datetime


class LoggingCog(commands.Cog):
    """Simple logging for member join/leave and messages to a configured channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log_channel_id = None
        try:
            val = os.getenv("LOG_CHANNEL_ID")
            if val:
                self.log_channel_id = int(val)
        except Exception:
            self.log_channel_id = None

    def _get_log_channel(self, guild: discord.Guild):
        if not self.log_channel_id:
            return None
        return guild.get_channel(self.log_channel_id) or self.bot.get_channel(self.log_channel_id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = self._get_log_channel(member.guild)
        if channel:
            emb = discord.Embed(title="Member Joined", color=discord.Color(0x0082FE), timestamp=datetime.utcnow())
            emb.add_field(name="Member", value=f"{member.mention} ({member.id})", inline=False)
            await channel.send(embed=emb)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = self._get_log_channel(member.guild)
        if channel:
            emb = discord.Embed(title="Member Left", color=discord.Color(0x0082FE), timestamp=datetime.utcnow())
            emb.add_field(name="Member", value=f"{member.mention} ({member.id})", inline=False)
            await channel.send(embed=emb)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        channel = self._get_log_channel(message.guild)
        if channel:
            emb = discord.Embed(title="Message", color=discord.Color(0x0082FE), timestamp=datetime.utcnow())
            emb.add_field(name="Author", value=f"{message.author} ({message.author.id})", inline=True)
            emb.add_field(name="Channel", value=f"#{message.channel} ({message.channel.id})", inline=True)
            emb.add_field(name="Content", value=message.content or "(no content)", inline=False)
            await channel.send(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
