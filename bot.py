import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} application commands")
    except Exception as e:
        print(f"Failed to sync app commands: {e}")


# Simple prefix command
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong!")


# Simple slash command
@bot.tree.command(name="ping")
async def ping_slash(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")


async def main():
    extensions = [
        "cogs.moderation",
        "cogs.logging_cog",
        "cogs.command_logger",
    ]
    async with bot:
        for ext in extensions:
            try:
                await bot.load_extension(ext)
                print(f"Loaded extension {ext}")
            except Exception as e:
                print(f"Failed to load extension {ext}: {e}")
        await bot.start(TOKEN)


if __name__ == "__main__":
    if not TOKEN:
        print("Error: BOT_TOKEN not set in environment")
    else:
        asyncio.run(main())
