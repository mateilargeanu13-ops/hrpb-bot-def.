import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

# Ensure project root is on sys.path so `utils` can be imported when loaded as an
# extension regardless of working directory or package context.
import sys
import pathlib
from datetime import datetime
from discord import TextStyle
from discord import ui

root = pathlib.Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from utils import punishments as punish_store
from typing import List


class Moderation(commands.Cog):
    """Moderation commands: kick, ban, (mute placeholder)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log_channel_id = None
        try:
            val = __import__("os").environ.get("LOG_CHANNEL_ID")
            if val:
                self.log_channel_id = int(val)
        except Exception:
            self.log_channel_id = None

    def _get_log_channel(self, guild: discord.Guild):
        if not self.log_channel_id:
            return None
        return guild.get_channel(self.log_channel_id) or self.bot.get_channel(self.log_channel_id)

    def _make_appeal_view(self, infraction_id: str, target_id: int, guild: discord.Guild) -> ui.View:
        """Return a View with an Appeal button that opens a modal for the target user."""

        class AppealModal(ui.Modal):
            def __init__(self, infraction_id: str, target_id: int, parent: "Moderation"):
                super().__init__(title="Submit Appeal")
                self.infraction_id = infraction_id
                self.target_id = target_id
                self.parent = parent
                self.reason = ui.TextInput(label="Appeal reason", style=TextStyle.paragraph, required=True, max_length=2000)
                self.add_item(self.reason)

            async def on_submit(self, interaction: discord.Interaction):
                if interaction.user.id != self.target_id:
                    await interaction.response.send_message("Only the affected user may submit an appeal.", ephemeral=True)
                    return
                ch = self.parent._get_log_channel(self.parent.bot.get_guild(self.parent.bot.guilds[0].id)) if self.parent.log_channel_id else None
                # Try to find a log channel via guild
                ch = self.parent._get_log_channel(interaction.guild) or ch
                emb = discord.Embed(title=f"Appeal for {self.infraction_id}", color=discord.Color(0x0082FE))
                emb.add_field(name="User", value=f"{interaction.user} ({interaction.user.id})", inline=True)
                emb.add_field(name="Infraction ID", value=str(self.infraction_id), inline=True)
                emb.add_field(name="Reason", value=self.reason.value, inline=False)
                emb.add_field(name="Timestamp", value=self.parent._format_ts(datetime.utcnow().isoformat() + "Z"), inline=True)
                if ch:
                    await ch.send(embed=emb)
                await interaction.response.send_message("Your appeal has been submitted to staff.", ephemeral=True)

        class _AppealView(ui.View):
            def __init__(self, infraction_id: str, target_id: int, guild: discord.Guild, parent: "Moderation"):
                super().__init__(timeout=None)
                self.infraction_id = infraction_id
                self.target_id = target_id
                self.guild = guild
                self.parent = parent

            @ui.button(label="Appeal", style=discord.ButtonStyle.primary)
            async def appeal_button(self, interaction: discord.Interaction, button: ui.Button):
                if interaction.user.id != self.target_id:
                    await interaction.response.send_message("Only the affected user may appeal.", ephemeral=True)
                    return
                modal = AppealModal(self.infraction_id, self.target_id, self.parent)
                await interaction.response.send_modal(modal)

        return _AppealView(infraction_id, target_id, guild, self)

    def _format_ts(self, ts: str) -> str:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(ts)

    def _make_action_embed(self, action: str, target: discord.abc.Snowflake, moderator: discord.abc.Snowflake, guild: discord.Guild, reason: Optional[str], infraction_id: str | None = None, title: Optional[str] = None):
        """Create a polished embed for moderation actions.

        Footer: server icon + "Infraction by <moderator>". Color: #0082FE.
        """
        if title is None:
            title = f"{action.title()} — {getattr(target, 'name', str(target))}"
        emb = discord.Embed(title=title, color=discord.Color(0x0082FE))
        emb.add_field(name="Action", value=action.upper(), inline=True)
        emb.add_field(name="Target", value=f"{getattr(target, 'mention', str(target))} ({getattr(target, 'id', str(target))})", inline=True)
        emb.add_field(name="Moderator", value=f"{getattr(moderator, 'name', str(moderator))} ({getattr(moderator, 'id', str(moderator))})" if hasattr(moderator, 'id') else str(moderator), inline=False)
        emb.add_field(name="Reason", value=reason or "(no reason)", inline=False)
        if infraction_id is not None:
            emb.add_field(name="Infraction ID", value=str(infraction_id), inline=True)
        # formatted timestamp (date + hour)
        emb.add_field(name="Timestamp", value=self._format_ts(datetime.utcnow().isoformat() + "Z"), inline=True)
        # footer with server icon and moderator
        icon = guild.icon.url if guild and getattr(guild, 'icon', None) else None
        emb.set_footer(text=f"Infraction by {getattr(moderator, 'name', str(moderator))}", icon_url=icon)
        return emb

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        """Kick a member. Attempts to DM the member before kicking."""
        # DM the user with an embed (server name displayed prominently in blue)
        dm = discord.Embed(title=f"You were kicked from {ctx.guild.name}", color=discord.Color(0x0082FE))
        dm.add_field(name="Moderator", value=f"{ctx.author} ({ctx.author.id})", inline=False)
        dm.add_field(name="Reason", value=reason or "(no reason)", inline=False)
        try:
            await member.send(embed=dm)
        except Exception:
            pass

        try:
            await member.kick(reason=reason)
            inf_id = punish_store.add_record(ctx.guild.id, member.id, "kick", ctx.author.id, reason)
            # log to configured channel
            ch = self._get_log_channel(ctx.guild)
            if ch:
                emb = self._make_action_embed("kick", member, ctx.author, ctx.guild, reason, infraction_id=inf_id)
                sent = await ch.send(content=member.mention, embed=emb, view=self._make_appeal_view(inf_id, member.id, ctx.guild))
                try:
                    await sent.create_thread(name=f"Proofs - {inf_id}")
                except Exception:
                    pass
            await ctx.send(embed=discord.Embed(description=f"Kicked {member.mention} (Infraction ID: {inf_id})", color=discord.Color.green()))
        except Exception as e:
            await ctx.send(f"Failed to kick: {e}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        """Ban a member. Attempts to DM the member before banning."""
        dm = discord.Embed(title=f"You were banned from {ctx.guild.name}", color=discord.Color(0x0082FE))
        dm.add_field(name="Moderator", value=f"{ctx.author} ({ctx.author.id})", inline=False)
        dm.add_field(name="Reason", value=reason or "(no reason)", inline=False)
        try:
            await member.send(embed=dm)
        except Exception:
            pass

        try:
            await member.ban(reason=reason)
            inf_id = punish_store.add_record(ctx.guild.id, member.id, "ban", ctx.author.id, reason)
            ch = self._get_log_channel(ctx.guild)
            if ch:
                emb = self._make_action_embed("ban", member, ctx.author, ctx.guild, reason, infraction_id=inf_id)
                sent = await ch.send(content=member.mention, embed=emb, view=self._make_appeal_view(inf_id, member.id, ctx.guild))
                try:
                    await sent.create_thread(name=f"Proofs - {inf_id}")
                except Exception:
                    pass
            await ctx.send(embed=discord.Embed(description=f"Banned {member.mention} (Infraction ID: {inf_id})", color=discord.Color.red()))
        except Exception as e:
            await ctx.send(f"Failed to ban: {e}")

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        """Warn a member (record-only, DMs the user)."""
        dm = discord.Embed(title=f"You were warned in {ctx.guild.name}", color=discord.Color(0x0082FE))
        dm.add_field(name="Moderator", value=f"{ctx.author} ({ctx.author.id})", inline=False)
        dm.add_field(name="Reason", value=reason or "(no reason)", inline=False)
        try:
            await member.send(embed=dm)
        except Exception:
            pass
        inf_id = punish_store.add_record(ctx.guild.id, member.id, "warn", ctx.author.id, reason)
        ch = self._get_log_channel(ctx.guild)
        if ch:
            emb = self._make_action_embed("warn", member, ctx.author, ctx.guild, reason, infraction_id=inf_id)
            sent = await ch.send(content=member.mention, embed=emb, view=self._make_appeal_view(inf_id, member.id, ctx.guild))
            try:
                await sent.create_thread(name=f"Proofs - {inf_id}")
            except Exception:
                pass
        await ctx.send(embed=discord.Embed(description=f"I successfully warned {member.mention} (Infraction ID: {inf_id})", color=discord.Color.yellow()))

    @commands.command(name="punishments")
    async def punishments_cmd(self, ctx: commands.Context, member: discord.Member = None):
        """Show a user's punishments."""
        target = member or ctx.author
        records = punish_store.get_records_for_user(ctx.guild.id, target.id)
        # only show punishment entries (P- prefix)
        records = [r for r in records if isinstance(r.get("id"), str) and r.get("id").startswith("P-")]
        if not records:
            await ctx.send(f"No punishments found for {target.mention}.")
            return
        emb = discord.Embed(title=f"Punishments for {getattr(target, 'name', target)}", color=discord.Color(0x0082FE))
        for r in records:
            ts = self._format_ts(r.get("timestamp"))
            action = r.get("action")
            reason = r.get("reason") or "(no reason)"
            mod = r.get("moderator_id")
            rid = r.get("id")
            revoked = r.get("revoked", False)
            label = f"[{ts}] {action.upper()} (ID: {rid}){' — REVOKED' if revoked else ''}"
            emb.add_field(name=label, value=f"Moderator: <@{mod}>\nReason: {reason}", inline=False)
        await ctx.send(embed=emb)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: int):
        """Unban a user by ID and record an unban infraction entry."""
        # try to find the ban entry
        bans = await ctx.guild.bans()
        ban_entry = None
        for b in bans:
            if b.user.id == int(user_id):
                ban_entry = b
                break
        if not ban_entry:
            await ctx.send(f"No ban found for user id {user_id}.")
            return
        try:
            await ctx.guild.unban(ban_entry.user)
        except Exception as e:
            await ctx.send(f"Failed to unban: {e}")
            return
        inf_id = punish_store.add_record(ctx.guild.id, user_id, "unban", ctx.author.id, "unbanned by moderator")
        ch = self._get_log_channel(ctx.guild)
        if ch:
            emb = self._make_action_embed("unban", ban_entry.user, ctx.author, ctx.guild, "unbanned by moderator", infraction_id=inf_id)
            sent = await ch.send(content=f"<@{user_id}>", embed=emb)
            try:
                await sent.create_thread(name=f"Proofs - {inf_id}")
            except Exception:
                pass
        await ctx.send(embed=discord.Embed(description=f"Unbanned user {user_id} (Infraction ID: {inf_id})", color=discord.Color.green()))

    @app_commands.command(name="unban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban_slash(self, interaction: discord.Interaction, user_id: int):
        bans = await interaction.guild.bans()
        ban_entry = None
        for b in bans:
            if b.user.id == int(user_id):
                ban_entry = b
                break
        if not ban_entry:
            await interaction.response.send_message(f"No ban found for user id {user_id}.")
            return
        try:
            await interaction.guild.unban(ban_entry.user)
        except Exception as e:
            await interaction.response.send_message(f"Failed to unban: {e}")
            return
        inf_id = punish_store.add_record(interaction.guild.id, user_id, "unban", interaction.user.id, "unbanned by moderator")
        ch = self._get_log_channel(interaction.guild)
        if ch:
            emb = self._make_action_embed("unban", ban_entry.user, interaction.user, interaction.guild, "unbanned by moderator", infraction_id=inf_id)
            sent = await ch.send(content=f"<@{user_id}>", embed=emb)
            try:
                await sent.create_thread(name=f"Proofs - {inf_id}")
            except Exception:
                pass
        await interaction.response.send_message(f"Unbanned user {user_id} (Infraction ID: {inf_id})")

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def revoke(self, ctx: commands.Context, infraction_id: str, *, reason: Optional[str] = None):
        """Revoke an infraction by ID."""
        ok = punish_store.revoke_infraction(infraction_id, ctx.author.id, reason)
        if not ok:
            await ctx.send(f"Infraction ID {infraction_id} not found.")
            return
        ch = self._get_log_channel(ctx.guild)
        if ch:
            emb = discord.Embed(title="Infraction Revoked", color=discord.Color(0x0082FE))
            emb.add_field(name="Infraction ID", value=str(infraction_id), inline=True)
            emb.add_field(name="Revoked by", value=f"{ctx.author} ({ctx.author.id})", inline=True)
            emb.add_field(name="Reason", value=reason or "(no reason)", inline=False)
            await ch.send(embed=emb)
        await ctx.send(embed=discord.Embed(description=f"Revoked infraction {infraction_id}.", color=discord.Color(0x0082FE)))

    @app_commands.command(name="revoke")
    @app_commands.checks.has_permissions(kick_members=True)
    async def revoke_slash(self, interaction: discord.Interaction, infraction_id: str, reason: Optional[str] = None):
        ok = punish_store.revoke_infraction(infraction_id, interaction.user.id, reason)
        if not ok:
            await interaction.response.send_message(f"Infraction ID {infraction_id} not found.")
            return
        ch = self._get_log_channel(interaction.guild)
        if ch:
            emb = discord.Embed(title="Infraction Revoked", color=discord.Color(0x0082FE))
            emb.add_field(name="Infraction ID", value=str(infraction_id), inline=True)
            emb.add_field(name="Revoked by", value=f"{interaction.user} ({interaction.user.id})", inline=True)
            emb.add_field(name="Reason", value=reason or "(no reason)", inline=False)
            await ch.send(embed=emb)
        await interaction.response.send_message(f"Revoked infraction {infraction_id}.")

    # --- Slash / application commands ---
    @app_commands.command(name="kick", description="Kick a member (DMs them, logs an infraction)")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick_slash(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        dm = discord.Embed(title=f"You were kicked from {interaction.guild.name}", color=discord.Color(0x0082FE))
        dm.add_field(name="Moderator", value=f"{interaction.user} ({interaction.user.id})", inline=False)
        dm.add_field(name="Reason", value=reason or "(no reason)", inline=False)
        try:
            await member.send(embed=dm)
        except Exception:
            pass
        try:
            await member.kick(reason=reason)
            inf_id = punish_store.add_record(interaction.guild.id, member.id, "kick", interaction.user.id, reason)
            ch = self._get_log_channel(interaction.guild)
            if ch:
                emb = self._make_action_embed("kick", member, interaction.user, interaction.guild, reason, infraction_id=inf_id)
                sent = await ch.send(content=member.mention, embed=emb, view=self._make_appeal_view(inf_id, member.id, interaction.guild))
                try:
                    await sent.create_thread(name=f"Proofs - {inf_id}")
                except Exception:
                    pass
            await interaction.response.send_message(f"Kicked {member.mention} (Infraction ID: {inf_id})")
        except Exception as e:
            await interaction.response.send_message(f"Failed to kick: {e}")

    @app_commands.command(name="ban", description="Ban a member (DMs them, logs an infraction)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban_slash(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        dm = discord.Embed(title=f"You were banned from {interaction.guild.name}", color=discord.Color(0x0082FE))
        dm.add_field(name="Moderator", value=f"{interaction.user} ({interaction.user.id})", inline=False)
        dm.add_field(name="Reason", value=reason or "(no reason)", inline=False)
        try:
            await member.send(embed=dm)
        except Exception:
            pass
        try:
            await member.ban(reason=reason)
            inf_id = punish_store.add_record(interaction.guild.id, member.id, "ban", interaction.user.id, reason)
            ch = self._get_log_channel(interaction.guild)
            if ch:
                emb = self._make_action_embed("ban", member, interaction.user, interaction.guild, reason, infraction_id=inf_id)
                sent = await ch.send(content=member.mention, embed=emb, view=self._make_appeal_view(inf_id, member.id, interaction.guild))
                try:
                    await sent.create_thread(name=f"Proofs - {inf_id}")
                except Exception:
                    pass
            await interaction.response.send_message(f"Banned {member.mention} (Infraction ID: {inf_id})")
        except Exception as e:
            await interaction.response.send_message(f"Failed to ban: {e}")

    @app_commands.command(name="warn", description="Warn a member (record-only; DMs them)")
    @app_commands.checks.has_permissions(kick_members=True)
    async def warn_slash(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        dm = discord.Embed(title=f"You were warned in {interaction.guild.name}", color=discord.Color(0x0082FE))
        dm.add_field(name="Moderator", value=f"{interaction.user} ({interaction.user.id})", inline=False)
        dm.add_field(name="Reason", value=reason or "(no reason)", inline=False)
        try:
            await member.send(embed=dm)
        except Exception:
            pass
        inf_id = punish_store.add_record(interaction.guild.id, member.id, "warn", interaction.user.id, reason)
        ch = self._get_log_channel(interaction.guild)
        if ch:
            emb = self._make_action_embed("warn", member, interaction.user, interaction.guild, reason, infraction_id=inf_id)
            sent = await ch.send(content=member.mention, embed=emb, view=self._make_appeal_view(inf_id, member.id, interaction.guild))
            try:
                await sent.create_thread(name=f"Proofs - {inf_id}")
            except Exception:
                pass
        await interaction.response.send_message(f"I successfully warned {member.mention} (Infraction ID: {inf_id})")

    @app_commands.command(name="punishments", description="Show punishments for a user")
    async def punishments_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        records = punish_store.get_records_for_user(interaction.guild.id, target.id)
        # filter to punishments only
        records = [r for r in records if isinstance(r.get("id"), str) and r.get("id").startswith("P-")]
        if not records:
            await interaction.response.send_message(f"No punishments found for {target.mention}.")
            return
        lines = []
        for r in records:
            ts = r.get("timestamp")
            action = r.get("action")
            reason = r.get("reason") or "(no reason)"
            mod = r.get("moderator_id")
            lines.append(f"[{ts}] {action.upper()} by <@{mod}> — {reason}")
        emb = discord.Embed(title=f"Punishments for {getattr(target, 'name', target)}", color=discord.Color(0x0082FE))
        for r in records:
            ts = self._format_ts(r.get("timestamp"))
            action = r.get("action")
            reason = r.get("reason") or "(no reason)"
            mod = r.get("moderator_id")
            rid = r.get("id")
            revoked = r.get("revoked", False)
            label = f"[{ts}] {action.upper()} (ID: {rid}){' — REVOKED' if revoked else ''}"
            emb.add_field(name=label, value=f"Moderator: <@{mod}>\nReason: {reason}", inline=False)
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="infraction", description="Create a staff infraction (DM + log)")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.choices(infraction_type=[
        app_commands.Choice(name="Verbal Warning", value="verbal_warning"),
        app_commands.Choice(name="Warning", value="warning"),
        app_commands.Choice(name="Strike", value="strike"),
        app_commands.Choice(name="Suspension", value="suspension"),
        app_commands.Choice(name="Under Investigation", value="under_investigation"),
        app_commands.Choice(name="Termination", value="termination"),
    ])
    async def infraction_slash(self, interaction: discord.Interaction, member: discord.Member, infraction_type: app_commands.Choice[str], reason: Optional[str] = None):
        """Create a staff infraction, send the embed to the user and log it."""
        # Build embed (fixed title)
        emb = discord.Embed(title="High Rock Park Border Infraction", color=discord.Color(0x0082FE))
        emb.add_field(name="Type", value=infraction_type.name, inline=True)
        emb.add_field(name="Moderator", value=f"{interaction.user} ({interaction.user.id})", inline=True)
        emb.add_field(name="Reason", value=reason or "(no reason)", inline=False)
        emb.add_field(name="Server", value=f"{interaction.guild.name} ({interaction.guild.id})", inline=False)
        # record infraction
        inf_id = punish_store.add_record(interaction.guild.id, member.id, infraction_type.value, interaction.user.id, reason)
        emb.add_field(name="Infraction ID", value=str(inf_id), inline=True)
        # footer with server icon and moderator
        icon = interaction.guild.icon.url if interaction.guild and getattr(interaction.guild, 'icon', None) else None
        emb.set_footer(text=f"Infraction by {interaction.user}", icon_url=icon)
        # DM target with embed
        try:
            await member.send(embed=emb)
        except Exception:
            pass

        # Send embed to the channel where the command was executed (if available)
        sent_msg = None
        try:
            ch = interaction.channel
            if ch:
                sent_msg = await ch.send(content=member.mention, embed=emb, view=self._make_appeal_view(inf_id, member.id, interaction.guild))
        except Exception:
            sent_msg = None

        # If we successfully posted the embed in-channel, record its location so it can be edited later
        if sent_msg is not None:
            try:
                punish_store.set_log_message(inf_id, sent_msg.channel.id, sent_msg.id)
                try:
                    await sent_msg.create_thread(name=f"Proofs - {inf_id}")
                except Exception:
                    pass
            except Exception:
                pass

        # Ephemeral confirmation to the moderator
        await interaction.response.send_message(f"I infracted successfully {member.mention}", ephemeral=True)

    @app_commands.command(name="infraction_list", description="List active infractions for a staff member")
    @app_commands.checks.has_permissions(kick_members=True)
    async def infraction_list(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        records = punish_store.get_active_records_for_user(interaction.guild.id, target.id)
        # only infractions (I-), exclude promotions
        records = [r for r in records if isinstance(r.get("id"), str) and r.get("id").startswith("I-") and not r.get("is_promotion", False)]
        if not records:
            await interaction.response.send_message(f"No active infractions found for {target.mention}.", ephemeral=True)
            return
        emb = discord.Embed(title=f"Active Infractions for {getattr(target, 'name', target)}", color=discord.Color(0x0082FE))
        for r in records:
            ts = self._format_ts(r.get("timestamp"))
            action = r.get("action")
            reason = r.get("reason") or "(no reason)"
            mod = r.get("moderator_id")
            rid = r.get("id")
            label = f"[{ts}] {action.upper()} (ID: {rid})"
            emb.add_field(name=label, value=f"Moderator: <@{mod}>\nReason: {reason}", inline=False)
        await interaction.response.send_message(embed=emb, ephemeral=True)

    @app_commands.command(name="promote", description="Promote a user to a role (checks recent promotions)")
    @app_commands.checks.has_permissions(kick_members=True)
    async def promote_slash(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role, reason: Optional[str] = None):
        # check last promotion
        records = punish_store.get_records_for_user(interaction.guild.id, member.id)
        promos = [r for r in records if r.get("action") == "promotion"]
        last_promo_time = None
        if promos:
            # find latest timestamp
            try:
                latest = max(promos, key=lambda x: x.get("timestamp"))
                last_promo_time = latest.get("timestamp")
            except Exception:
                last_promo_time = None
        if last_promo_time:
            try:
                last_dt = datetime.fromisoformat(last_promo_time.replace("Z", "+00:00"))
                elapsed = datetime.utcnow() - last_dt
                if elapsed.total_seconds() < 4 * 24 * 3600:
                    remaining = 4 * 24 * 3600 - elapsed.total_seconds()
                    days = int(remaining // 86400)
                    hours = int((remaining % 86400) // 3600)
                    minutes = int((remaining % 3600) // 60)
                    await interaction.response.send_message(f"This user can be promoted in {days}d {hours}h {minutes}m", ephemeral=True)
                    return
            except Exception:
                pass

        # perform promotion (note: the bot does not actually assign roles here; it records the promotion and notifies)
        emb = discord.Embed(title="High Rock Park Broder Promotion", color=discord.Color(0x0082FE))
        emb.add_field(name="Role", value=f"{role.name} ({role.id})", inline=True)
        emb.add_field(name="Promoted by", value=f"{interaction.user} ({interaction.user.id})", inline=True)
        emb.add_field(name="Reason", value=reason or "(no reason)", inline=False)
        emb.add_field(name="Server", value=f"{interaction.guild.name} ({interaction.guild.id})", inline=False)
        # record promotion (no ID shown in embed)
        inf_id = punish_store.add_record(interaction.guild.id, member.id, "promotion", interaction.user.id, reason)
        icon = interaction.guild.icon.url if interaction.guild and getattr(interaction.guild, 'icon', None) else None
        emb.set_footer(text=f"Promoted by {interaction.user}", icon_url=icon)

        # DM target
        try:
            await member.send(embed=emb)
        except Exception:
            pass

        # post in channel
        sent_msg = None
        try:
            ch = interaction.channel
            if ch:
                sent_msg = await ch.send(content=member.mention, embed=emb)
        except Exception:
            sent_msg = None
        if sent_msg:
            try:
                punish_store.set_log_message(inf_id, sent_msg.channel.id, sent_msg.id)
            except Exception:
                pass

        await interaction.response.send_message(f"Promoted {member.mention}", ephemeral=True)

    @app_commands.command(name="infraction_manage", description="Manage an existing infraction (revoke or edit)")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.choices(action=[
        app_commands.Choice(name="Revoke", value="revoke"),
        app_commands.Choice(name="Edit", value="edit"),
    ])
    @app_commands.choices(new_type=[
        app_commands.Choice(name="Verbal Warning", value="verbal_warning"),
        app_commands.Choice(name="Warning", value="warning"),
        app_commands.Choice(name="Strike", value="strike"),
        app_commands.Choice(name="Suspension", value="suspension"),
        app_commands.Choice(name="Under Investigation", value="under_investigation"),
        app_commands.Choice(name="Termination", value="termination"),
    ])
    async def infraction_manage(self, interaction: discord.Interaction, infraction_id: str, action: app_commands.Choice[str], new_type: Optional[app_commands.Choice[str]] = None, new_reason: Optional[str] = None):
        """Manage an infraction: revoke or edit its reason/type."""
        rec = punish_store.get_record_by_id(infraction_id)
        if not rec:
            await interaction.response.send_message(f"Infraction ID {infraction_id} not found.", ephemeral=True)
            return

        # Revoke
        if action.value == "revoke":
            ok = punish_store.revoke_infraction(infraction_id, interaction.user.id, new_reason)
            if not ok:
                await interaction.response.send_message(f"Failed to revoke {infraction_id}.", ephemeral=True)
                return
            # edit original embed if possible
            ch_id = rec.get("log_channel_id")
            msg_id = rec.get("log_message_id")
            if ch_id and msg_id:
                try:
                    ch = self.bot.get_channel(int(ch_id))
                    if ch:
                        msg = await ch.fetch_message(int(msg_id))
                        if msg and msg.embeds:
                            emb = msg.embeds[0]
                            emb.add_field(name="Status", value="<:w_banned:1472052624495874048> This Infraction was revoked", inline=False)
                            emb.color = discord.Color(0x0082FE)
                            await msg.edit(embed=emb)
                except Exception:
                    pass
            await interaction.response.send_message(f"Revoked infraction {infraction_id}.", ephemeral=True)
            return

        # Edit
        if action.value == "edit":
            updates = {}
            if new_type:
                updates["action"] = new_type.value
            if new_reason is not None:
                updates["reason"] = new_reason
            if updates:
                punish_store.update_record(infraction_id, **updates)
            # update original embed
            ch_id = rec.get("log_channel_id")
            msg_id = rec.get("log_message_id")
            if ch_id and msg_id:
                try:
                    ch = self.bot.get_channel(int(ch_id))
                    if ch:
                        msg = await ch.fetch_message(int(msg_id))
                        if msg and msg.embeds:
                            # rebuild embed to reflect changes
                            emb = discord.Embed(title=msg.embeds[0].title or f"Infraction (ID: {infraction_id})", color=discord.Color(0x0082FE))
                            a = updates.get("action") or rec.get("action")
                            r = updates.get("reason") or rec.get("reason")
                            emb.add_field(name="Type", value=a, inline=True)
                            emb.add_field(name="Moderator", value=f"<@{rec.get('moderator_id')}>", inline=True)
                            emb.add_field(name="Reason", value=r or "(no reason)", inline=False)
                            emb.add_field(name="Infraction ID", value=str(infraction_id), inline=True)
                            emb.add_field(name="Timestamp", value=self._format_ts(rec.get("timestamp")), inline=True)
                            icon = interaction.guild.icon.url if interaction.guild and getattr(interaction.guild, 'icon', None) else None
                            emb.set_footer(text=f"Infraction by {interaction.user}", icon_url=icon)
                            await msg.edit(embed=emb)
                except Exception:
                    pass
            await interaction.response.send_message(f"Edited infraction {infraction_id}.", ephemeral=True)
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
