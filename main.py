# ============================================================
#                 MALARVAADI DISCORD BOT
#                    ADVANCED EDITION
# ============================================================

import os
import re
import json
import time
import random
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
from dotenv import load_dotenv

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

BOT_NAME = "Malarvaadi"
PREFIX = "+"
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE = "malarvaadi.db"

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

COLOR = 0x5865F2
SUCCESS = 0x57F287
ERROR = 0xED4245
WARNING = 0xFEE75C

VERSION = "1.0.0"
START_TIME = time.time()

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("malarvaadi.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("Malarvaadi")

# ============================================================
# BOT INTENTS
# ============================================================

intents = discord.Intents.default()

intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.voice_states = True
intents.presences = True

# ============================================================
# BOT INITIALIZATION
# ============================================================

class MalarvaadiBot(commands.Bot):

    def __init__(self):

        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX),
            intents=intents,
            help_command=None,
            case_insensitive=True
        )

        self.db = None
        self.ready_at = None

        self.cooldowns = defaultdict(dict)
        self.config_cache = {}

    async def setup_hook(self):

        logger.info("Initializing Malarvaadi database...")

        self.db = await aiosqlite.connect(DATABASE)

        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA foreign_keys=ON")

        await initialize_database(self)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS logging_config (
                guild_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                channel_id INTEGER,
                enabled INTEGER DEFAULT 1,
                events_json TEXT DEFAULT '{}',
                PRIMARY KEY (guild_id, category)
            )
        """)
        await self.db.commit()

        logger.info("Database initialized.")

        await self.tree.sync()

        logger.info("Slash commands synchronized.")

    async def on_ready(self):

        self.ready_at = datetime.now(timezone.utc)

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers | +help"
            )
        )

        logger.info(
            f"{self.user} is online | "
            f"Servers: {len(self.guilds)}"
        )

    async def close(self):

        if self.db:
            await self.db.close()

        await super().close()


bot = MalarvaadiBot()

# ============================================================
# DATABASE INITIALIZATION
# ============================================================

async def initialize_database(bot):

    tables = [

        """
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            welcome_channel INTEGER,
            goodbye_channel INTEGER,
            log_channel INTEGER,
            autorole INTEGER,
            modlog_channel INTEGER,
            currency TEXT DEFAULT 'Coins',
            welcome_message TEXT,
            prefix TEXT DEFAULT '+'
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER,
            guild_id INTEGER,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            wallet INTEGER DEFAULT 0,
            bank INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            last_daily INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, guild_id)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            created_at INTEGER
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS tickets (
            channel_id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            user_id INTEGER,
            claimed_by INTEGER,
            status TEXT DEFAULT 'open',
            created_at INTEGER
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS giveaways (
            message_id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            channel_id INTEGER,
            prize TEXT,
            winners INTEGER,
            ends_at INTEGER,
            ended INTEGER DEFAULT 0
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_id INTEGER,
            message TEXT,
            remind_at INTEGER,
            completed INTEGER DEFAULT 0
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id INTEGER,
            message_id INTEGER,
            emoji TEXT,
            role_id INTEGER,
            PRIMARY KEY(message_id, emoji)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS birthdays (
            guild_id INTEGER,
            user_id INTEGER,
            day INTEGER,
            month INTEGER,
            PRIMARY KEY(guild_id, user_id)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS economy_inventory (
            guild_id INTEGER,
            user_id INTEGER,
            item TEXT,
            quantity INTEGER DEFAULT 1,
            PRIMARY KEY(guild_id, user_id, item)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            content TEXT,
            status TEXT DEFAULT 'pending'
        )
        """
    ]

    for table in tables:
        await bot.db.execute(table)

    await bot.db.commit()

# ============================================================
# EMBED HELPERS
# ============================================================

def make_embed(title, description=None, color=COLOR):

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_footer(
        text="MALARVAADI • Advanced Discord Management"
    )

    return embed


async def ensure_user(guild_id, user_id):

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO users (user_id, guild_id)
        VALUES (?, ?)
        """,
        (user_id, guild_id)
    )

    await bot.db.commit()


async def get_config(guild_id):

    cursor = await bot.db.execute(
        "SELECT * FROM guild_config WHERE guild_id = ?",
        (guild_id,)
    )

    return await cursor.fetchone()


# ============================================================
# INTERACTIVE HELP CENTER
# ============================================================

HELP_CATEGORIES = {

    "Moderation": (
        "🛡️",
        "Server protection and moderation tools."
    ),

    "Economy": (
        "💰",
        "Currency, banking, trading and virtual economy."
    ),

    "Fun": (
        "🎮",
        "Games, entertainment and interactive commands."
    ),

    "Leveling": (
        "📊",
        "XP, ranks, leaderboards and progression."
    ),

    "Tickets": (
        "🎟️",
        "Support tickets and staff management."
    ),

    "Giveaways": (
        "🎉",
        "Automated giveaway management."
    ),

    "Welcome": (
        "👋",
        "Member welcome messages and onboarding."
    ),

    "Birthdays": (
        "🎂",
        "Birthday tracking and celebrations."
    ),

    "Community": (
        "👥",
        "Suggestions, polls and community engagement."
    ),

    "Configuration": (
        "⚙️",
        "Server and bot configuration."
    ),

    "Counters": (
        "🔢",
        "Live server counter management."
    ),

    "Join to Create": (
        "🎙️",
        "Dynamic voice channel management."
    ),

    "Reaction Roles": (
        "🎭",
        "Self-assignable server roles."
    ),

    "Verification": (
        "✅",
        "Member verification and access control."
    ),

    "Utilities": (
        "🔧",
        "Useful tools and server utilities."
    )
}


# ============================================================
# MALARVAADI PREMIUM INTERACTIVE HELP CENTER
# ============================================================

HELP_COMMAND_GROUPS = {
    "Getting Started": {
        "emoji": "🏠",
        "description": "Essential bot commands",
        "commands": ["help", "botinfo", "serverstats"]
    },
    "Moderation": {
        "emoji": "🛡️",
        "description": "Moderation and server protection",
        "commands": [
            "ban", "kick", "timeout", "untimeout",
            "warn", "warnings", "clearwarnings",
            "purge", "lock", "unlock", "slowmode"
        ]
    },
    "Economy": {
        "emoji": "💰",
        "description": "Coins, rewards and marketplace",
        "commands": [
            "balance", "daily", "work", "deposit",
            "withdraw", "pay", "crime", "rob",
            "richest", "inventory", "buy", "sell",
            "giftitem", "useitem"
        ]
    },
    "Leveling & Games": {
        "emoji": "🎮",
        "description": "XP, ranks and entertainment",
        "commands": [
            "rank", "leaderboard", "coinflip", "dice",
            "rps", "guess", "guessnumber", "cancelguess",
            "trivia", "triviaanswer", "gameleaderboard",
            "gamestats"
        ]
    },
    "Community": {
        "emoji": "🌍",
        "description": "Community engagement tools",
        "commands": [
            "suggest", "approve", "reject", "poll",
            "endpoll", "pollinfo", "confess", "announce",
            "confessionstats", "remind", "myreminders",
            "cancelreminder", "repeatremind"
        ]
    },
    "Welcome & Onboarding": {
        "emoji": "👋",
        "description": "Welcome messages, goodbye messages and member onboarding",
        "commands": [
            "setwelcome", "setwelcomemessage", "setgoodbye",
            "setgoodbyemessage", "setautorole", "disableautorole",
            "setaccountage", "onboarding"
        ]
    },
    "Logging": {
        "emoji": "📋",
        "description": "Server audit logs and member activity.",
        "commands": ["setlogs", "logs", "logging"]
    },
    "Server Management": {
        "emoji": "⚙️",
        "description": "Configure and manage your server",
        "commands": [
            "setmembercounter",
            "addreactionrole", "removereactionrole",
            "reactionroles", "setstarboard", "starboardemoji",
            "disablestarboard", "setsticky", "removesticky",
            "verificationpanel", "setverifiedrole",
            "setsecuritylog", "setminaccountage", "antiraid",
            "securitystatus", "setvoicecreate", "disablevoicecreate",
            "roomname", "roomlimit", "roomlock", "roomunlock",
            "roomtransfer", "roominfo"
        ]
    },
    "Events & Giveaways": {
        "emoji": "🎉",
        "description": "Events and community giveaways",
        "commands": [
            "eventcreate", "eventjoin", "eventleave",
            "eventparticipants", "eventinfo", "eventcancel",
            "eventlist", "giveaway", "endgiveaway",
            "reroll", "giveawayinfo"
        ]
    },
    "Administration": {
        "emoji": "👑",
        "description": "Advanced bot administration",
        "commands": [
            "dbstatus", "serverconfig", "disablecommand",
            "enablecommand", "adminhistory", "maintenance",
            "activityleaderboard", "dailyreport", "weeklyreport"
        ]
    }
}


class MalarvaadiHelpView(discord.ui.View):

    def __init__(self, author_id):
        super().__init__(timeout=180)

        self.author_id = author_id
        self.category = None
        self.page = 0
        self.page_size = 6

        options = [
            discord.SelectOption(
                label=name,
                emoji=data["emoji"],
                description=data["description"][:100],
                value=name
            )
            for name, data in HELP_COMMAND_GROUPS.items()
        ]

        select = discord.ui.Select(
            placeholder="Explore Malarvaadi commands...",
            options=options
        )

        select.callback = self.select_category
        self.add_item(select)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This help menu belongs to another user.",
                ephemeral=True
            )
            return False

        return True

    def build_embed(self):

        if self.category is None:
            embed = make_embed(
                "🌺 MALARVAADI | HELP CENTER",
                "Welcome to the Malarvaadi command center!\n\n"
                "Select a category from the dropdown menu "
                "to explore available commands."
            )

            embed.add_field(
                name="🤖 Bot Information",
                value=(
                    f"**Servers:** {len(bot.guilds)}\n"
                    f"**Commands:** {len(list(bot.walk_commands()))}\n"
                    f"**Prefix:** `{PREFIX}`"
                ),
                inline=True
            )

            embed.add_field(
                name="⚡ Command System",
                value="Prefix and slash commands supported.",
                inline=True
            )

            embed.set_footer(
                text="Malarvaadi • Interactive Help Center"
            )

            return embed

        data = HELP_COMMAND_GROUPS[self.category]
        available = []

        for name in data["commands"]:
            command = bot.get_command(name)

            if command is not None:
                available.append(command)

        total_pages = max(
            1,
            (len(available) + self.page_size - 1)
            // self.page_size
        )

        self.page = min(self.page, total_pages - 1)

        start = self.page * self.page_size
        current = available[start:start + self.page_size]

        embed = make_embed(
            f"{data['emoji']} {self.category}",
            data["description"]
        )

        if not current:
            embed.description += (
                "\n\nNo matching commands are currently registered."
            )
        else:
            for command in current:
                description = (
                    command.short_doc or "No description available."
                )

                embed.add_field(
                    name=f"`{PREFIX}{command.qualified_name}`",
                    value=description[:200],
                    inline=False
                )

        embed.set_footer(
            text=f"Malarvaadi • Page {self.page + 1}/{total_pages}"
        )

        return embed

    async def select_category(self, interaction):
        self.category = interaction.data["values"][0]
        self.page = 0

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

    @discord.ui.button(
        label="Previous",
        emoji="⬅️",
        style=discord.ButtonStyle.secondary
    )
    async def previous_page(self, interaction, button):

        if self.category is None:
            await interaction.response.send_message(
                "Select a category first.",
                ephemeral=True
            )
            return

        self.page = max(0, self.page - 1)

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

    @discord.ui.button(
        label="Home",
        emoji="🏠",
        style=discord.ButtonStyle.primary
    )
    async def home_page(self, interaction, button):
        self.category = None
        self.page = 0

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

    @discord.ui.button(
        label="Next",
        emoji="➡️",
        style=discord.ButtonStyle.secondary
    )
    async def next_page(self, interaction, button):

        if self.category is None:
            await interaction.response.send_message(
                "Select a category first.",
                ephemeral=True
            )
            return

        self.page += 1

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )


@bot.hybrid_command(
    name="help",
    description="Open the Malarvaadi interactive help center."
)
async def help_command(ctx):

    view = MalarvaadiHelpView(ctx.author.id)

    await ctx.send(
        embed=view.build_embed(),
        view=view,
        ephemeral=ctx.interaction is not None
    )

# BASIC EVENT HANDLERS
# ============================================================

@bot.event
async def on_member_join(member):

    config = await get_config(member.guild.id)

    if not config:
        return

    welcome_channel = config[1]
    autorole = config[4]

    if welcome_channel:

        channel = member.guild.get_channel(welcome_channel)

        if channel:

            embed = make_embed(
                "👋 Welcome!",
                f"Welcome {member.mention} to **{member.guild.name}**!"
            )

            await channel.send(embed=embed)

    if autorole:

        role = member.guild.get_role(autorole)

        if role:

            try:
                await member.add_roles(role)
            except discord.Forbidden:
                logger.warning("Could not assign autorole.")


@bot.event
async def on_message(message):

    if message.author.bot or not message.guild:
        return

    await ensure_user(
        message.guild.id,
        message.author.id
    )

    await bot.process_commands(message)


# ============================================================
# ERROR HANDLING
# ============================================================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingPermissions):

        await ctx.send(
            embed=make_embed(
                "⛔ Missing Permissions",
                "You don't have permission to use this command.",
                ERROR
            )
        )

        return

    if isinstance(error, commands.MissingRequiredArgument):

        await ctx.send(
            f"Missing argument: `{error.param.name}`",
            ephemeral=False
        )

        return

    logger.error(
        f"Command error: {error}",
        exc_info=error
    )

    await ctx.send(
        embed=make_embed(
            "⚠️ Command Error",
            "Something went wrong while executing this command.",
            ERROR
        )
    )


# ============================================================
# STARTUP
# ============================================================

async def main():

    if not TOKEN:

        raise RuntimeError(
            "DISCORD_TOKEN is missing from environment variables."
        )

    async with bot:

        await bot.start(TOKEN)


# ============================================================
#             MALARVAADI ADVANCED MODERATION
# ============================================================

async def moderation_log(guild, title, description):

    config = await get_config(guild.id)

    if not config or not config[5]:
        return

    channel = guild.get_channel(config[5])

    if channel:
        try:
            await channel.send(
                embed=make_embed(title, description, WARNING)
            )
        except discord.HTTPException:
            logger.warning("Moderation log delivery failed.")


def valid_target(ctx, member):

    if member.id == ctx.author.id:
        return False

    if member.id == bot.user.id:
        return False

    if member == ctx.guild.owner:
        return False

    if member.top_role >= ctx.author.top_role:
        return False

    if member.top_role >= ctx.guild.me.top_role:
        return False

    return True


# ------------------------------------------------------------
# BAN
# ------------------------------------------------------------

@bot.hybrid_command(
    name="ban",
    description="Ban a member from the server."
)
@commands.guild_only()
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):

    if not valid_target(ctx, member):
        return await ctx.send("❌ You cannot ban this member.")

    try:
        await member.send(
            f"You have been banned from **{ctx.guild.name}**.\n"
            f"Reason: {reason}"
        )
    except discord.HTTPException:
        pass

    await member.ban(reason=f"{ctx.author}: {reason}")

    await moderation_log(
        ctx.guild,
        "🔨 Member Banned",
        f"**Member:** {member} (`{member.id}`)\n"
        f"**Moderator:** {ctx.author.mention}\n"
        f"**Reason:** {reason}"
    )

    await ctx.send(f"🔨 **{member}** has been banned.")


# ------------------------------------------------------------
# KICK
# ------------------------------------------------------------

@bot.hybrid_command(
    name="kick",
    description="Kick a member from the server."
)
@commands.guild_only()
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):

    if not valid_target(ctx, member):
        return await ctx.send("❌ You cannot kick this member.")

    try:
        await member.send(
            f"You have been kicked from **{ctx.guild.name}**.\n"
            f"Reason: {reason}"
        )
    except discord.HTTPException:
        pass

    await member.kick(reason=f"{ctx.author}: {reason}")

    await moderation_log(
        ctx.guild,
        "👢 Member Kicked",
        f"**Member:** {member}\n"
        f"**Moderator:** {ctx.author.mention}\n"
        f"**Reason:** {reason}"
    )

    await ctx.send(f"👢 **{member}** has been kicked.")


# ------------------------------------------------------------
# TIMEOUT
# ------------------------------------------------------------

@bot.hybrid_command(
    name="timeout",
    description="Timeout a member."
)
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def timeout(
    ctx,
    member: discord.Member,
    minutes: int,
    *,
    reason="No reason provided"
):

    if not valid_target(ctx, member):
        return await ctx.send("❌ You cannot timeout this member.")

    if not 1 <= minutes <= 40320:
        return await ctx.send(
            "❌ Duration must be between 1 and 40320 minutes."
        )

    await member.timeout(
        timedelta(minutes=minutes),
        reason=f"{ctx.author}: {reason}"
    )

    await moderation_log(
        ctx.guild,
        "🔇 Member Timed Out",
        f"**Member:** {member.mention}\n"
        f"**Duration:** {minutes} minutes\n"
        f"**Moderator:** {ctx.author.mention}\n"
        f"**Reason:** {reason}"
    )

    await ctx.send(
        f"🔇 {member.mention} has been timed out for "
        f"**{minutes} minutes**."
    )


# ------------------------------------------------------------
# REMOVE TIMEOUT
# ------------------------------------------------------------

@bot.hybrid_command(
    name="untimeout",
    description="Remove a member's timeout."
)
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def untimeout(ctx, member: discord.Member):

    if not valid_target(ctx, member):
        return await ctx.send("❌ You cannot modify this member.")

    await member.timeout(
        None,
        reason=f"Timeout removed by {ctx.author}"
    )

    await moderation_log(
        ctx.guild,
        "🔊 Timeout Removed",
        f"**Member:** {member.mention}\n"
        f"**Moderator:** {ctx.author.mention}"
    )

    await ctx.send(f"🔊 Timeout removed for {member.mention}.")


# ------------------------------------------------------------
# WARN
# ------------------------------------------------------------

@bot.hybrid_command(
    name="warn",
    description="Issue a warning to a member."
)
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):

    if not valid_target(ctx, member):
        return await ctx.send("❌ You cannot warn this member.")

    await ensure_user(ctx.guild.id, member.id)

    await bot.db.execute(
        """
        INSERT INTO warnings
        (guild_id, user_id, moderator_id, reason, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            ctx.guild.id,
            member.id,
            ctx.author.id,
            reason,
            int(time.time())
        )
    )

    await bot.db.execute(
        """
        UPDATE users
        SET warnings = warnings + 1
        WHERE guild_id = ? AND user_id = ?
        """,
        (ctx.guild.id, member.id)
    )

    await bot.db.commit()

    try:
        await member.send(
            f"⚠️ You received a warning in **{ctx.guild.name}**.\n"
            f"Reason: {reason}"
        )
    except discord.HTTPException:
        pass

    await moderation_log(
        ctx.guild,
        "⚠️ Member Warned",
        f"**Member:** {member.mention}\n"
        f"**Moderator:** {ctx.author.mention}\n"
        f"**Reason:** {reason}"
    )

    await ctx.send(f"⚠️ {member.mention} has received a warning.")


# ------------------------------------------------------------
# VIEW WARNINGS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="warnings",
    description="View a member's warning history."
)
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
async def warnings(ctx, member: discord.Member):

    cursor = await bot.db.execute(
        """
        SELECT moderator_id, reason, created_at
        FROM warnings
        WHERE guild_id = ? AND user_id = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (ctx.guild.id, member.id)
    )

    records = await cursor.fetchall()

    if not records:
        return await ctx.send("✅ This member has no warnings.")

    description = ""

    for index, record in enumerate(records, 1):

        moderator_id, reason, created_at = record

        timestamp = f"<t:{created_at}:R>"

        description += (
            f"**{index}.** {reason}\n"
            f"Moderator: <@{moderator_id}> • {timestamp}\n\n"
        )

    embed = make_embed(
        f"⚠️ Warning History — {member}",
        description
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# CLEAR WARNINGS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="clearwarnings",
    description="Clear a member's warning history."
)
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
async def clearwarnings(ctx, member: discord.Member):

    if not valid_target(ctx, member):
        return await ctx.send("❌ You cannot modify this member.")

    await bot.db.execute(
        "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
        (ctx.guild.id, member.id)
    )

    await bot.db.execute(
        """
        UPDATE users SET warnings = 0
        WHERE guild_id = ? AND user_id = ?
        """,
        (ctx.guild.id, member.id)
    )

    await bot.db.commit()

    await moderation_log(
        ctx.guild,
        "🧹 Warnings Cleared",
        f"**Member:** {member.mention}\n"
        f"**Moderator:** {ctx.author.mention}"
    )

    await ctx.send(f"🧹 Warnings cleared for {member.mention}.")


# ------------------------------------------------------------
# PURGE
# ------------------------------------------------------------

@bot.hybrid_command(
    name="purge",
    description="Bulk delete messages."
)
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def purge(ctx, amount: int):

    if not 1 <= amount <= 100:
        return await ctx.send(
            "❌ Choose an amount between 1 and 100."
        )

    extra = 1 if ctx.interaction is None else 0

    deleted = await ctx.channel.purge(
        limit=amount + extra
    )

    await moderation_log(
        ctx.guild,
        "🧹 Messages Purged",
        f"**Channel:** {ctx.channel.mention}\n"
        f"**Moderator:** {ctx.author.mention}\n"
        f"**Deleted:** {max(0, len(deleted) - extra)}"
    )

    await ctx.send(
        f"🧹 Deleted **{max(0, len(deleted) - extra)} messages**.",
        delete_after=5
    )


# ------------------------------------------------------------
# LOCK CHANNEL
# ------------------------------------------------------------

@bot.hybrid_command(
    name="lock",
    description="Lock the current channel."
)
@commands.guild_only()
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def lock(ctx):

    overwrite = ctx.channel.overwrites_for(
        ctx.guild.default_role
    )

    overwrite.send_messages = False

    await ctx.channel.set_permissions(
        ctx.guild.default_role,
        overwrite=overwrite,
        reason=f"Channel locked by {ctx.author}"
    )

    await ctx.send("🔒 This channel has been locked.")

    await moderation_log(
        ctx.guild,
        "🔒 Channel Locked",
        f"**Channel:** {ctx.channel.mention}\n"
        f"**Moderator:** {ctx.author.mention}"
    )


# ------------------------------------------------------------
# UNLOCK CHANNEL
# ------------------------------------------------------------

@bot.hybrid_command(
    name="unlock",
    description="Unlock the current channel."
)
@commands.guild_only()
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def unlock(ctx):

    overwrite = ctx.channel.overwrites_for(
        ctx.guild.default_role
    )

    overwrite.send_messages = None

    await ctx.channel.set_permissions(
        ctx.guild.default_role,
        overwrite=overwrite,
        reason=f"Channel unlocked by {ctx.author}"
    )

    await ctx.send("🔓 This channel has been unlocked.")

    await moderation_log(
        ctx.guild,
        "🔓 Channel Unlocked",
        f"**Channel:** {ctx.channel.mention}\n"
        f"**Moderator:** {ctx.author.mention}"
    )


# ------------------------------------------------------------
# SLOWMODE
# ------------------------------------------------------------

@bot.hybrid_command(
    name="slowmode",
    description="Configure channel slowmode."
)
@commands.guild_only()
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):

    if not 0 <= seconds <= 21600:
        return await ctx.send(
            "❌ Slowmode must be between 0 and 21600 seconds."
        )

    await ctx.channel.edit(
        slowmode_delay=seconds,
        reason=f"Slowmode changed by {ctx.author}"
    )

    await ctx.send(
        f"⏱️ Slowmode set to **{seconds} seconds**."
    )

    await moderation_log(
        ctx.guild,
        "⏱️ Slowmode Updated",
        f"**Channel:** {ctx.channel.mention}\n"
        f"**Duration:** {seconds} seconds\n"
        f"**Moderator:** {ctx.author.mention}"
    )


# ============================================================
# END OF MODERATION ENGINE
# ============================================================
# ============================================================
#          MALARVAADI ADVANCED AUTOMOD ENGINE
# ============================================================

AUTOMOD_SETTINGS = {
    "enabled": True,
    "max_messages": 6,
    "interval": 5,
    "max_mentions": 5,
    "max_emojis": 12,
    "duplicate_limit": 3,
    "timeout_minutes": 5,
    "block_invites": True,
    "bad_words": []
}

MESSAGE_HISTORY = defaultdict(list)
DUPLICATE_HISTORY = defaultdict(list)
VIOLATIONS = defaultdict(list)


async def automod_violation(message, reason):

    guild = message.guild
    member = message.author

    now = time.time()

    VIOLATIONS[(guild.id, member.id)] = [
        timestamp
        for timestamp in VIOLATIONS[(guild.id, member.id)]
        if now - timestamp < 300
    ]

    VIOLATIONS[(guild.id, member.id)].append(now)

    try:
        await message.delete()
    except discord.HTTPException:
        pass

    await moderation_log(
        guild,
        "🚨 AutoMod Violation",
        f"**Member:** {member.mention}\n"
        f"**Channel:** {message.channel.mention}\n"
        f"**Violation:** {reason}"
    )

    violations = len(VIOLATIONS[(guild.id, member.id)])

    if violations >= 3:

        try:
            await member.timeout(
                timedelta(minutes=AUTOMOD_SETTINGS["timeout_minutes"]),
                reason=f"Malarvaadi AutoMod: {reason}"
            )

            await moderation_log(
                guild,
                "🔇 AutoMod Timeout",
                f"**Member:** {member.mention}\n"
                f"**Duration:** {AUTOMOD_SETTINGS['timeout_minutes']} minutes\n"
                f"**Reason:** Repeated AutoMod violations"
            )

            VIOLATIONS[(guild.id, member.id)].clear()

        except discord.HTTPException:
            logger.warning("AutoMod timeout failed.")


def contains_invite(content):

    pattern = (
        r"(?:https?://)?(?:www\.)?"
        r"(?:discord\.gg|discord(?:app)?\.com/invite)/"
        r"[a-zA-Z0-9-]+"
    )

    return bool(re.search(pattern, content, re.IGNORECASE))


def count_emojis(content):

    return sum(
        1 for character in content
        if ord(character) > 0x1F000
    )


async def process_automod(message):

    if not AUTOMOD_SETTINGS["enabled"]:
        return False

    if not message.guild:
        return False

    member = message.author

    if member.bot:
        return False

    if member.guild_permissions.manage_messages:
        return False

    now = time.time()

    key = (message.guild.id, member.id)

    # MESSAGE FLOOD DETECTION

    MESSAGE_HISTORY[key] = [
        timestamp
        for timestamp in MESSAGE_HISTORY[key]
        if now - timestamp < AUTOMOD_SETTINGS["interval"]
    ]

    MESSAGE_HISTORY[key].append(now)

    if len(MESSAGE_HISTORY[key]) > AUTOMOD_SETTINGS["max_messages"]:

        await automod_violation(message, "Message flooding")
        return True

    # DUPLICATE MESSAGE DETECTION

    content = message.content.strip().lower()

    if len(content) >= 5:

        DUPLICATE_HISTORY[key] = [
            item for item in DUPLICATE_HISTORY[key]
            if now - item[1] < 30
        ]

        DUPLICATE_HISTORY[key].append((content, now))

        duplicates = sum(
            1 for item in DUPLICATE_HISTORY[key]
            if item[0] == content
        )

        if duplicates >= AUTOMOD_SETTINGS["duplicate_limit"]:

            await automod_violation(message, "Repeated duplicate messages")
            return True

    # MENTION SPAM

    if len(message.mentions) > AUTOMOD_SETTINGS["max_mentions"]:

        await automod_violation(message, "Mention spam")
        return True

    # EMOJI SPAM

    if count_emojis(content) > AUTOMOD_SETTINGS["max_emojis"]:

        await automod_violation(message, "Excessive emojis")
        return True

    # INVITE FILTER

    if AUTOMOD_SETTINGS["block_invites"] and contains_invite(content):

        await automod_violation(message, "Discord invite link")
        return True

    # BAD WORD FILTER

    for word in AUTOMOD_SETTINGS["bad_words"]:

        if re.search(
            rf"(?<!\w){re.escape(word)}(?!\w)",
            content,
            re.IGNORECASE
        ):

            await automod_violation(message, "Filtered language")
            return True

    return False


# ------------------------------------------------------------
# AUTOMOD COMMANDS
# ------------------------------------------------------------

@bot.hybrid_group(
    name="automod",
    description="Manage Malarvaadi AutoMod.",
    invoke_without_command=True
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def automod(ctx):

    embed = make_embed(
        "🛡️ Malarvaadi AutoMod",
        "Advanced automatic server protection."
    )

    for setting, value in AUTOMOD_SETTINGS.items():

        embed.add_field(
            name=setting.replace("_", " ").title(),
            value=str(value),
            inline=True
        )

    await ctx.send(embed=embed)


@automod.command(name="enable")
async def automod_enable(ctx):

    AUTOMOD_SETTINGS["enabled"] = True

    await ctx.send("✅ AutoMod enabled.")


@automod.command(name="disable")
async def automod_disable(ctx):

    AUTOMOD_SETTINGS["enabled"] = False

    await ctx.send("⚠️ AutoMod disabled.")


@automod.command(name="invites")
async def automod_invites(ctx, enabled: bool):

    AUTOMOD_SETTINGS["block_invites"] = enabled

    await ctx.send(
        f"Invite filtering: **{'Enabled' if enabled else 'Disabled'}**"
    )


@automod.command(name="badword")
async def automod_badword(ctx, action: str, *, word: str):

    if action.lower() == "add":

        word = word.strip().lower()

        if len(word) > 50 or len(word) < 2:
            return await ctx.send("❌ Word length must be 2–50 characters.")

        if word not in AUTOMOD_SETTINGS["bad_words"]:
            AUTOMOD_SETTINGS["bad_words"].append(word)

        await ctx.send("✅ Filtered word added.")

    elif action.lower() == "remove":

        word = word.strip().lower()

        if word in AUTOMOD_SETTINGS["bad_words"]:
            AUTOMOD_SETTINGS["bad_words"].remove(word)

            await ctx.send("✅ Filtered word removed.")
        else:
            await ctx.send("❌ Word not found.")

    else:

        await ctx.send("Use `add` or `remove`.")


# ------------------------------------------------------------
# AUTOMOD EVENT INTEGRATION
# ------------------------------------------------------------

@bot.listen("on_message")
async def malarvaadi_automod_listener(message):

    if await process_automod(message):
        return


# ============================================================
# END OF AUTOMOD ENGINE
# ============================================================
# ============================================================
#              MALARVAADI ADVANCED ECONOMY
# ============================================================

ECONOMY_CONFIG = {
    "daily_reward": 500,
    "weekly_reward": 2500,
    "work_min": 100,
    "work_max": 800,
    "crime_min": 200,
    "crime_max": 1500,
    "rob_chance": 0.45,
    "rob_penalty": 500,
    "currency": "Coins"
}


async def economy_user(guild_id, user_id):

    await ensure_user(guild_id, user_id)

    cursor = await bot.db.execute(
        """
        SELECT wallet, bank, last_daily
        FROM users
        WHERE guild_id = ? AND user_id = ?
        """,
        (guild_id, user_id)
    )

    return await cursor.fetchone()


async def economy_update(guild_id, user_id, wallet=0, bank=0):

    await ensure_user(guild_id, user_id)

    await bot.db.execute(
        """
        UPDATE users
        SET wallet = wallet + ?, bank = bank + ?
        WHERE guild_id = ? AND user_id = ?
        """,
        (wallet, bank, guild_id, user_id)
    )

    await bot.db.commit()


def economy_embed(title, description):

    return make_embed(
        f"💰 {title}",
        description,
        SUCCESS
    )


# ------------------------------------------------------------
# BALANCE
# ------------------------------------------------------------

@bot.hybrid_command(
    name="balance",
    aliases=["bal"],
    description="Check your wallet and bank balance."
)
@commands.guild_only()
async def balance(ctx, member: discord.Member = None):

    member = member or ctx.author

    wallet, bank, _ = await economy_user(
        ctx.guild.id,
        member.id
    )

    total = wallet + bank

    embed = economy_embed(
        "Account Balance",
        f"**Account Holder:** {member.mention}\n\n"
        f"👛 Wallet: `{wallet:,}` Coins\n"
        f"🏦 Bank: `{bank:,}` Coins\n"
        f"💎 Net Worth: `{total:,}` Coins"
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# DAILY REWARD
# ------------------------------------------------------------

@bot.hybrid_command(
    name="daily",
    description="Collect your daily reward."
)
@commands.guild_only()
async def daily(ctx):

    await ensure_user(ctx.guild.id, ctx.author.id)

    now = int(time.time())

    wallet, bank, last_daily = await economy_user(
        ctx.guild.id,
        ctx.author.id
    )

    remaining = 86400 - (now - last_daily)

    if remaining > 0:

        hours, remainder = divmod(remaining, 3600)
        minutes = remainder // 60

        return await ctx.send(
            f"⏳ Your next daily reward is available in "
            f"**{hours}h {minutes}m**."
        )

    reward = ECONOMY_CONFIG["daily_reward"]

    await economy_update(
        ctx.guild.id,
        ctx.author.id,
        wallet=reward
    )

    await bot.db.execute(
        """
        UPDATE users SET last_daily = ?
        WHERE guild_id = ? AND user_id = ?
        """,
        (now, ctx.guild.id, ctx.author.id)
    )

    await bot.db.commit()

    await ctx.send(
        embed=economy_embed(
            "Daily Reward",
            f"🎁 You collected **{reward:,} Coins**!"
        )
    )


# ------------------------------------------------------------
# WORK
# ------------------------------------------------------------

@bot.hybrid_command(
    name="work",
    description="Work to earn money."
)
@commands.guild_only()
@commands.cooldown(1, 30, commands.BucketType.user)
async def work(ctx):

    reward = random.randint(
        ECONOMY_CONFIG["work_min"],
        ECONOMY_CONFIG["work_max"]
    )

    jobs = [
        "worked as a developer",
        "completed a delivery",
        "worked at a shop",
        "designed a website",
        "completed a freelance project",
        "helped a local business"
    ]

    job = random.choice(jobs)

    await economy_update(
        ctx.guild.id,
        ctx.author.id,
        wallet=reward
    )

    await ctx.send(
        embed=economy_embed(
            "Work Completed",
            f"💼 You {job}.\n"
            f"💰 Earnings: **{reward:,} Coins**"
        )
    )


# ------------------------------------------------------------
# DEPOSIT
# ------------------------------------------------------------

@bot.hybrid_command(
    name="deposit",
    aliases=["dep"],
    description="Deposit wallet money into your bank."
)
@commands.guild_only()
async def deposit(ctx, amount: str):

    wallet, bank, _ = await economy_user(
        ctx.guild.id,
        ctx.author.id
    )

    if amount.lower() in ("all", "max"):
        value = wallet
    else:
        try:
            value = int(amount)
        except ValueError:
            return await ctx.send("❌ Enter a valid amount.")

    if value <= 0 or value > wallet:
        return await ctx.send("❌ Insufficient wallet balance.")

    await economy_update(
        ctx.guild.id,
        ctx.author.id,
        wallet=-value,
        bank=value
    )

    await ctx.send(
        embed=economy_embed(
            "Deposit Successful",
            f"🏦 Deposited **{value:,} Coins**."
        )
    )


# ------------------------------------------------------------
# WITHDRAW
# ------------------------------------------------------------

@bot.hybrid_command(
    name="withdraw",
    aliases=["with"],
    description="Withdraw money from your bank."
)
@commands.guild_only()
async def withdraw(ctx, amount: str):

    wallet, bank, _ = await economy_user(
        ctx.guild.id,
        ctx.author.id
    )

    if amount.lower() in ("all", "max"):
        value = bank
    else:
        try:
            value = int(amount)
        except ValueError:
            return await ctx.send("❌ Enter a valid amount.")

    if value <= 0 or value > bank:
        return await ctx.send("❌ Insufficient bank balance.")

    await economy_update(
        ctx.guild.id,
        ctx.author.id,
        wallet=value,
        bank=-value
    )

    await ctx.send(
        embed=economy_embed(
            "Withdrawal Successful",
            f"👛 Withdrawn **{value:,} Coins**."
        )
    )


# ------------------------------------------------------------
# TRANSFER
# ------------------------------------------------------------

@bot.hybrid_command(
    name="pay",
    aliases=["transfer"],
    description="Transfer money to another member."
)
@commands.guild_only()
async def pay(ctx, member: discord.Member, amount: int):

    if member.bot or member.id == ctx.author.id:
        return await ctx.send("❌ Invalid recipient.")

    if amount <= 0:
        return await ctx.send("❌ Amount must be positive.")

    sender, _, _ = await economy_user(
        ctx.guild.id,
        ctx.author.id
    )

    if sender < amount:
        return await ctx.send("❌ Insufficient wallet balance.")

    await ensure_user(ctx.guild.id, member.id)

    async with bot.db.execute("BEGIN IMMEDIATE"):

        await bot.db.execute(
            """
            UPDATE users SET wallet = wallet - ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (amount, ctx.guild.id, ctx.author.id)
        )

        await bot.db.execute(
            """
            UPDATE users SET wallet = wallet + ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (amount, ctx.guild.id, member.id)
        )

        await bot.db.commit()

    await ctx.send(
        embed=economy_embed(
            "Transfer Completed",
            f"💸 {ctx.author.mention} sent "
            f"**{amount:,} Coins** to {member.mention}."
        )
    )


# ------------------------------------------------------------
# CRIME
# ------------------------------------------------------------

@bot.hybrid_command(
    name="crime",
    description="Take a risky job for extra money."
)
@commands.guild_only()
@commands.cooldown(1, 60, commands.BucketType.user)
async def crime(ctx):

    reward = random.randint(
        ECONOMY_CONFIG["crime_min"],
        ECONOMY_CONFIG["crime_max"]
    )

    if random.random() < 0.55:

        await economy_update(
            ctx.guild.id,
            ctx.author.id,
            wallet=reward
        )

        await ctx.send(
            embed=economy_embed(
                "Crime Successful",
                f"🕵️ You escaped successfully!\n"
                f"💰 Earned **{reward:,} Coins**."
            )
        )

    else:

        penalty = ECONOMY_CONFIG["rob_penalty"]

        wallet, bank, _ = await economy_user(
            ctx.guild.id,
            ctx.author.id
        )

        lost = min(wallet, penalty)

        await economy_update(
            ctx.guild.id,
            ctx.author.id,
            wallet=-lost
        )

        await ctx.send(
            embed=make_embed(
                "🚔 Crime Failed",
                f"You were caught!\n"
                f"💸 Lost **{lost:,} Coins**.",
                ERROR
            )
        )


# ------------------------------------------------------------
# ROBBERY
# ------------------------------------------------------------

@bot.hybrid_command(
    name="rob",
    description="Attempt to rob another member."
)
@commands.guild_only()
@commands.cooldown(1, 120, commands.BucketType.user)
async def rob(ctx, member: discord.Member):

    if member.bot or member.id == ctx.author.id:
        return await ctx.send("❌ Invalid target.")

    await ensure_user(ctx.guild.id, member.id)

    target_wallet, _, _ = await economy_user(
        ctx.guild.id,
        member.id
    )

    if target_wallet < 100:
        return await ctx.send("❌ Target has too little cash.")

    if random.random() < ECONOMY_CONFIG["rob_chance"]:

        stolen = random.randint(
            50,
            min(500, target_wallet)
        )

        await economy_update(
            ctx.guild.id,
            ctx.author.id,
            wallet=stolen
        )

        await economy_update(
            ctx.guild.id,
            member.id,
            wallet=-stolen
        )

        await ctx.send(
            embed=economy_embed(
                "Robbery Successful",
                f"🦹 You stole **{stolen:,} Coins** from "
                f"{member.mention}."
            )
        )

    else:

        penalty = min(
            300,
            (await economy_user(ctx.guild.id, ctx.author.id))[0]
        )

        await economy_update(
            ctx.guild.id,
            ctx.author.id,
            wallet=-penalty
        )

        await ctx.send(
            embed=make_embed(
                "🚨 Robbery Failed",
                f"You were caught and lost **{penalty:,} Coins**.",
                ERROR
            )
        )


# ------------------------------------------------------------
# LEADERBOARD
# ------------------------------------------------------------

@bot.hybrid_command(
    name="richest",
    aliases=["leaderboard"],
    description="View the richest members."
)
@commands.guild_only()
async def richest(ctx):

    cursor = await bot.db.execute(
        """
        SELECT user_id, wallet, bank, (wallet + bank) AS total
        FROM users
        WHERE guild_id = ?
        ORDER BY total DESC
        LIMIT 10
        """,
        (ctx.guild.id,)
    )

    records = await cursor.fetchall()

    if not records:
        return await ctx.send("No economy records found.")

    description = ""

    for index, row in enumerate(records, 1):

        user_id, wallet, bank, total = row

        description += (
            f"**{index}.** <@{user_id}> — "
            f"💰 `{total:,}` Coins\n"
        )

    await ctx.send(
        embed=economy_embed(
            "Richest Members",
            description
        )
    )


# ============================================================
# END OF ECONOMY ENGINE
# ============================================================

# ============================================================
#          MALARVAADI ADVANCED MARKETPLACE
# ============================================================

SHOP_ITEMS = {
    "wooden_sword": {
        "name": "Wooden Sword",
        "price": 500,
        "description": "A beginner's weapon.",
        "emoji": "⚔️"
    },
    "iron_sword": {
        "name": "Iron Sword",
        "price": 1500,
        "description": "A reliable combat weapon.",
        "emoji": "🗡️"
    },
    "shield": {
        "name": "Shield",
        "price": 1000,
        "description": "Protect yourself.",
        "emoji": "🛡️"
    },
    "health_potion": {
        "name": "Health Potion",
        "price": 300,
        "description": "A magical potion.",
        "emoji": "🧪"
    },
    "golden_crown": {
        "name": "Golden Crown",
        "price": 5000,
        "description": "A symbol of wealth.",
        "emoji": "👑"
    },
    "diamond": {
        "name": "Diamond",
        "price": 10000,
        "description": "A rare precious gem.",
        "emoji": "💎"
    },
    "pet_cat": {
        "name": "Pet Cat",
        "price": 2500,
        "description": "Your adorable companion.",
        "emoji": "🐈"
    },
    "magic_wand": {
        "name": "Magic Wand",
        "price": 7500,
        "description": "A mysterious magical item.",
        "emoji": "🪄"
    }
}


async def inventory_add(guild_id, user_id, item, quantity=1):

    await bot.db.execute(
        """
        INSERT INTO economy_inventory
        (guild_id, user_id, item, quantity)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id, item)
        DO UPDATE SET quantity = quantity + excluded.quantity
        """,
        (guild_id, user_id, item, quantity)
    )

    await bot.db.commit()


async def inventory_remove(guild_id, user_id, item, quantity=1):

    cursor = await bot.db.execute(
        """
        SELECT quantity FROM economy_inventory
        WHERE guild_id = ? AND user_id = ? AND item = ?
        """,
        (guild_id, user_id, item)
    )

    record = await cursor.fetchone()

    if not record or record[0] < quantity:
        return False

    await bot.db.execute(
        """
        UPDATE economy_inventory
        SET quantity = quantity - ?
        WHERE guild_id = ? AND user_id = ? AND item = ?
        """,
        (quantity, guild_id, user_id, item)
    )

    await bot.db.execute(
        """
        DELETE FROM economy_inventory
        WHERE guild_id = ? AND user_id = ? AND item = ?
        AND quantity <= 0
        """,
        (guild_id, user_id, item)
    )

    await bot.db.commit()

    return True


# ------------------------------------------------------------
# SHOP DISPLAY
# ------------------------------------------------------------

@bot.hybrid_command(
    name="shop",
    description="Browse the Malarvaadi marketplace."
)
@commands.guild_only()
async def shop(ctx):

    embed = make_embed(
        "🏪 Malarvaadi Marketplace",
        "Browse available items and purchase your favorites."
    )

    for item_id, item in SHOP_ITEMS.items():

        embed.add_field(
            name=f"{item['emoji']} {item['name']}",
            value=(
                f"{item['description']}\n"
                f"Price: **{item['price']:,} Coins**\n"
                f"ID: `{item_id}`"
            ),
            inline=True
        )

    embed.add_field(
        name="How to purchase",
        value="`+buy item_id quantity`\nExample: `+buy diamond 1`",
        inline=False
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# BUY ITEMS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="buy",
    description="Purchase an item from the marketplace."
)
@commands.guild_only()
async def buy(ctx, item_id: str, quantity: int = 1):

    item_id = item_id.lower()

    if item_id not in SHOP_ITEMS:
        return await ctx.send("❌ Item not found in the marketplace.")

    if not 1 <= quantity <= 100:
        return await ctx.send("❌ Quantity must be between 1 and 100.")

    item = SHOP_ITEMS[item_id]
    total_price = item["price"] * quantity

    wallet, bank, _ = await economy_user(
        ctx.guild.id,
        ctx.author.id
    )

    if wallet < total_price:
        return await ctx.send(
            f"❌ You need **{total_price:,} Coins** "
            f"but only have **{wallet:,} Coins**."
        )

    await economy_update(
        ctx.guild.id,
        ctx.author.id,
        wallet=-total_price
    )

    await inventory_add(
        ctx.guild.id,
        ctx.author.id,
        item_id,
        quantity
    )

    await ctx.send(
        embed=economy_embed(
            "Purchase Successful",
            f"{item['emoji']} Purchased **{quantity}x "
            f"{item['name']}**.\n"
            f"💰 Paid: **{total_price:,} Coins**."
        )
    )


# ------------------------------------------------------------
# INVENTORY
# ------------------------------------------------------------

@bot.hybrid_command(
    name="inventory",
    aliases=["inv", "bag"],
    description="View your personal inventory."
)
@commands.guild_only()
async def inventory(ctx, member: discord.Member = None):

    member = member or ctx.author

    cursor = await bot.db.execute(
        """
        SELECT item, quantity FROM economy_inventory
        WHERE guild_id = ? AND user_id = ?
        ORDER BY quantity DESC
        """,
        (ctx.guild.id, member.id)
    )

    records = await cursor.fetchall()

    if not records:
        return await ctx.send("🎒 This inventory is empty.")

    description = ""

    for item_id, quantity in records:

        item = SHOP_ITEMS.get(item_id)

        if not item:
            continue

        description += (
            f"{item['emoji']} **{item['name']}** "
            f"× `{quantity}`\n"
        )

    embed = make_embed(
        f"🎒 {member.display_name}'s Inventory",
        description or "No recognized items."
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# SELL ITEMS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="sell",
    description="Sell an item from your inventory."
)
@commands.guild_only()
async def sell(ctx, item_id: str, quantity: int = 1):

    item_id = item_id.lower()

    if item_id not in SHOP_ITEMS:
        return await ctx.send("❌ Unknown item.")

    if not 1 <= quantity <= 100:
        return await ctx.send("❌ Invalid quantity.")

    item = SHOP_ITEMS[item_id]

    removed = await inventory_remove(
        ctx.guild.id,
        ctx.author.id,
        item_id,
        quantity
    )

    if not removed:
        return await ctx.send("❌ You don't own enough of this item.")

    earnings = (item["price"] * quantity) // 2

    await economy_update(
        ctx.guild.id,
        ctx.author.id,
        wallet=earnings
    )

    await ctx.send(
        embed=economy_embed(
            "Item Sold",
            f"{item['emoji']} Sold **{quantity}x "
            f"{item['name']}**.\n"
            f"💰 Received: **{earnings:,} Coins**."
        )
    )


# ------------------------------------------------------------
# GIFT ITEMS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="giftitem",
    description="Gift an inventory item to another member."
)
@commands.guild_only()
async def giftitem(
    ctx,
    member: discord.Member,
    item_id: str,
    quantity: int = 1
):

    if member.bot or member.id == ctx.author.id:
        return await ctx.send("❌ Invalid recipient.")

    if item_id not in SHOP_ITEMS:
        return await ctx.send("❌ Unknown item.")

    if not 1 <= quantity <= 100:
        return await ctx.send("❌ Invalid quantity.")

    removed = await inventory_remove(
        ctx.guild.id,
        ctx.author.id,
        item_id,
        quantity
    )

    if not removed:
        return await ctx.send("❌ You don't own enough items.")

    await inventory_add(
        ctx.guild.id,
        member.id,
        item_id,
        quantity
    )

    item = SHOP_ITEMS[item_id]

    await ctx.send(
        embed=economy_embed(
            "Gift Delivered",
            f"{item['emoji']} {ctx.author.mention} gifted "
            f"**{quantity}x {item['name']}** to {member.mention}."
        )
    )


# ------------------------------------------------------------
# ADMIN ITEM CREATION
# ------------------------------------------------------------

@bot.hybrid_command(
    name="addshopitem",
    description="Add an item to the marketplace."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def addshopitem(
    ctx,
    item_id: str,
    price: int,
    *,
    name: str
):

    item_id = item_id.lower()

    if not re.fullmatch(r"[a-z0-9_]{2,32}", item_id):
        return await ctx.send("❌ Invalid item ID.")

    if item_id in SHOP_ITEMS:
        return await ctx.send("❌ This item already exists.")

    if not 1 <= price <= 1000000000:
        return await ctx.send("❌ Invalid item price.")

    if len(name) > 80:
        return await ctx.send("❌ Item name is too long.")

    SHOP_ITEMS[item_id] = {
        "name": name,
        "price": price,
        "description": "Custom marketplace item.",
        "emoji": "📦"
    }

    await ctx.send(
        f"✅ Added **{name}** to the marketplace for "
        f"**{price:,} Coins**."
    )


# ------------------------------------------------------------
# USE ITEMS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="useitem",
    description="Use an item from your inventory."
)
@commands.guild_only()
async def useitem(ctx, item_id: str):

    if item_id not in SHOP_ITEMS:
        return await ctx.send("❌ Unknown item.")

    if item_id not in ("health_potion",):
        return await ctx.send(
            "ℹ️ This item has no usable effect yet."
        )

    removed = await inventory_remove(
        ctx.guild.id,
        ctx.author.id,
        item_id,
        1
    )

    if not removed:
        return await ctx.send("❌ You don't own this item.")

    await ctx.send(
        "🧪 You used a Health Potion! "
        "Your character feels refreshed."
    )


# ============================================================
# END OF MARKETPLACE ENGINE
# ============================================================

# ============================================================
#             MALARVAADI ADVANCED LEVELING
# ============================================================

XP_CONFIG = {
    "enabled": True,
    "min_xp": 15,
    "max_xp": 25,
    "cooldown": 60,
    "announcement": True,
    "announcement_channel": None,
    "multiplier": 1.0
}

XP_COOLDOWNS = {}
LEVEL_ROLES = {}

RANK_NAMES = {
    1: "Peasant",
    5: "Merchant",
    10: "Foot Soldier",
    20: "Captain",
    35: "Commander",
    50: "Warlord"
}


def xp_required(level):
    return 100 * (level ** 2)


def get_rank_name(level):

    rank = "Newcomer"

    for required_level, name in sorted(RANK_NAMES.items()):

        if level >= required_level:
            rank = name

    return rank


async def get_xp_data(guild_id, user_id):

    await ensure_user(guild_id, user_id)

    cursor = await bot.db.execute(
        """
        SELECT xp, level FROM users
        WHERE guild_id = ? AND user_id = ?
        """,
        (guild_id, user_id)
    )

    return await cursor.fetchone()


async def award_xp(member, amount):

    guild_id = member.guild.id
    user_id = member.id

    await ensure_user(guild_id, user_id)

    cursor = await bot.db.execute(
        """
        SELECT xp, level FROM users
        WHERE guild_id = ? AND user_id = ?
        """,
        (guild_id, user_id)
    )

    xp, level = await cursor.fetchone()

    new_xp = xp + amount
    new_level = level

    while new_xp >= xp_required(new_level + 1):
        new_level += 1

    await bot.db.execute(
        """
        UPDATE users
        SET xp = ?, level = ?
        WHERE guild_id = ? AND user_id = ?
        """,
        (new_xp, new_level, guild_id, user_id)
    )

    await bot.db.commit()

    if new_level > level:

        await level_up_announcement(
            member,
            new_level
        )

        await assign_level_role(
            member,
            new_level
        )


async def level_up_announcement(member, level):

    if not XP_CONFIG["announcement"]:
        return

    channel_id = XP_CONFIG["announcement_channel"]

    channel = (
        member.guild.get_channel(channel_id)
        if channel_id
        else member.guild.system_channel
    )

    if not channel:
        return

    embed = make_embed(
        "🎉 LEVEL UP!",
        f"Congratulations {member.mention}!\n\n"
        f"You reached **Level {level}**!\n"
        f"Rank: **{get_rank_name(level)}**"
    )

    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        logger.warning("Level-up announcement failed.")


async def assign_level_role(member, level):

    guild_roles = LEVEL_ROLES.get(member.guild.id, {})

    for required_level, role_id in guild_roles.items():

        if level < required_level:
            continue

        role = member.guild.get_role(role_id)

        if not role:
            continue

        try:
            await member.add_roles(
                role,
                reason="Malarvaadi level reward"
            )
        except discord.HTTPException:
            logger.warning("Level reward assignment failed.")


# ------------------------------------------------------------
# XP MESSAGE INTEGRATION
# ------------------------------------------------------------

@bot.listen("on_message")
async def malarvaadi_xp_listener(message):

    if not XP_CONFIG["enabled"]:
        return

    if not message.guild or message.author.bot:
        return

    key = (message.guild.id, message.author.id)
    now = time.time()

    last_message = XP_COOLDOWNS.get(key, 0)

    if now - last_message < XP_CONFIG["cooldown"]:
        return

    XP_COOLDOWNS[key] = now

    amount = random.randint(
        XP_CONFIG["min_xp"],
        XP_CONFIG["max_xp"]
    )

    amount = int(amount * XP_CONFIG["multiplier"])

    if amount > 0:
        await award_xp(message.author, amount)


# ------------------------------------------------------------
# RANK COMMAND
# ------------------------------------------------------------

@bot.hybrid_command(
    name="rank",
    description="View your XP and rank."
)
@commands.guild_only()
async def rank(ctx, member: discord.Member = None):

    member = member or ctx.author

    xp, level = await get_xp_data(
        ctx.guild.id,
        member.id
    )

    current_requirement = xp_required(level + 1)
    previous_requirement = xp_required(level)

    progress = xp - previous_requirement
    required = current_requirement - previous_requirement

    percentage = min(100, int(progress / required * 100))

    filled = int(percentage / 10)
    bar = "🟩" * filled + "⬛" * (10 - filled)

    embed = make_embed(
        f"🏆 {member.display_name}'s Rank",
        f"**Rank:** {get_rank_name(level)}\n"
        f"**Level:** {level}\n"
        f"**Total XP:** {xp:,}\n\n"
        f"{bar} **{percentage}%**\n"
        f"`{progress:,} / {required:,} XP`"
    )

    embed.set_thumbnail(url=member.display_avatar.url)

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# LEADERBOARD
# ------------------------------------------------------------

@bot.hybrid_command(
    name="xpleaderboard",
    aliases=["topxp"],
    description="View the server XP leaderboard."
)
@commands.guild_only()
async def xpleaderboard(ctx):

    cursor = await bot.db.execute(
        """
        SELECT user_id, xp, level
        FROM users
        WHERE guild_id = ?
        ORDER BY level DESC, xp DESC
        LIMIT 10
        """,
        (ctx.guild.id,)
    )

    records = await cursor.fetchall()

    if not records:
        return await ctx.send("No XP records available.")

    description = ""

    for index, (user_id, xp, level) in enumerate(records, 1):

        description += (
            f"**{index}.** <@{user_id}> — "
            f"Level `{level}` • `{xp:,} XP`\n"
        )

    await ctx.send(
        embed=make_embed(
            "🏆 XP Leaderboard",
            description
        )
    )


# ------------------------------------------------------------
# ADMIN XP ADJUSTMENT
# ------------------------------------------------------------

@bot.hybrid_command(
    name="addxp",
    description="Give XP to a member."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def addxp(
    ctx,
    member: discord.Member,
    amount: int
):

    if not 1 <= amount <= 1000000:
        return await ctx.send("❌ XP amount must be between 1 and 1,000,000.")

    await award_xp(member, amount)

    await ctx.send(
        f"✅ Added **{amount:,} XP** to {member.mention}."
    )


# ------------------------------------------------------------
# LEVEL ROLE CONFIGURATION
# ------------------------------------------------------------

@bot.hybrid_command(
    name="setlevelrole",
    description="Configure a level reward role."
)
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
async def setlevelrole(
    ctx,
    level: int,
    role: discord.Role
):

    if level < 1:
        return await ctx.send("❌ Level must be positive.")

    if role >= ctx.guild.me.top_role:
        return await ctx.send("❌ That role is above the bot's role.")

    LEVEL_ROLES.setdefault(ctx.guild.id, {})
    LEVEL_ROLES[ctx.guild.id][level] = role.id

    await ctx.send(
        f"✅ {role.mention} will be awarded at level **{level}**."
    )


# ------------------------------------------------------------
# XP MULTIPLIER
# ------------------------------------------------------------

@bot.hybrid_command(
    name="setxpmultiplier",
    description="Configure the XP multiplier."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setxpmultiplier(ctx, multiplier: float):

    if not 0.1 <= multiplier <= 5:
        return await ctx.send("❌ Multiplier must be between 0.1 and 5.")

    XP_CONFIG["multiplier"] = multiplier

    await ctx.send(
        f"✅ XP multiplier set to **{multiplier}x**."
    )


# ============================================================
# END OF LEVELING ENGINE
# ============================================================

# ============================================================
#             MALARVAADI ADVANCED TICKETS
# ============================================================

import io
import discord


async def ensure_ticket_schema():

    migrations = {
        "support_role_id": "INTEGER",
        "ticket_category_id": "INTEGER",
        "ticket_panel_channel_id": "INTEGER",
        "ticket_number": "INTEGER DEFAULT 0",
        "ticket_reason": "TEXT",
        "closed_by": "INTEGER"
    }

    cursor = await bot.db.execute(
        "PRAGMA table_info(guild_config)"
    )

    existing = {row[1] for row in await cursor.fetchall()}

    for column, definition in migrations.items():

        if column not in existing:
            await bot.db.execute(
                f"ALTER TABLE guild_config ADD COLUMN {column} {definition}"
            )

    # Migrate missing columns in the tickets table
    cursor = await bot.db.execute("PRAGMA table_info(tickets)")
    existing_ticket_columns = {
        row[1] for row in await cursor.fetchall()
    }

    ticket_migrations = {
        "ticket_reason": "TEXT",
        "closed_by": "INTEGER"
    }

    for column, definition in ticket_migrations.items():
        if column not in existing_ticket_columns:
            await bot.db.execute(
                f"ALTER TABLE tickets ADD COLUMN {column} {definition}"
            )

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS ticket_counters (
            guild_id INTEGER PRIMARY KEY,
            last_number INTEGER DEFAULT 0
        )
    """)

    await bot.db.commit()


async def ticket_config(guild_id):

    await ensure_ticket_schema()

    cursor = await bot.db.execute(
        """
        SELECT support_role_id, ticket_category_id,
               ticket_panel_channel_id
        FROM guild_config
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    return await cursor.fetchone()


async def next_ticket_number(guild_id):

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO ticket_counters
        (guild_id, last_number)
        VALUES (?, 0)
        """,
        (guild_id,)
    )

    await bot.db.execute(
        """
        UPDATE ticket_counters
        SET last_number = last_number + 1
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    cursor = await bot.db.execute(
        """
        SELECT last_number FROM ticket_counters
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    result = await cursor.fetchone()
    await bot.db.commit()

    return result[0]


# ------------------------------------------------------------
# CREATE TICKET
# ------------------------------------------------------------

class TicketReasonModal(discord.ui.Modal):

    def __init__(self):
        super().__init__(
            title="Create Support Ticket",
            timeout=300
        )

        self.reason = discord.ui.TextInput(
            label="How can our team help you?",
            placeholder="Describe your issue...",
            style=discord.TextStyle.paragraph,
            min_length=5,
            max_length=1000
        )

        self.add_item(self.reason)

    async def on_submit(self, interaction):

        await create_ticket_channel(
            interaction,
            str(self.reason.value)
        )


async def create_ticket_channel(interaction, reason):

    guild = interaction.guild
    member = interaction.user

    if not guild:
        return await interaction.response.send_message(
            "Tickets can only be created inside a server.",
            ephemeral=True
        )

    await ensure_ticket_schema()

    cursor = await bot.db.execute(
        """
        SELECT channel_id FROM tickets
        WHERE guild_id = ? AND user_id = ? AND status = 'open'
        """,
        (guild.id, member.id)
    )

    if await cursor.fetchone():

        return await interaction.response.send_message(
            "❌ You already have an open ticket.",
            ephemeral=True
        )

    config = await ticket_config(guild.id)

    if not config or not config[0]:

        return await interaction.response.send_message(
            "❌ Tickets haven't been configured by staff.",
            ephemeral=True
        )

    staff_role = guild.get_role(config[0])

    if not staff_role:

        return await interaction.response.send_message(
            "❌ The configured support role no longer exists.",
            ephemeral=True
        )

    category = guild.get_channel(config[1]) if config[1] else None

    number = await next_ticket_number(guild.id)

    safe_name = re.sub(
        r"[^a-z0-9-]",
        "-",
        member.display_name.lower()
    )[:20].strip("-") or "member"

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),
        member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True
        ),
        staff_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_messages=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True
        )
    }

    await interaction.response.defer(ephemeral=True)

    try:

        channel = await guild.create_text_channel(
            name=f"ticket-{number:04d}-{safe_name}",
            category=category if isinstance(
                category, discord.CategoryChannel
            ) else None,
            overwrites=overwrites,
            topic=f"Malarvaadi ticket #{number} | User ID: {member.id}"
        )

        await bot.db.execute(
            """
            INSERT INTO tickets
            (channel_id, guild_id, user_id, claimed_by,
             status, created_at, ticket_reason)
            VALUES (?, ?, ?, NULL, 'open', ?, ?)
            """,
            (
                channel.id,
                guild.id,
                member.id,
                int(time.time()),
                reason
            )
        )

        await bot.db.commit()

        embed = make_embed(
            f"🎟️ Support Ticket #{number:04d}",
            f"Welcome {member.mention}!\n\n"
            f"**Your request:**\n{reason}\n\n"
            "Our support team will assist you shortly."
        )

        embed.add_field(
            name="Ticket Owner",
            value=member.mention,
            inline=True
        )

        embed.add_field(
            name="Status",
            value="🟢 Open",
            inline=True
        )

        await channel.send(
            content=staff_role.mention,
            embed=embed,
            view=TicketControlView()
        )

        await interaction.followup.send(
            f"✅ Your ticket has been created: {channel.mention}",
            ephemeral=True
        )

    except (discord.HTTPException, aiosqlite.Error) as error:

        logger.exception("Ticket creation failed")

        await interaction.followup.send(
            "❌ Ticket creation failed. Please contact staff.",
            ephemeral=True
        )


# ------------------------------------------------------------
# TICKET PANEL
# ------------------------------------------------------------

class TicketPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Create Ticket",
        emoji="🎟️",
        style=discord.ButtonStyle.primary,
        custom_id="malarvaadi:ticket:create"
    )
    async def create_ticket(self, interaction, button):

        await interaction.response.send_modal(
            TicketReasonModal()
        )


# ------------------------------------------------------------
# STAFF CLAIM
# ------------------------------------------------------------

class TicketControlView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    async def get_ticket(self, interaction):

        await ensure_ticket_schema()

        cursor = await bot.db.execute(
            """
            SELECT user_id, status, claimed_by
            FROM tickets
            WHERE channel_id = ? AND guild_id = ?
            """,
            (interaction.channel.id, interaction.guild.id)
        )

        return await cursor.fetchone()

    async def staff_check(self, interaction):

        config = await ticket_config(interaction.guild.id)

        if not config or not config[0]:
            return False

        role = interaction.guild.get_role(config[0])

        if not role:
            return False

        return (
            interaction.user.guild_permissions.manage_guild
            or role in interaction.user.roles
        )

    @discord.ui.button(
        label="Claim",
        emoji="🙋",
        style=discord.ButtonStyle.success,
        custom_id="malarvaadi:ticket:claim"
    )
    async def claim(self, interaction, button):

        if not await self.staff_check(interaction):

            return await interaction.response.send_message(
                "❌ Only support staff can claim tickets.",
                ephemeral=True
            )

        record = await self.get_ticket(interaction)

        if not record or record[1] != "open":

            return await interaction.response.send_message(
                "This ticket is not open.",
                ephemeral=True
            )

        if record[2]:

            return await interaction.response.send_message(
                f"Already claimed by <@{record[2]}>.",
                ephemeral=True
            )

        await bot.db.execute(
            """
            UPDATE tickets SET claimed_by = ?
            WHERE channel_id = ?
            """,
            (interaction.user.id, interaction.channel.id)
        )

        await bot.db.commit()

        await interaction.response.send_message(
            f"🙋 Ticket claimed by {interaction.user.mention}."
        )

    # --------------------------------------------------------
    # CLOSE
    # --------------------------------------------------------

    @discord.ui.button(
        label="Close",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="malarvaadi:ticket:close"
    )
    async def close(self, interaction, button):

        record = await self.get_ticket(interaction)

        if not record or record[1] != "open":

            return await interaction.response.send_message(
                "Ticket is already closed.",
                ephemeral=True
            )

        is_owner = interaction.user.id == record[0]
        is_staff = await self.staff_check(interaction)

        if not is_owner and not is_staff:

            return await interaction.response.send_message(
                "❌ You cannot close this ticket.",
                ephemeral=True
            )

        await interaction.response.defer()

        await bot.db.execute(
            """
            UPDATE tickets
            SET status = 'closed', closed_by = ?
            WHERE channel_id = ?
            """,
            (interaction.user.id, interaction.channel.id)
        )

        await bot.db.commit()

        overwrite = interaction.channel.overwrites_for(
            interaction.guild.get_member(record[0])
            or interaction.guild.default_role
        )

        overwrite.send_messages = False

        await interaction.channel.set_permissions(
            interaction.guild.get_member(record[0])
            or interaction.guild.default_role,
            overwrite=overwrite
        )

        await interaction.followup.send(
            "🔒 Ticket closed. Staff can reopen it if necessary.",
            view=TicketClosedView()
        )

    # --------------------------------------------------------
    # TRANSCRIPT
    # --------------------------------------------------------

    @discord.ui.button(
        label="Transcript",
        emoji="📄",
        style=discord.ButtonStyle.secondary,
        custom_id="malarvaadi:ticket:transcript"
    )
    async def transcript(self, interaction, button):

        if not await self.staff_check(interaction):

            return await interaction.response.send_message(
                "❌ Only support staff can export transcripts.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        messages = []

        async for message in interaction.channel.history(
            limit=1000,
            oldest_first=True
        ):

            content = message.clean_content or "[No text content]"

            messages.append(
                f"[{message.created_at.isoformat()}] "
                f"{message.author} ({message.author.id}): "
                f"{content}"
            )

        output = "\n".join(messages)

        file = discord.File(
            io.BytesIO(output.encode("utf-8")),
            filename=f"ticket-{interaction.channel.id}.txt"
        )

        await interaction.followup.send(
            "📄 Ticket transcript:",
            file=file,
            ephemeral=True
        )


# ------------------------------------------------------------
# REOPEN TICKET
# ------------------------------------------------------------

class TicketClosedView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Reopen Ticket",
        emoji="🔓",
        style=discord.ButtonStyle.success,
        custom_id="malarvaadi:ticket:reopen"
    )
    async def reopen(self, interaction, button):

        await ensure_ticket_schema()

        if not await TicketControlView().staff_check(interaction):

            return await interaction.response.send_message(
                "❌ Only support staff can reopen tickets.",
                ephemeral=True
            )

        cursor = await bot.db.execute(
            """
            SELECT user_id, status FROM tickets
            WHERE channel_id = ? AND guild_id = ?
            """,
            (interaction.channel.id, interaction.guild.id)
        )

        record = await cursor.fetchone()

        if not record or record[1] != "closed":

            return await interaction.response.send_message(
                "This ticket cannot be reopened.",
                ephemeral=True
            )

        member = interaction.guild.get_member(record[0])

        if not member:
            return await interaction.response.send_message(
                "❌ Ticket owner is no longer in this server.",
                ephemeral=True
            )

        overwrite = interaction.channel.overwrites_for(member)
        overwrite.send_messages = True
        overwrite.view_channel = True

        await interaction.channel.set_permissions(
            member,
            overwrite=overwrite
        )

        await bot.db.execute(
            """
            UPDATE tickets
            SET status = 'open', closed_by = NULL
            WHERE channel_id = ?
            """,
            (interaction.channel.id,)
        )

        await bot.db.commit()

        await interaction.response.send_message(
            f"🔓 Ticket reopened by {interaction.user.mention}."
        )


# ------------------------------------------------------------
# SETUP TICKET PANEL
# ------------------------------------------------------------

@bot.hybrid_command(
    name="ticketsetup",
    description="Configure the Malarvaadi ticket system."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
@commands.bot_has_permissions(
    manage_channels=True,
    manage_roles=True,
    send_messages=True,
    embed_links=True
)
async def ticketsetup(
    ctx,
    channel: discord.TextChannel,
    staff_role: discord.Role,
    category: discord.CategoryChannel = None
):

    if staff_role >= ctx.guild.me.top_role:

        return await ctx.send(
            "❌ The staff role must be below the bot's highest role."
        )

    await ensure_ticket_schema()

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO guild_config (guild_id)
        VALUES (?)
        """,
        (ctx.guild.id,)
    )

    await bot.db.execute(
        """
        UPDATE guild_config
        SET support_role_id = ?,
            ticket_category_id = ?,
            ticket_panel_channel_id = ?
        WHERE guild_id = ?
        """,
        (
            staff_role.id,
            category.id if category else None,
            channel.id,
            ctx.guild.id
        )
    )

    await bot.db.commit()

    embed = make_embed(
        "🎟️ Malarvaadi Support Center",
        "Need assistance? Our support team is here to help!\n\n"
        "Press the button below to open a private support ticket.\n\n"
        "Please explain your issue clearly so our team can assist you."
    )

    await channel.send(
        embed=embed,
        view=TicketPanelView()
    )

    await ctx.send(
        f"✅ Ticket panel created in {channel.mention}."
    )


# ------------------------------------------------------------
# TICKET STATISTICS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="ticketstats",
    description="View ticket statistics."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def ticketstats(ctx):

    cursor = await bot.db.execute(
        """
        SELECT
            COUNT(*),
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END)
        FROM tickets
        WHERE guild_id = ?
        """,
        (ctx.guild.id,)
    )

    total, opened, closed = await cursor.fetchone()

    embed = make_embed(
        "📊 Ticket Statistics",
        f"🎟️ Total Tickets: **{total or 0}**\n"
        f"🟢 Open Tickets: **{opened or 0}**\n"
        f"🔒 Closed Tickets: **{closed or 0}**"
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# REGISTER PERSISTENT VIEWS
# ------------------------------------------------------------

bot.add_view(TicketPanelView())
bot.add_view(TicketControlView())
bot.add_view(TicketClosedView())


# ============================================================
# END OF TICKET ENGINE
# ============================================================

# ============================================================
#          MALARVAADI ADVANCED GIVEAWAY ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_giveaway_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS giveaway_entries (
            message_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY(message_id, user_id)
        )
    """)

    await bot.db.execute("""
        CREATE INDEX IF NOT EXISTS idx_giveaway_ending
        ON giveaways(ended, ends_at)
    """)

    await bot.db.commit()


def parse_duration(value):

    match = re.fullmatch(
        r"(\d+)(s|m|h|d)",
        value.lower()
    )

    if not match:
        return None

    amount = int(match.group(1))

    if amount <= 0:
        return None

    multiplier = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400
    }

    seconds = amount * multiplier[match.group(2)]

    if seconds < 60 or seconds > 30 * 86400:
        return None

    return seconds


# ------------------------------------------------------------
# GIVEAWAY EMBED
# ------------------------------------------------------------

async def giveaway_embed(message_id):

    cursor = await bot.db.execute(
        """
        SELECT guild_id, prize, winners, ends_at, ended
        FROM giveaways
        WHERE message_id = ?
        """,
        (message_id,)
    )

    record = await cursor.fetchone()

    if not record:
        return make_embed(
            "🎉 Giveaway",
            "Giveaway information unavailable."
        )

    guild_id, prize, winners, ends_at, ended = record

    cursor = await bot.db.execute(
        """
        SELECT COUNT(*) FROM giveaway_entries
        WHERE message_id = ?
        """,
        (message_id,)
    )

    entries = (await cursor.fetchone())[0]

    embed = make_embed(
        "🎉 MALARVAADI GIVEAWAY",
        f"**Prize:** {prize}\n\n"
        f"🏆 Winners: **{winners}**\n"
        f"👥 Entries: **{entries}**\n"
        f"🕒 Ends: <t:{ends_at}:R>\n\n"
        f"{'🔴 Giveaway ended' if ended else '🟢 Press the button to enter!'}"
    )

    embed.add_field(
        name="Giveaway ID",
        value=f"`{message_id}`",
        inline=False
    )

    return embed


# ------------------------------------------------------------
# GIVEAWAY ENTRY VIEW
# ------------------------------------------------------------

class GiveawayView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Enter Giveaway",
        emoji="🎉",
        style=discord.ButtonStyle.success,
        custom_id="malarvaadi:giveaway:enter"
    )
    async def enter(self, interaction, button):

        await ensure_giveaway_schema()

        message_id = interaction.message.id

        cursor = await bot.db.execute(
            """
            SELECT ends_at, ended, guild_id
            FROM giveaways
            WHERE message_id = ?
            """,
            (message_id,)
        )

        record = await cursor.fetchone()

        if not record:
            return await interaction.response.send_message(
                "❌ Giveaway not found.",
                ephemeral=True
            )

        ends_at, ended, guild_id = record

        if ended or time.time() >= ends_at:

            return await interaction.response.send_message(
                "⏰ This giveaway has ended.",
                ephemeral=True
            )

        if interaction.guild.id != guild_id:
            return await interaction.response.send_message(
                "❌ Invalid giveaway server.",
                ephemeral=True
            )

        try:

            await bot.db.execute(
                """
                INSERT INTO giveaway_entries
                (message_id, user_id)
                VALUES (?, ?)
                """,
                (message_id, interaction.user.id)
            )

            await bot.db.commit()

            await interaction.response.send_message(
                "🎉 You're entered into the giveaway!",
                ephemeral=True
            )

        except aiosqlite.IntegrityError:

            await interaction.response.send_message(
                "You're already entered in this giveaway!",
                ephemeral=True
            )


# ------------------------------------------------------------
# GIVEAWAY ENDING
# ------------------------------------------------------------

async def finish_giveaway(message_id):

    await ensure_giveaway_schema()

    cursor = await bot.db.execute(
        """
        SELECT guild_id, channel_id, prize,
               winners, ended
        FROM giveaways
        WHERE message_id = ?
        """,
        (message_id,)
    )

    record = await cursor.fetchone()

    if not record:
        return False

    guild_id, channel_id, prize, winner_count, ended = record

    if ended:
        return False

    cursor = await bot.db.execute(
        """
        SELECT user_id FROM giveaway_entries
        WHERE message_id = ?
        """,
        (message_id,)
    )

    entries = [row[0] for row in await cursor.fetchall()]

    winners = random.sample(
        entries,
        min(winner_count, len(entries))
    )

    await bot.db.execute(
        """
        UPDATE giveaways
        SET ended = 1
        WHERE message_id = ?
        """,
        (message_id,)
    )

    await bot.db.commit()

    channel = bot.get_channel(channel_id)

    if not channel:

        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            logger.warning("Giveaway channel unavailable.")
            return False

    try:
        message = await channel.fetch_message(message_id)

        embed = await giveaway_embed(message_id)

        embed.title = "🏁 GIVEAWAY ENDED"

        if winners:

            winner_text = ", ".join(
                f"<@{user_id}>" for user_id in winners
            )

            embed.add_field(
                name="🏆 Winner(s)",
                value=winner_text,
                inline=False
            )

            announcement = (
                f"🎉 Congratulations {winner_text}!\n"
                f"You won **{prize}**!"
            )

        else:

            embed.add_field(
                name="Result",
                value="No participants entered.",
                inline=False
            )

            announcement = "No valid giveaway entries."

        await message.edit(
            embed=embed,
            view=None
        )

        await channel.send(announcement)

    except discord.HTTPException:

        logger.exception("Giveaway announcement failed.")
        return False

    return True


# ------------------------------------------------------------
# AUTOMATIC GIVEAWAY SCHEDULER
# ------------------------------------------------------------

@tasks.loop(seconds=30)
async def giveaway_scheduler():

    if not bot.db:
        return

    cursor = await bot.db.execute(
        """
        SELECT message_id FROM giveaways
        WHERE ended = 0 AND ends_at <= ?
        """,
        (int(time.time()),)
    )

    records = await cursor.fetchall()

    for (message_id,) in records:

        try:
            await finish_giveaway(message_id)

        except Exception:
            logger.exception(
                f"Giveaway processing failed: {message_id}"
            )


@bot.listen("on_ready")
async def start_giveaway_scheduler():

    await ensure_giveaway_schema()

    if not giveaway_scheduler.is_running():
        giveaway_scheduler.start()


# ------------------------------------------------------------
# CREATE GIVEAWAY
# ------------------------------------------------------------

@bot.hybrid_command(
    name="giveaway",
    description="Create a new giveaway."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
@commands.bot_has_permissions(
    send_messages=True,
    embed_links=True,
    read_message_history=True
)
async def giveaway(
    ctx,
    channel: discord.TextChannel,
    duration: str,
    winners: int,
    *,
    prize: str
):

    seconds = parse_duration(duration)

    if seconds is None:

        return await ctx.send(
            "❌ Invalid duration. Examples: `10m`, `2h`, `1d`."
        )

    if not 1 <= winners <= 20:
        return await ctx.send(
            "❌ Winners must be between 1 and 20."
        )

    if not 2 <= len(prize) <= 150:
        return await ctx.send(
            "❌ Prize name must be 2–150 characters."
        )

    await ensure_giveaway_schema()

    ends_at = int(time.time()) + seconds

    embed = make_embed(
        "🎉 MALARVAADI GIVEAWAY",
        f"**Prize:** {prize}\n\n"
        f"🏆 Winners: **{winners}**\n"
        f"👥 Entries: **0**\n"
        f"🕒 Ends: <t:{ends_at}:R>\n\n"
        "Press the button below to enter!"
    )

    embed.add_field(
        name="Hosted By",
        value=ctx.author.mention,
        inline=False
    )

    message = await channel.send(
        embed=embed,
        view=GiveawayView()
    )

    await bot.db.execute(
        """
        INSERT INTO giveaways
        (message_id, guild_id, channel_id, prize,
         winners, ends_at, ended)
        VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (
            message.id,
            ctx.guild.id,
            channel.id,
            prize,
            winners,
            ends_at
        )
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Giveaway created successfully in {channel.mention}!"
    )


# ------------------------------------------------------------
# END GIVEAWAY MANUALLY
# ------------------------------------------------------------

@bot.hybrid_command(
    name="endgiveaway",
    description="End an active giveaway."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def endgiveaway(ctx, message_id: int):

    cursor = await bot.db.execute(
        """
        SELECT guild_id, ended FROM giveaways
        WHERE message_id = ?
        """,
        (message_id,)
    )

    record = await cursor.fetchone()

    if not record or record[0] != ctx.guild.id:
        return await ctx.send("❌ Giveaway not found.")

    if record[1]:
        return await ctx.send("❌ Giveaway already ended.")

    success = await finish_giveaway(message_id)

    if success:
        await ctx.send("🏁 Giveaway ended successfully.")
    else:
        await ctx.send(
            "❌ Giveaway could not be completed. Check the logs."
        )


# ------------------------------------------------------------
# REROLL WINNER
# ------------------------------------------------------------

@bot.hybrid_command(
    name="reroll",
    description="Select a replacement giveaway winner."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def reroll(ctx, message_id: int):

    cursor = await bot.db.execute(
        """
        SELECT guild_id, ended, winners, prize
        FROM giveaways
        WHERE message_id = ?
        """,
        (message_id,)
    )

    record = await cursor.fetchone()

    if not record or record[0] != ctx.guild.id:
        return await ctx.send("❌ Giveaway not found.")

    if not record[1]:
        return await ctx.send(
            "❌ End the giveaway before rerolling."
        )

    guild_id, ended, winner_count, prize = record

    cursor = await bot.db.execute(
        """
        SELECT user_id FROM giveaway_entries
        WHERE message_id = ?
        """,
        (message_id,)
    )

    entries = [row[0] for row in await cursor.fetchall()]

    if not entries:
        return await ctx.send("❌ No giveaway entries found.")

    winner = random.choice(entries)

    await ctx.send(
        f"🎉 New winner for **{prize}**: <@{winner}>!"
    )


# ------------------------------------------------------------
# GIVEAWAY INFORMATION
# ------------------------------------------------------------

@bot.hybrid_command(
    name="giveawayinfo",
    description="View giveaway information."
)
@commands.guild_only()
async def giveawayinfo(ctx, message_id: int):

    cursor = await bot.db.execute(
        """
        SELECT guild_id, channel_id, prize,
               winners, ends_at, ended
        FROM giveaways
        WHERE message_id = ?
        """,
        (message_id,)
    )

    record = await cursor.fetchone()

    if not record or record[0] != ctx.guild.id:
        return await ctx.send("❌ Giveaway not found.")

    guild_id, channel_id, prize, winners, ends_at, ended = record

    cursor = await bot.db.execute(
        """
        SELECT COUNT(*) FROM giveaway_entries
        WHERE message_id = ?
        """,
        (message_id,)
    )

    entries = (await cursor.fetchone())[0]

    embed = make_embed(
        "🎉 Giveaway Information",
        f"**Prize:** {prize}\n"
        f"**Winners:** {winners}\n"
        f"**Entries:** {entries}\n"
        f"**Ends:** <t:{ends_at}:F>\n"
        f"**Status:** {'Ended' if ended else 'Active'}\n"
        f"**Channel:** <#{channel_id}>"
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# REGISTER PERSISTENT VIEW
# ------------------------------------------------------------

bot.add_view(GiveawayView())


# ============================================================
# END OF GIVEAWAY ENGINE
# ============================================================

# ============================================================
#       MALARVAADI WELCOME & ONBOARDING ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE MIGRATIONS
# ------------------------------------------------------------

async def ensure_onboarding_schema():

    columns = {
        "goodbye_message": "TEXT",
        "counter_channel": "INTEGER",
        "min_account_age": "INTEGER DEFAULT 0",
        "onboarding_enabled": "INTEGER DEFAULT 1"
    }

    cursor = await bot.db.execute(
        "PRAGMA table_info(guild_config)"
    )

    existing = {
        row[1] for row in await cursor.fetchall()
    }

    for name, definition in columns.items():

        if name not in existing:

            await bot.db.execute(
                f"ALTER TABLE guild_config ADD COLUMN {name} {definition}"
            )

    await bot.db.commit()


async def onboarding_config(guild_id):

    await ensure_onboarding_schema()

    cursor = await bot.db.execute(
        """
        SELECT welcome_channel, goodbye_channel, autorole,
               welcome_message, goodbye_message,
               counter_channel, min_account_age,
               onboarding_enabled
        FROM guild_config
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    return await cursor.fetchone()


# ------------------------------------------------------------
# MESSAGE TEMPLATE ENGINE
# ------------------------------------------------------------

def format_member_message(template, member):

    values = {
        "{user}": member.mention,
        "{username}": discord.utils.escape_markdown(member.name),
        "{server}": discord.utils.escape_markdown(member.guild.name),
        "{membercount}": str(member.guild.member_count),
        "{userid}": str(member.id)
    }

    for key, value in values.items():
        template = template.replace(key, value)

    return template


# ------------------------------------------------------------
# WELCOME MESSAGE CONFIGURATION
# ------------------------------------------------------------

@bot.command(
    name="setwelcome",
    description="Configure the server welcome channel."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setwelcome(
    ctx,
    channel: discord.TextChannel
):

    await ensure_onboarding_schema()

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO guild_config (guild_id)
        VALUES (?)
        """,
        (ctx.guild.id,)
    )

    await bot.db.execute(
        """
        UPDATE guild_config
        SET welcome_channel = ?
        WHERE guild_id = ?
        """,
        (channel.id, ctx.guild.id)
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Welcome channel configured: {channel.mention}"
    )


@bot.command(
    name="setwelcomemessage",
    description="Set a custom welcome message."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setwelcomemessage(ctx, *, message: str):

    if not 1 <= len(message) <= 1800:
        return await ctx.send("❌ Message must contain 1–1800 characters.")

    await ensure_onboarding_schema()

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO guild_config (guild_id)
        VALUES (?)
        """,
        (ctx.guild.id,)
    )

    await bot.db.execute(
        """
        UPDATE guild_config
        SET welcome_message = ?
        WHERE guild_id = ?
        """,
        (message, ctx.guild.id)
    )

    await bot.db.commit()

    await ctx.send(
        "✅ Custom welcome message saved.\n"
        "Available placeholders: `{user}`, `{username}`, "
        "`{server}`, `{membercount}`, `{userid}`."
    )


# ------------------------------------------------------------
# GOODBYE CONFIGURATION
# ------------------------------------------------------------

@bot.command(
    name="setgoodbye",
    description="Configure the goodbye channel."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setgoodbye(
    ctx,
    channel: discord.TextChannel
):

    await ensure_onboarding_schema()

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO guild_config (guild_id)
        VALUES (?)
        """,
        (ctx.guild.id,)
    )

    await bot.db.execute(
        """
        UPDATE guild_config
        SET goodbye_channel = ?
        WHERE guild_id = ?
        """,
        (channel.id, ctx.guild.id)
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Goodbye channel configured: {channel.mention}"
    )


@bot.command(
    name="setgoodbyemessage",
    description="Configure the goodbye message."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setgoodbyemessage(ctx, *, message: str):

    if not 1 <= len(message) <= 1800:
        return await ctx.send("❌ Message must contain 1–1800 characters.")

    await ensure_onboarding_schema()

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO guild_config (guild_id)
        VALUES (?)
        """,
        (ctx.guild.id,)
    )

    await bot.db.execute(
        """
        UPDATE guild_config
        SET goodbye_message = ?
        WHERE guild_id = ?
        """,
        (message, ctx.guild.id)
    )

    await bot.db.commit()

    await ctx.send("✅ Goodbye message saved.")


# ------------------------------------------------------------
# AUTOROLE CONFIGURATION
# ------------------------------------------------------------

@bot.command(
    name="setautorole",
    description="Configure automatic member roles."
)
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
async def setautorole(ctx, role: discord.Role):

    if role >= ctx.guild.me.top_role:
        return await ctx.send(
            "❌ The role must be below the bot's highest role."
        )

    await ensure_onboarding_schema()

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO guild_config (guild_id)
        VALUES (?)
        """,
        (ctx.guild.id,)
    )

    await bot.db.execute(
        """
        UPDATE guild_config
        SET autorole = ?
        WHERE guild_id = ?
        """,
        (role.id, ctx.guild.id)
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Autorole configured: {role.mention}"
    )


@bot.command(
    name="disableautorole",
    description="Disable automatic role assignment."
)
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
async def disableautorole(ctx):

    await bot.db.execute(
        """
        UPDATE guild_config
        SET autorole = NULL
        WHERE guild_id = ?
        """,
        (ctx.guild.id,)
    )

    await bot.db.commit()

    await ctx.send("✅ Autorole disabled.")


# ------------------------------------------------------------
# ACCOUNT AGE PROTECTION
# ------------------------------------------------------------

@bot.command(
    name="setaccountage",
    description="Set the minimum account age alert threshold."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setaccountage(ctx, days: int):

    if not 0 <= days <= 365:
        return await ctx.send(
            "❌ Choose a threshold between 0 and 365 days."
        )

    await ensure_onboarding_schema()

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO guild_config (guild_id)
        VALUES (?)
        """,
        (ctx.guild.id,)
    )

    await bot.db.execute(
        """
        UPDATE guild_config
        SET min_account_age = ?
        WHERE guild_id = ?
        """,
        (days, ctx.guild.id)
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Accounts younger than **{days} days** "
        "will be flagged for staff review."
    )


# ------------------------------------------------------------
# LIVE COUNTER CONFIGURATION
# ------------------------------------------------------------

@bot.command(
    name="setmembercounter",
    description="Configure a live member counter channel."
)
@commands.guild_only()
@commands.has_permissions(manage_channels=True)
async def setmembercounter(
    ctx,
    channel: discord.VoiceChannel
):

    await ensure_onboarding_schema()

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO guild_config (guild_id)
        VALUES (?)
        """,
        (ctx.guild.id,)
    )

    await bot.db.execute(
        """
        UPDATE guild_config
        SET counter_channel = ?
        WHERE guild_id = ?
        """,
        (channel.id, ctx.guild.id)
    )

    await bot.db.commit()

    await update_member_counter(ctx.guild)

    await ctx.send(
        f"✅ Member counter configured: {channel.mention}"
    )


async def update_member_counter(guild):

    config = await onboarding_config(guild.id)

    if not config or not config[5]:
        return

    channel = guild.get_channel(config[5])

    if not channel:
        return

    try:

        await channel.edit(
            name=f"👥 Members: {guild.member_count}"
        )

    except discord.HTTPException:

        logger.warning("Member counter update failed.")


# ------------------------------------------------------------
# MEMBER JOIN LISTENER
# ------------------------------------------------------------

@bot.listen("on_member_join")
async def malarvaadi_onboarding_join(member):

    config = await onboarding_config(member.guild.id)

    if not config:
        return

    welcome_channel_id = config[0]
    welcome_message = config[3]
    min_age = config[6] or 0
    enabled = config[7]

    if enabled:

        account_age = (
            datetime.now(timezone.utc) - member.created_at
        ).days

        if min_age > 0 and account_age < min_age:

            await moderation_log(
                member.guild,
                "⚠️ New Account Alert",
                f"**Member:** {member.mention}\n"
                f"**Account Age:** {account_age} days\n"
                f"**Threshold:** {min_age} days"
            )

        if welcome_channel_id:

            channel = member.guild.get_channel(
                welcome_channel_id
            )

            if channel:

                message = welcome_message or (
                    "Welcome {user} to **{server}**! "
                    "You are member #{membercount}."
                )

                try:

                    await channel.send(
                        format_member_message(message, member)
                    )

                except discord.HTTPException:

                    logger.warning("Custom welcome failed.")

    await update_member_counter(member.guild)


# ------------------------------------------------------------
# MEMBER LEAVE LISTENER
# ------------------------------------------------------------

@bot.listen("on_member_remove")
async def malarvaadi_goodbye_listener(member):

    config = await onboarding_config(member.guild.id)

    if not config:
        return

    goodbye_channel_id = config[1]
    goodbye_message = config[4]

    if goodbye_channel_id:

        channel = member.guild.get_channel(
            goodbye_channel_id
        )

        if channel:

            message = goodbye_message or (
                "**{username}** has left **{server}**. "
                "We now have {membercount} members."
            )

            try:

                await channel.send(
                    format_member_message(message, member)
                )

            except discord.HTTPException:

                logger.warning("Goodbye message failed.")

    await update_member_counter(member.guild)


# ------------------------------------------------------------
# ONBOARDING STATUS
# ------------------------------------------------------------

@bot.command(
    name="onboarding",
    description="View onboarding configuration."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def onboarding(ctx):

    config = await onboarding_config(ctx.guild.id)

    if not config:
        return await ctx.send(
            "❌ No onboarding configuration found."
        )

    welcome = (
        f"<#{config[0]}>"
        if config[0] else "Not configured"
    )

    goodbye = (
        f"<#{config[1]}>"
        if config[1] else "Not configured"
    )

    autorole = (
        f"<@&{config[2]}>"
        if config[2] else "Disabled"
    )

    counter = (
        f"<#{config[5]}>"
        if config[5] else "Not configured"
    )

    embed = make_embed(
        "👋 Malarvaadi Onboarding",
        f"**Welcome Channel:** {welcome}\n"
        f"**Goodbye Channel:** {goodbye}\n"
        f"**Autorole:** {autorole}\n"
        f"**Member Counter:** {counter}\n"
        f"**Account Age Threshold:** {config[6]} days\n"
        f"**Onboarding:** {'Enabled' if config[7] else 'Disabled'}"
    )

    await ctx.send(embed=embed)


# ============================================================
# END OF ONBOARDING ENGINE
# ============================================================

# ============================================================
#       MALARVAADI COMMUNITY ENGAGEMENT ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_community_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS community_polls (
            message_id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            channel_id INTEGER,
            creator_id INTEGER,
            question TEXT,
            options TEXT,
            ends_at INTEGER,
            ended INTEGER DEFAULT 0
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS community_votes (
            message_id INTEGER,
            user_id INTEGER,
            option_index INTEGER,
            PRIMARY KEY(message_id, user_id)
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS suggestion_messages (
            suggestion_id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            channel_id INTEGER,
            message_id INTEGER,
            user_id INTEGER,
            content TEXT,
            status TEXT DEFAULT 'pending',
            created_at INTEGER
        )
    """)

    await bot.db.commit()


# ------------------------------------------------------------
# SUGGESTIONS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="suggest",
    description="Submit a server suggestion."
)
@commands.guild_only()
async def suggest(ctx, *, suggestion: str):

    await ensure_community_schema()

    if not 10 <= len(suggestion) <= 1500:
        return await ctx.send(
            "❌ Suggestions must contain 10–1500 characters."
        )

    embed = make_embed(
        "💡 Community Suggestion",
        suggestion
    )

    embed.add_field(
        name="Submitted By",
        value=ctx.author.mention,
        inline=True
    )

    embed.add_field(
        name="Status",
        value="🟡 Pending Review",
        inline=True
    )

    message = await ctx.send(embed=embed)

    cursor = await bot.db.execute(
        """
        INSERT INTO suggestion_messages
        (guild_id, channel_id, message_id, user_id,
         content, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            ctx.guild.id,
            ctx.channel.id,
            message.id,
            ctx.author.id,
            suggestion,
            int(time.time())
        )
    )

    suggestion_id = cursor.lastrowid

    await bot.db.commit()

    embed.set_footer(
        text=f"Malarvaadi Suggestion ID: {suggestion_id}"
    )

    await message.edit(embed=embed)

    await ctx.send(
        f"✅ Suggestion submitted! ID: `{suggestion_id}`",
        delete_after=8
    )


# ------------------------------------------------------------
# APPROVE / REJECT SUGGESTIONS
# ------------------------------------------------------------

async def review_suggestion(ctx, suggestion_id, status):

    await ensure_community_schema()

    cursor = await bot.db.execute(
        """
        SELECT channel_id, message_id, user_id,
               content, status
        FROM suggestion_messages
        WHERE suggestion_id = ? AND guild_id = ?
        """,
        (suggestion_id, ctx.guild.id)
    )

    record = await cursor.fetchone()

    if not record:
        return await ctx.send("❌ Suggestion not found.")

    channel_id, message_id, user_id, content, old_status = record

    if old_status != "pending":
        return await ctx.send(
            "❌ This suggestion has already been reviewed."
        )

    await bot.db.execute(
        """
        UPDATE suggestion_messages
        SET status = ?
        WHERE suggestion_id = ? AND guild_id = ?
        """,
        (status, suggestion_id, ctx.guild.id)
    )

    await bot.db.commit()

    channel = ctx.guild.get_channel(channel_id)

    if channel:

        try:

            message = await channel.fetch_message(message_id)

            embed = make_embed(
                "💡 Community Suggestion",
                content
            )

            embed.add_field(
                name="Submitted By",
                value=f"<@{user_id}>",
                inline=True
            )

            embed.add_field(
                name="Review Status",
                value=(
                    "🟢 Approved"
                    if status == "approved"
                    else "🔴 Rejected"
                ),
                inline=True
            )

            embed.set_footer(
                text=f"Malarvaadi Suggestion ID: {suggestion_id}"
            )

            await message.edit(embed=embed)

        except discord.HTTPException:
            logger.warning("Suggestion message could not be edited.")

    await ctx.send(
        f"✅ Suggestion `{suggestion_id}` marked **{status}**."
    )


@bot.hybrid_command(
    name="approve",
    description="Approve a community suggestion."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def approve(ctx, suggestion_id: int):

    await review_suggestion(
        ctx,
        suggestion_id,
        "approved"
    )


@bot.hybrid_command(
    name="reject",
    description="Reject a community suggestion."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def reject(ctx, suggestion_id: int):

    await review_suggestion(
        ctx,
        suggestion_id,
        "rejected"
    )


# ------------------------------------------------------------
# POLL CREATION
# ------------------------------------------------------------

POLL_EMOJIS = [
    "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣",
    "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"
]


@bot.hybrid_command(
    name="poll",
    description="Create an interactive community poll."
)
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
async def poll(
    ctx,
    duration: str,
    question: str,
    *,
    choices: str
):

    await ensure_community_schema()

    seconds = parse_duration(duration)

    if seconds is None:
        return await ctx.send(
            "❌ Use a duration such as `10m`, `2h` or `1d`."
        )

    options = [
        option.strip()
        for option in choices.split("|")
        if option.strip()
    ]

    if not 2 <= len(options) <= 10:
        return await ctx.send(
            "❌ Provide between 2 and 10 choices, "
            "separated by `|`."
        )

    if len(question) > 200:
        return await ctx.send("❌ Question is too long.")

    if any(len(option) > 100 for option in options):
        return await ctx.send("❌ Each choice must be under 100 characters.")

    ends_at = int(time.time()) + seconds

    description = "\n\n".join(
        f"{POLL_EMOJIS[index]} **{option}**"
        for index, option in enumerate(options)
    )

    embed = make_embed(
        "📊 Community Poll",
        f"**{question}**\n\n"
        f"{description}\n\n"
        f"⏰ Ends: <t:{ends_at}:R>"
    )

    embed.add_field(
        name="Created By",
        value=ctx.author.mention,
        inline=False
    )

    message = await ctx.send(embed=embed)

    for index in range(len(options)):
        await message.add_reaction(POLL_EMOJIS[index])

    await bot.db.execute(
        """
        INSERT INTO community_polls
        (message_id, guild_id, channel_id, creator_id,
         question, options, ends_at, ended)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            message.id,
            ctx.guild.id,
            ctx.channel.id,
            ctx.author.id,
            question,
            json.dumps(options),
            ends_at
        )
    )

    await bot.db.commit()


# ------------------------------------------------------------
# END POLL
# ------------------------------------------------------------

@bot.hybrid_command(
    name="endpoll",
    description="End a community poll and display results."
)
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
async def endpoll(ctx, message_id: int):

    await ensure_community_schema()

    cursor = await bot.db.execute(
        """
        SELECT channel_id, question, options, ended
        FROM community_polls
        WHERE message_id = ? AND guild_id = ?
        """,
        (message_id, ctx.guild.id)
    )

    record = await cursor.fetchone()

    if not record:
        return await ctx.send("❌ Poll not found.")

    channel_id, question, raw_options, ended = record

    if ended:
        return await ctx.send("❌ This poll has already ended.")

    channel = ctx.guild.get_channel(channel_id)

    if not channel:
        return await ctx.send("❌ Poll channel not found.")

    try:
        message = await channel.fetch_message(message_id)
    except discord.HTTPException:
        return await ctx.send("❌ Poll message not found.")

    options = json.loads(raw_options)

    results = []

    for index, option in enumerate(options):

        emoji = POLL_EMOJIS[index]

        reaction = discord.utils.get(
            message.reactions,
            emoji=emoji
        )

        votes = 0

        if reaction:

            async for user in reaction.users():

                if not user.bot:
                    votes += 1

        results.append((option, votes))

    results.sort(
        key=lambda item: item[1],
        reverse=True
    )

    description = "\n".join(
        f"**{index + 1}. {option}** — `{votes}` votes"
        for index, (option, votes) in enumerate(results)
    )

    result_embed = make_embed(
        "🏁 Poll Results",
        f"**{question}**\n\n{description}"
    )

    await message.edit(
        embed=result_embed
    )

    await bot.db.execute(
        """
        UPDATE community_polls
        SET ended = 1
        WHERE message_id = ?
        """,
        (message_id,)
    )

    await bot.db.commit()

    await ctx.send("📊 Poll ended and results published!")


# ------------------------------------------------------------
# POLL INFORMATION
# ------------------------------------------------------------

@bot.hybrid_command(
    name="pollinfo",
    description="View poll information."
)
@commands.guild_only()
async def pollinfo(ctx, message_id: int):

    await ensure_community_schema()

    cursor = await bot.db.execute(
        """
        SELECT question, options, ends_at, ended
        FROM community_polls
        WHERE message_id = ? AND guild_id = ?
        """,
        (message_id, ctx.guild.id)
    )

    record = await cursor.fetchone()

    if not record:
        return await ctx.send("❌ Poll not found.")

    question, raw_options, ends_at, ended = record

    options = json.loads(raw_options)

    embed = make_embed(
        "📊 Poll Information",
        f"**Question:** {question}\n"
        f"**Options:** {len(options)}\n"
        f"**Ends:** <t:{ends_at}:F>\n"
        f"**Status:** {'Ended' if ended else 'Active'}"
    )

    await ctx.send(embed=embed)


# ============================================================
# END OF COMMUNITY ENGINE
# ============================================================
# ============================================================
#          MALARVAADI REACTION ROLES ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_reaction_role_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (message_id, emoji)
        )
    """)

    await bot.db.commit()


# ------------------------------------------------------------
# EMOJI HELPERS
# ------------------------------------------------------------

def normalize_reaction_emoji(emoji):

    if isinstance(emoji, discord.Emoji):
        return str(emoji.id)

    if isinstance(emoji, discord.PartialEmoji):
        return str(emoji.id) if emoji.id else emoji.name

    return str(emoji)


# ------------------------------------------------------------
# ROLE VALIDATION
# ------------------------------------------------------------

def reaction_role_is_assignable(guild, role):

    if role is None:
        return False

    if role.is_default():
        return False

    if role.managed:
        return False

    if guild.me is None:
        return False

    if role >= guild.me.top_role:
        return False

    return True


# ------------------------------------------------------------
# CREATE REACTION ROLE MAPPING
# ------------------------------------------------------------

@bot.command(
    name="addreactionrole",
    description="Connect a reaction to a server role."
)
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
async def addreactionrole(
    ctx,
    message_id: str,
    emoji: str,
    role: discord.Role
):

    await ensure_reaction_role_schema()

    try:
        target_message_id = int(message_id)
    except ValueError:
        return await ctx.send(
            "❌ Enter a valid message ID."
        )

    if not reaction_role_is_assignable(ctx.guild, role):
        return await ctx.send(
            "❌ I cannot assign that role. Check my role hierarchy."
        )

    channel = ctx.channel

    try:
        target_message = await channel.fetch_message(
            target_message_id
        )
    except discord.NotFound:
        return await ctx.send(
            "❌ Message not found in this channel."
        )
    except discord.Forbidden:
        return await ctx.send(
            "❌ I cannot access that message."
        )
    except discord.HTTPException:
        return await ctx.send(
            "❌ Discord could not retrieve that message."
        )

    try:
        await target_message.add_reaction(emoji)
    except discord.HTTPException:
        return await ctx.send(
            "❌ Invalid emoji or I cannot add that reaction."
        )

    normalized_emoji = normalize_reaction_emoji(
        discord.PartialEmoji.from_str(emoji)
    )

    await bot.db.execute(
        """
        INSERT OR REPLACE INTO reaction_roles
        (guild_id, message_id, emoji, role_id)
        VALUES (?, ?, ?, ?)
        """,
        (
            ctx.guild.id,
            target_message.id,
            normalized_emoji,
            role.id
        )
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Reaction role created!\n"
        f"Emoji: {emoji}\n"
        f"Role: {role.mention}\n"
        f"Message ID: `{target_message.id}`"
    )


# ------------------------------------------------------------
# REMOVE REACTION ROLE MAPPING
# ------------------------------------------------------------

@bot.command(
    name="removereactionrole",
    description="Remove a reaction-role mapping."
)
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
async def removereactionrole(
    ctx,
    message_id: str,
    emoji: str
):

    await ensure_reaction_role_schema()

    try:
        target_message_id = int(message_id)
    except ValueError:
        return await ctx.send(
            "❌ Enter a valid message ID."
        )

    normalized_emoji = normalize_reaction_emoji(
        discord.PartialEmoji.from_str(emoji)
    )

    cursor = await bot.db.execute(
        """
        DELETE FROM reaction_roles
        WHERE guild_id = ?
        AND message_id = ?
        AND emoji = ?
        """,
        (
            ctx.guild.id,
            target_message_id,
            normalized_emoji
        )
    )

    await bot.db.commit()

    if cursor.rowcount == 0:
        return await ctx.send(
            "❌ No matching reaction-role mapping found."
        )

    await ctx.send(
        "✅ Reaction-role mapping removed."
    )


# ------------------------------------------------------------
# LIST REACTION ROLES
# ------------------------------------------------------------

@bot.command(
    name="reactionroles",
    description="View configured reaction roles."
)
@commands.guild_only()
async def reactionroles(ctx):

    await ensure_reaction_role_schema()

    cursor = await bot.db.execute(
        """
        SELECT message_id, emoji, role_id
        FROM reaction_roles
        WHERE guild_id = ?
        ORDER BY message_id
        """,
        (ctx.guild.id,)
    )

    records = await cursor.fetchall()

    if not records:
        return await ctx.send(
            "No reaction roles have been configured."
        )

    embed = make_embed(
        "🎭 Reaction Role Configuration",
        "React to the configured messages to receive roles."
    )

    for message_id, emoji, role_id in records:

        role = ctx.guild.get_role(role_id)

        embed.add_field(
            name=f"Message: {message_id}",
            value=(
                f"Emoji: {emoji}\n"
                f"Role: {role.mention if role else 'Deleted role'}"
            ),
            inline=False
        )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# REACTION ADD LISTENER
# ------------------------------------------------------------

@bot.listen("on_raw_reaction_add")
async def malarvaadi_reaction_role_add(payload):

    if payload.guild_id is None:
        return

    if bot.user and payload.user_id == bot.user.id:
        return

    await ensure_reaction_role_schema()

    emoji = normalize_reaction_emoji(payload.emoji)

    cursor = await bot.db.execute(
        """
        SELECT role_id
        FROM reaction_roles
        WHERE guild_id = ?
        AND message_id = ?
        AND emoji = ?
        """,
        (
            payload.guild_id,
            payload.message_id,
            emoji
        )
    )

    record = await cursor.fetchone()

    if not record:
        return

    guild = bot.get_guild(payload.guild_id)

    if guild is None:
        return

    member = guild.get_member(payload.user_id)

    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except discord.HTTPException:
            return

    role = guild.get_role(record[0])

    if not reaction_role_is_assignable(guild, role):
        return

    if role in member.roles:
        return

    try:
        await member.add_roles(
            role,
            reason="Malarvaadi reaction role"
        )
    except discord.Forbidden:
        logger.warning(
            "Missing permission to assign reaction role."
        )
    except discord.HTTPException:
        logger.exception(
            "Reaction role assignment failed."
        )


# ------------------------------------------------------------
# REACTION REMOVE LISTENER
# ------------------------------------------------------------

@bot.listen("on_raw_reaction_remove")
async def malarvaadi_reaction_role_remove(payload):

    if payload.guild_id is None:
        return

    await ensure_reaction_role_schema()

    emoji = normalize_reaction_emoji(payload.emoji)

    cursor = await bot.db.execute(
        """
        SELECT role_id
        FROM reaction_roles
        WHERE guild_id = ?
        AND message_id = ?
        AND emoji = ?
        """,
        (
            payload.guild_id,
            payload.message_id,
            emoji
        )
    )

    record = await cursor.fetchone()

    if not record:
        return

    guild = bot.get_guild(payload.guild_id)

    if guild is None:
        return

    member = guild.get_member(payload.user_id)

    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except discord.HTTPException:
            return

    role = guild.get_role(record[0])

    if not reaction_role_is_assignable(guild, role):
        return

    if role not in member.roles:
        return

    try:
        await member.remove_roles(
            role,
            reason="Malarvaadi reaction role removed"
        )
    except discord.Forbidden:
        logger.warning(
            "Missing permission to remove reaction role."
        )
    except discord.HTTPException:
        logger.exception(
            "Reaction role removal failed."
        )


# ============================================================
# END OF REACTION ROLES ENGINE
# ============================================================
# ============================================================
#       MALARVAADI ANNOUNCEMENT & CONFESSION ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_announcement_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS announcement_config (
            guild_id INTEGER PRIMARY KEY,
            confession_channel_id INTEGER
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS confessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)

    await bot.db.commit()


# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

async def get_announcement_config(guild_id):

    await ensure_announcement_schema()

    cursor = await bot.db.execute(
        """
        SELECT confession_channel_id
        FROM announcement_config
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    return await cursor.fetchone()


# ------------------------------------------------------------
# SET CONFESSION CHANNEL
# ------------------------------------------------------------

@bot.command(
    name="setconfession",
    description="Configure the anonymous confession channel."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setconfession(ctx, channel: discord.TextChannel):

    await ensure_announcement_schema()

    await bot.db.execute(
        """
        INSERT INTO announcement_config
        (guild_id, confession_channel_id)
        VALUES (?, ?)
        ON CONFLICT(guild_id)
        DO UPDATE SET confession_channel_id = excluded.confession_channel_id
        """,
        (ctx.guild.id, channel.id)
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Confession channel configured: {channel.mention}"
    )


# ------------------------------------------------------------
# DISABLE CONFESSIONS
# ------------------------------------------------------------

@bot.command(
    name="disableconfession",
    description="Disable anonymous confessions."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def disableconfession(ctx):

    await ensure_announcement_schema()

    await bot.db.execute(
        """
        DELETE FROM announcement_config
        WHERE guild_id = ?
        """,
        (ctx.guild.id,)
    )

    await bot.db.commit()

    await ctx.send("✅ Anonymous confessions disabled.")


# ------------------------------------------------------------
# ANONYMOUS CONFESSION
# ------------------------------------------------------------

@bot.hybrid_command(
    name="confess",
    description="Send an anonymous confession."
)
@commands.guild_only()
async def confess(ctx, *, message: str):

    await ensure_announcement_schema()

    if not 5 <= len(message) <= 1500:
        return await ctx.send(
            "❌ Confession must contain 5–1500 characters."
        )

    config = await get_announcement_config(ctx.guild.id)

    if not config or not config[0]:
        return await ctx.send(
            "❌ Confession channel has not been configured."
        )

    channel = ctx.guild.get_channel(config[0])

    if channel is None:
        return await ctx.send(
            "❌ Configured confession channel no longer exists."
        )

    confession_id = None

    try:

        cursor = await bot.db.execute(
            """
            INSERT INTO confessions
            (guild_id, user_id, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                ctx.guild.id,
                ctx.author.id,
                message,
                int(time.time())
            )
        )

        confession_id = cursor.lastrowid

        await bot.db.commit()

        embed = make_embed(
            "💌 Anonymous Confession",
            message
        )

        embed.add_field(
            name="Confession ID",
            value=f"`#{confession_id}`",
            inline=False
        )

        embed.set_footer(
            text="Malarvaadi Community • Anonymous"
        )

        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none()
        )

    except discord.HTTPException:
        logger.exception("Confession delivery failed.")

        return await ctx.send(
            "❌ Could not deliver your confession. Please try again."
        )

    await ctx.send(
        "✅ Your confession was submitted anonymously.",
        ephemeral=bool(ctx.interaction)
    )


# ------------------------------------------------------------
# PROFESSIONAL ANNOUNCEMENT
# ------------------------------------------------------------

@bot.hybrid_command(
    name="announce",
    description="Publish a professional server announcement."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def announce(
    ctx,
    channel: discord.TextChannel,
    title: str,
    *,
    message: str
):

    if not 1 <= len(title) <= 200:
        return await ctx.send("❌ Title must be 1–200 characters.")

    if not 1 <= len(message) <= 4000:
        return await ctx.send("❌ Message must be 1–4000 characters.")

    embed = make_embed(
        f"📢 {title}",
        message,
        COLOR
    )

    embed.add_field(
        name="Server",
        value=ctx.guild.name,
        inline=True
    )

    embed.add_field(
        name="Published By",
        value=ctx.author.display_name,
        inline=True
    )

    embed.set_footer(
        text="Malarvaadi Announcement System"
    )

    try:

        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none()
        )

    except discord.Forbidden:
        return await ctx.send(
            "❌ I don't have permission to send messages in that channel."
        )

    except discord.HTTPException:
        return await ctx.send(
            "❌ Discord could not publish the announcement."
        )

    await ctx.send(
        f"✅ Announcement published in {channel.mention}."
    )


# ------------------------------------------------------------
# CONFESSION STATISTICS (ADMIN)
# ------------------------------------------------------------

@bot.command(
    name="confessionstats",
    description="View confession statistics."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def confessionstats(ctx):

    await ensure_announcement_schema()

    cursor = await bot.db.execute(
        """
        SELECT COUNT(*)
        FROM confessions
        WHERE guild_id = ?
        """,
        (ctx.guild.id,)
    )

    total = (await cursor.fetchone())[0]

    cursor = await bot.db.execute(
        """
        SELECT COUNT(DISTINCT user_id)
        FROM confessions
        WHERE guild_id = ?
        """,
        (ctx.guild.id,)
    )

    contributors = (await cursor.fetchone())[0]

    embed = make_embed(
        "💌 Confession Statistics",
        "Community confession activity."
    )

    embed.add_field(
        name="Total Confessions",
        value=f"`{total}`",
        inline=True
    )

    embed.add_field(
        name="Contributors",
        value=f"`{contributors}`",
        inline=True
    )

    await ctx.send(embed=embed)


# ============================================================
# END OF ANNOUNCEMENT & CONFESSION ENGINE
# ============================================================

# ============================================================
#          MALARVAADI REMINDER & SCHEDULING ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_reminder_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            guild_id INTEGER,
            channel_id INTEGER,
            message TEXT NOT NULL,
            remind_at INTEGER NOT NULL,
            completed INTEGER DEFAULT 0,
            recurrence TEXT DEFAULT 'none'
        )
    """)

    # Migrate the original reminders table safely.
    cursor = await bot.db.execute(
        "PRAGMA table_info(reminders)"
    )

    columns = [row[1] for row in await cursor.fetchall()]

    migrations = {
        "guild_id": "INTEGER",
        "recurrence": "TEXT DEFAULT 'none'"
    }

    for column, definition in migrations.items():
        if column not in columns:
            await bot.db.execute(
                f"ALTER TABLE reminders ADD COLUMN {column} {definition}"
            )

    await bot.db.commit()


# ------------------------------------------------------------
# CREATE REMINDER
# ------------------------------------------------------------

@bot.hybrid_command(
    name="remind",
    description="Create a personal reminder."
)
@commands.guild_only()
async def remind(
    ctx,
    duration: str,
    *,
    message: str
):

    await ensure_reminder_schema()

    seconds = parse_duration(duration)

    if seconds is None:
        return await ctx.send(
            "❌ Invalid duration. Example: `10m`, `2h`, `1d`."
        )

    if seconds > 31536000:
        return await ctx.send(
            "❌ Maximum reminder duration is one year."
        )

    if not 1 <= len(message) <= 1000:
        return await ctx.send(
            "❌ Reminder text must contain 1–1000 characters."
        )

    remind_at = int(time.time()) + seconds

    cursor = await bot.db.execute(
        """
        INSERT INTO reminders
        (user_id, guild_id, channel_id, message,
         remind_at, completed, recurrence)
        VALUES (?, ?, ?, ?, ?, 0, 'none')
        """,
        (
            ctx.author.id,
            ctx.guild.id,
            ctx.channel.id,
            message,
            remind_at
        )
    )

    reminder_id = cursor.lastrowid

    await bot.db.commit()

    await ctx.send(
        f"⏰ Reminder created!\n"
        f"**ID:** `{reminder_id}`\n"
        f"**Message:** {message}\n"
        f"**Time:** <t:{remind_at}:F>\n"
        f"**In:** <t:{remind_at}:R>"
    )


# ------------------------------------------------------------
# PERSONAL REMINDERS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="myreminders",
    description="View your active reminders."
)
@commands.guild_only()
async def myreminders(ctx):

    await ensure_reminder_schema()

    cursor = await bot.db.execute(
        """
        SELECT id, message, remind_at, recurrence
        FROM reminders
        WHERE user_id = ?
        AND guild_id = ?
        AND completed = 0
        ORDER BY remind_at ASC
        LIMIT 20
        """,
        (ctx.author.id, ctx.guild.id)
    )

    records = await cursor.fetchall()

    if not records:
        return await ctx.send(
            "📭 You have no active reminders."
        )

    embed = make_embed(
        "⏰ Your Active Reminders",
        f"Showing {len(records)} reminder(s)."
    )

    for reminder_id, message, remind_at, recurrence in records:

        embed.add_field(
            name=f"Reminder #{reminder_id}",
            value=(
                f"{message}\n"
                f"🕒 <t:{remind_at}:R>\n"
                f"🔁 {recurrence}"
            ),
            inline=False
        )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# CANCEL REMINDER
# ------------------------------------------------------------

@bot.hybrid_command(
    name="cancelreminder",
    description="Cancel one of your reminders."
)
@commands.guild_only()
async def cancelreminder(ctx, reminder_id: int):

    await ensure_reminder_schema()

    cursor = await bot.db.execute(
        """
        UPDATE reminders
        SET completed = 1
        WHERE id = ?
        AND user_id = ?
        AND guild_id = ?
        AND completed = 0
        """,
        (
            reminder_id,
            ctx.author.id,
            ctx.guild.id
        )
    )

    await bot.db.commit()

    if cursor.rowcount == 0:
        return await ctx.send(
            "❌ Reminder not found or already completed."
        )

    await ctx.send(
        f"✅ Reminder `{reminder_id}` cancelled."
    )


# ------------------------------------------------------------
# RECURRING REMINDERS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="repeatremind",
    description="Create a daily or weekly recurring reminder."
)
@commands.guild_only()
async def repeatremind(
    ctx,
    frequency: str,
    *,
    message: str
):

    await ensure_reminder_schema()

    frequency = frequency.lower()

    intervals = {
        "daily": 86400,
        "weekly": 604800
    }

    if frequency not in intervals:
        return await ctx.send(
            "❌ Frequency must be `daily` or `weekly`."
        )

    if not 1 <= len(message) <= 1000:
        return await ctx.send(
            "❌ Reminder text must contain 1–1000 characters."
        )

    remind_at = int(time.time()) + intervals[frequency]

    cursor = await bot.db.execute(
        """
        INSERT INTO reminders
        (user_id, guild_id, channel_id, message,
         remind_at, completed, recurrence)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (
            ctx.author.id,
            ctx.guild.id,
            ctx.channel.id,
            message,
            remind_at,
            frequency
        )
    )

    reminder_id = cursor.lastrowid

    await bot.db.commit()

    await ctx.send(
        f"🔁 Recurring reminder created!\n"
        f"**ID:** `{reminder_id}`\n"
        f"**Frequency:** {frequency.title()}\n"
        f"**Next reminder:** <t:{remind_at}:F>"
    )


# ------------------------------------------------------------
# REMINDER DELIVERY
# ------------------------------------------------------------

async def process_due_reminders():

    await ensure_reminder_schema()

    now = int(time.time())

    cursor = await bot.db.execute(
        """
        SELECT id, user_id, guild_id, channel_id,
               message, remind_at, recurrence
        FROM reminders
        WHERE completed = 0
        AND remind_at <= ?
        ORDER BY remind_at ASC
        LIMIT 100
        """,
        (now,)
    )

    records = await cursor.fetchall()

    for record in records:

        (
            reminder_id,
            user_id,
            guild_id,
            channel_id,
            message,
            remind_at,
            recurrence
        ) = record

        try:

            user = bot.get_user(user_id)

            if user is None:
                user = await bot.fetch_user(user_id)

            reminder_embed = make_embed(
                "⏰ Malarvaadi Reminder",
                message
            )

            reminder_embed.add_field(
                name="Reminder ID",
                value=f"`{reminder_id}`",
                inline=True
            )

            reminder_embed.add_field(
                name="Scheduled Time",
                value=f"<t:{remind_at}:F>",
                inline=True
            )

            reminder_embed.set_footer(
                text="Your reminder has arrived!"
            )

            if channel_id:

                channel = bot.get_channel(channel_id)

                if channel is None:
                    channel = await bot.fetch_channel(channel_id)

                await channel.send(
                    content=f"<@{user_id}>",
                    embed=reminder_embed,
                    allowed_mentions=discord.AllowedMentions(
                        users=[discord.Object(id=user_id)]
                    )
                )

            else:

                await user.send(embed=reminder_embed)

            if recurrence in ("daily", "weekly"):

                interval = (
                    86400 if recurrence == "daily"
                    else 604800
                )

                next_time = max(
                    remind_at + interval,
                    now + 1
                )

                await bot.db.execute(
                    """
                    UPDATE reminders
                    SET remind_at = ?
                    WHERE id = ?
                    """,
                    (next_time, reminder_id)
                )

            else:

                await bot.db.execute(
                    """
                    UPDATE reminders
                    SET completed = 1
                    WHERE id = ?
                    """,
                    (reminder_id,)
                )

            await bot.db.commit()

        except discord.Forbidden:

            # Do not repeatedly retry reminders that cannot
            # be delivered because the destination blocks the bot.
            await bot.db.execute(
                """
                UPDATE reminders
                SET completed = 1
                WHERE id = ?
                """,
                (reminder_id,)
            )

            await bot.db.commit()

            logger.warning(
                "Reminder %s could not be delivered.",
                reminder_id
            )

        except Exception:

            logger.exception(
                "Reminder delivery failed: %s",
                reminder_id
            )


# ------------------------------------------------------------
# AUTOMATIC REMINDER SCHEDULER
# ------------------------------------------------------------

@tasks.loop(seconds=30)
async def malarvaadi_reminder_scheduler():

    await process_due_reminders()


@malarvaadi_reminder_scheduler.before_loop
async def before_reminder_scheduler():

    await bot.wait_until_ready()


@bot.listen("on_ready")
async def start_reminder_scheduler():

    if not malarvaadi_reminder_scheduler.is_running():
        malarvaadi_reminder_scheduler.start()


# ============================================================
# END OF REMINDER ENGINE
# ============================================================

# ============================================================
#          MALARVAADI STARBOARD & STICKY ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_starboard_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS starboard_config (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            threshold INTEGER DEFAULT 3,
            emoji TEXT DEFAULT '⭐'
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS starboard_messages (
            source_message_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            starboard_message_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS sticky_messages (
            channel_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            last_message_id INTEGER
        )
    """)

    await bot.db.commit()


# ============================================================
# STARBOARD CONFIGURATION
# ============================================================

@bot.hybrid_command(
    name="setstarboard",
    description="Configure the server starboard."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setstarboard(
    ctx,
    channel: discord.TextChannel,
    threshold: int = 3
):

    await ensure_starboard_schema()

    if not 1 <= threshold <= 100:
        return await ctx.send(
            "❌ Threshold must be between 1 and 100."
        )

    await bot.db.execute(
        """
        INSERT INTO starboard_config
        (guild_id, channel_id, threshold, emoji)
        VALUES (?, ?, ?, '⭐')
        ON CONFLICT(guild_id)
        DO UPDATE SET
            channel_id = excluded.channel_id,
            threshold = excluded.threshold
        """,
        (ctx.guild.id, channel.id, threshold)
    )

    await bot.db.commit()

    await ctx.send(
        f"⭐ Starboard configured!\n"
        f"Channel: {channel.mention}\n"
        f"Threshold: {threshold} stars"
    )


# ------------------------------------------------------------
# CHANGE STARBOARD EMOJI
# ------------------------------------------------------------

@bot.hybrid_command(
    name="starboardemoji",
    description="Change the starboard reaction emoji."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def starboardemoji(ctx, emoji: str):

    await ensure_starboard_schema()

    cursor = await bot.db.execute(
        """
        SELECT channel_id
        FROM starboard_config
        WHERE guild_id = ?
        """,
        (ctx.guild.id,)
    )

    if not await cursor.fetchone():
        return await ctx.send(
            "❌ Configure starboard first."
        )

    try:
        await ctx.message.add_reaction(emoji)
    except discord.HTTPException:
        return await ctx.send("❌ Invalid reaction emoji.")

    await bot.db.execute(
        """
        UPDATE starboard_config
        SET emoji = ?
        WHERE guild_id = ?
        """,
        (emoji, ctx.guild.id)
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Starboard emoji changed to {emoji}."
    )


# ------------------------------------------------------------
# DISABLE STARBOARD
# ------------------------------------------------------------

@bot.hybrid_command(
    name="disablestarboard",
    description="Disable the server starboard."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def disablestarboard(ctx):

    await ensure_starboard_schema()

    await bot.db.execute(
        "DELETE FROM starboard_config WHERE guild_id = ?",
        (ctx.guild.id,)
    )

    await bot.db.commit()

    await ctx.send("✅ Starboard disabled.")


# ============================================================
# STARBOARD REACTION PROCESSING
# ============================================================

async def process_starboard_reaction(
    payload,
    reaction_added
):

    if payload.guild_id is None:
        return

    if bot.user and payload.user_id == bot.user.id:
        return

    await ensure_starboard_schema()

    guild = bot.get_guild(payload.guild_id)

    if guild is None:
        return

    cursor = await bot.db.execute(
        """
        SELECT channel_id, threshold, emoji
        FROM starboard_config
        WHERE guild_id = ?
        """,
        (guild.id,)
    )

    config = await cursor.fetchone()

    if not config:
        return

    starboard_channel_id, threshold, configured_emoji = config

    if normalize_reaction_emoji(payload.emoji) != normalize_reaction_emoji(
        discord.PartialEmoji.from_str(configured_emoji)
    ):
        return

    source_channel = guild.get_channel(payload.channel_id)

    if source_channel is None:
        return

    try:
        source_message = await source_channel.fetch_message(
            payload.message_id
        )
    except discord.HTTPException:
        return

    if source_message.author.bot:
        return

    if source_message.author.id == payload.user_id:
        return

    reaction = discord.utils.get(
        source_message.reactions,
        emoji=payload.emoji
    )

    count = reaction.count if reaction else 0

    # Subtract the bot's own reaction if present.
    if reaction:
        async for reactor in reaction.users(limit=None):
            if bot.user and reactor.id == bot.user.id:
                count -= 1
                break

    starboard_channel = guild.get_channel(
        starboard_channel_id
    )

    if starboard_channel is None:
        return

    cursor = await bot.db.execute(
        """
        SELECT starboard_message_id
        FROM starboard_messages
        WHERE source_message_id = ?
        """,
        (source_message.id,)
    )

    existing = await cursor.fetchone()

    if count < threshold:

        if existing:

            try:
                old_message = await starboard_channel.fetch_message(
                    existing[0]
                )
                await old_message.delete()
            except discord.HTTPException:
                pass

            await bot.db.execute(
                """
                DELETE FROM starboard_messages
                WHERE source_message_id = ?
                """,
                (source_message.id,)
            )

            await bot.db.commit()

        return

    embed = discord.Embed(
        description=source_message.content or "*No text content*",
        color=COLOR,
        timestamp=source_message.created_at
    )

    embed.set_author(
        name=str(source_message.author),
        icon_url=source_message.author.display_avatar.url
    )

    embed.add_field(
        name="Source",
        value=f"[Jump to message]({source_message.jump_url})",
        inline=True
    )

    embed.add_field(
        name="Stars",
        value=f"⭐ {count}",
        inline=True
    )

    if source_message.attachments:
        attachment = source_message.attachments[0]

        if attachment.content_type and attachment.content_type.startswith("image/"):
            embed.set_image(url=attachment.url)

    if existing:

        try:
            old_message = await starboard_channel.fetch_message(
                existing[0]
            )

            await old_message.edit(embed=embed)
            return

        except discord.NotFound:
            pass

        except discord.HTTPException:
            return

    try:

        posted = await starboard_channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none()
        )

        await bot.db.execute(
            """
            INSERT OR REPLACE INTO starboard_messages
            (source_message_id, guild_id,
             starboard_message_id, channel_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                source_message.id,
                guild.id,
                posted.id,
                starboard_channel.id
            )
        )

        await bot.db.commit()

    except discord.HTTPException:
        logger.exception("Starboard message could not be published.")


@bot.listen("on_raw_reaction_add")
async def malarvaadi_starboard_add(payload):

    await process_starboard_reaction(
        payload,
        True
    )


@bot.listen("on_raw_reaction_remove")
async def malarvaadi_starboard_remove(payload):

    await process_starboard_reaction(
        payload,
        False
    )


# ============================================================
# STICKY MESSAGE SYSTEM
# ============================================================

@bot.hybrid_command(
    name="setsticky",
    description="Set a sticky message for a channel."
)
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
async def setsticky(
    ctx,
    channel: discord.TextChannel,
    *,
    message: str
):

    await ensure_starboard_schema()

    if not 1 <= len(message) <= 1800:
        return await ctx.send(
            "❌ Sticky message must contain 1–1800 characters."
        )

    await bot.db.execute(
        """
        INSERT INTO sticky_messages
        (channel_id, guild_id, message, last_message_id)
        VALUES (?, ?, ?, NULL)
        ON CONFLICT(channel_id)
        DO UPDATE SET
            message = excluded.message,
            guild_id = excluded.guild_id,
            last_message_id = NULL
        """,
        (channel.id, ctx.guild.id, message)
    )

    await bot.db.commit()

    await ctx.send(
        f"📌 Sticky message configured for {channel.mention}."
    )


# ------------------------------------------------------------
# REMOVE STICKY MESSAGE
# ------------------------------------------------------------

@bot.hybrid_command(
    name="removesticky",
    description="Remove a channel's sticky message."
)
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
async def removesticky(
    ctx,
    channel: discord.TextChannel
):

    await ensure_starboard_schema()

    cursor = await bot.db.execute(
        """
        SELECT last_message_id
        FROM sticky_messages
        WHERE channel_id = ? AND guild_id = ?
        """,
        (channel.id, ctx.guild.id)
    )

    record = await cursor.fetchone()

    if not record:
        return await ctx.send(
            "❌ No sticky message configured for that channel."
        )

    if record[0]:

        try:
            old_message = await channel.fetch_message(record[0])
            await old_message.delete()
        except discord.HTTPException:
            pass

    await bot.db.execute(
        """
        DELETE FROM sticky_messages
        WHERE channel_id = ? AND guild_id = ?
        """,
        (channel.id, ctx.guild.id)
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Sticky message removed from {channel.mention}."
    )


# ------------------------------------------------------------
# STICKY MESSAGE LISTENER
# ------------------------------------------------------------

@bot.listen("on_message")
async def malarvaadi_sticky_listener(message):

    if message.author.bot or message.guild is None:
        return

    await ensure_starboard_schema()

    cursor = await bot.db.execute(
        """
        SELECT message, last_message_id
        FROM sticky_messages
        WHERE channel_id = ?
        """,
        (message.channel.id,)
    )

    record = await cursor.fetchone()

    if not record:
        return

    sticky_text, previous_message_id = record

    if previous_message_id:

        try:
            previous = await message.channel.fetch_message(
                previous_message_id
            )
            await previous.delete()
        except discord.HTTPException:
            pass

    try:

        embed = make_embed(
            "📌 Sticky Message",
            sticky_text
        )

        sticky = await message.channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none()
        )

        await bot.db.execute(
            """
            UPDATE sticky_messages
            SET last_message_id = ?
            WHERE channel_id = ?
            """,
            (sticky.id, message.channel.id)
        )

        await bot.db.commit()

    except discord.HTTPException:
        logger.exception("Sticky message could not be reposted.")


# ============================================================
# END OF STARBOARD & STICKY ENGINE
# ============================================================

# ============================================================
#       MALARVAADI VERIFICATION & ANTI-RAID ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_security_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS security_config (
            guild_id INTEGER PRIMARY KEY,
            verification_channel_id INTEGER,
            verification_role_id INTEGER,
            verified_role_id INTEGER,
            log_channel_id INTEGER,
            min_account_age_days INTEGER DEFAULT 0,
            raid_enabled INTEGER DEFAULT 1,
            raid_threshold INTEGER DEFAULT 8,
            raid_window INTEGER DEFAULT 20,
            lockdown INTEGER DEFAULT 0
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS verified_members (
            guild_id INTEGER,
            user_id INTEGER,
            verified_at INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    await bot.db.commit()


# ------------------------------------------------------------
# CONFIGURATION HELPERS
# ------------------------------------------------------------

async def get_security_config(guild_id):

    await ensure_security_schema()

    cursor = await bot.db.execute(
        """
        SELECT verification_channel_id,
               verification_role_id,
               verified_role_id,
               log_channel_id,
               min_account_age_days,
               raid_enabled,
               raid_threshold,
               raid_window,
               lockdown
        FROM security_config
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    return await cursor.fetchone()


async def update_security_config(guild_id, column, value):

    allowed_columns = {
        "verification_channel_id",
        "verification_role_id",
        "verified_role_id",
        "log_channel_id",
        "min_account_age_days",
        "raid_enabled",
        "raid_threshold",
        "raid_window",
        "lockdown"
    }

    if column not in allowed_columns:
        raise ValueError("Invalid security configuration field.")

    await ensure_security_schema()

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO security_config (guild_id)
        VALUES (?)
        """,
        (guild_id,)
    )

    await bot.db.execute(
        f"""
        UPDATE security_config
        SET {column} = ?
        WHERE guild_id = ?
        """,
        (value, guild_id)
    )

    await bot.db.commit()


# ------------------------------------------------------------
# SECURITY LOGGING
# ------------------------------------------------------------

async def security_log(guild, title, description):

    config = await get_security_config(guild.id)

    if not config or not config[3]:
        return

    channel = guild.get_channel(config[3])

    if channel is None:
        return

    embed = make_embed(
        title,
        description,
        COLOR
    )

    try:
        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none()
        )
    except discord.HTTPException:
        logger.warning("Security log could not be delivered.")


# ============================================================
# VERIFICATION VIEW
# ============================================================

class MalarvaadiVerificationView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify Me",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="malarvaadi:verify:button"
    )
    async def verify_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if interaction.guild is None:
            return await interaction.response.send_message(
                "This button only works inside a server.",
                ephemeral=True
            )

        guild = interaction.guild
        member = interaction.user

        config = await get_security_config(guild.id)

        if not config or not config[2]:
            return await interaction.response.send_message(
                "❌ Verification has not been configured.",
                ephemeral=True
            )

        (
            verification_channel_id,
            verification_role_id,
            verified_role_id,
            log_channel_id,
            min_age,
            raid_enabled,
            raid_threshold,
            raid_window,
            lockdown
        ) = config

        if verification_channel_id and interaction.channel_id != verification_channel_id:
            return await interaction.response.send_message(
                "❌ Please verify in the designated verification channel.",
                ephemeral=True
            )

        if member.bot:
            return await interaction.response.send_message(
                "Bots do not need member verification.",
                ephemeral=True
            )

        if min_age:
            account_age = (
                discord.utils.utcnow() - member.created_at
            ).total_seconds() / 86400

            if account_age < min_age:
                return await interaction.response.send_message(
                    f"❌ Your account must be at least {min_age} days old.",
                    ephemeral=True
                )

        role = guild.get_role(verified_role_id)

        if role is None:
            return await interaction.response.send_message(
                "❌ The configured verified role no longer exists.",
                ephemeral=True
            )

        if not reaction_role_is_assignable(guild, role):
            return await interaction.response.send_message(
                "❌ The bot cannot assign the verified role. "
                "Check the role hierarchy and Manage Roles permission.",
                ephemeral=True
            )

        if role in member.roles:
            return await interaction.response.send_message(
                "✅ You are already verified!",
                ephemeral=True
            )

        try:

            await member.add_roles(
                role,
                reason="Malarvaadi member verification"
            )

            await bot.db.execute(
                """
                INSERT OR REPLACE INTO verified_members
                (guild_id, user_id, verified_at)
                VALUES (?, ?, ?)
                """,
                (
                    guild.id,
                    member.id,
                    int(time.time())
                )
            )

            await bot.db.commit()

            await interaction.response.send_message(
                "🎉 Verification successful! Welcome to the community.",
                ephemeral=True
            )

            await security_log(
                guild,
                "✅ Member Verified",
                f"{member.mention} has completed verification."
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ I don't have permission to assign your role.",
                ephemeral=True
            )

        except discord.HTTPException:

            logger.exception("Verification failed.")

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Verification failed. Please try again.",
                    ephemeral=True
                )


# Register the persistent verification button.
bot.add_view(MalarvaadiVerificationView())


# ------------------------------------------------------------
# VERIFICATION PANEL COMMAND
# ------------------------------------------------------------

@bot.hybrid_command(
    name="verificationpanel",
    description="Publish the member verification panel."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def verificationpanel(
    ctx,
    channel: discord.TextChannel
):

    await ensure_security_schema()

    await update_security_config(
        ctx.guild.id,
        "verification_channel_id",
        channel.id
    )

    embed = make_embed(
        "🛡️ Server Verification",
        "Welcome to our community!\n\n"
        "Click the button below to verify your membership "
        "and unlock the server."
    )

    embed.add_field(
        name="Verification",
        value="Press **Verify Me** to continue.",
        inline=False
    )

    await channel.send(
        embed=embed,
        view=MalarvaadiVerificationView()
    )

    await ctx.send(
        f"✅ Verification panel published in {channel.mention}."
    )


# ------------------------------------------------------------
# SET VERIFIED ROLE
# ------------------------------------------------------------

@bot.hybrid_command(
    name="setverifiedrole",
    description="Set the role awarded after verification."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setverifiedrole(ctx, role: discord.Role):

    if not reaction_role_is_assignable(ctx.guild, role):
        return await ctx.send(
            "❌ The bot cannot assign that role. "
            "Check role hierarchy."
        )

    await update_security_config(
        ctx.guild.id,
        "verified_role_id",
        role.id
    )

    await ctx.send(
        f"✅ Verified role configured: {role.mention}"
    )


# ------------------------------------------------------------
# SET SECURITY LOG CHANNEL
# ------------------------------------------------------------

@bot.command(
    name="setsecuritylog",
    description="Configure the security log channel."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setsecuritylog(ctx, channel: discord.TextChannel):

    await update_security_config(
        ctx.guild.id,
        "log_channel_id",
        channel.id
    )

    await ctx.send(
        f"✅ Security logs will be sent to {channel.mention}."
    )


# ------------------------------------------------------------
# ACCOUNT AGE REQUIREMENT
# ------------------------------------------------------------

@bot.command(
    name="setminaccountage",
    description="Set the minimum account age for verification."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setminaccountage(ctx, days: int):

    if not 0 <= days <= 365:
        return await ctx.send(
            "❌ Account age must be between 0 and 365 days."
        )

    await update_security_config(
        ctx.guild.id,
        "min_account_age_days",
        days
    )

    await ctx.send(
        f"✅ Minimum account age set to {days} days."
    )


# ============================================================
# ANTI-RAID ENGINE
# ============================================================

RAID_JOIN_HISTORY = defaultdict(list)

async def process_raid_join(member):

    if member.bot:
        return

    config = await get_security_config(member.guild.id)

    if not config:
        return

    (
        verification_channel_id,
        verification_role_id,
        verified_role_id,
        log_channel_id,
        min_age,
        raid_enabled,
        raid_threshold,
        raid_window,
        lockdown
    ) = config

    if not raid_enabled:
        return

    now = time.time()
    history = RAID_JOIN_HISTORY[member.guild.id]

    history.append(now)

    cutoff = now - raid_window

    RAID_JOIN_HISTORY[member.guild.id] = [
        timestamp
        for timestamp in history
        if timestamp >= cutoff
    ]

    join_count = len(RAID_JOIN_HISTORY[member.guild.id])

    if join_count >= raid_threshold and not lockdown:

        await update_security_config(
            member.guild.id,
            "lockdown",
            1
        )

        await security_log(
            member.guild,
            "🚨 Possible Raid Detected",
            f"**Recent joins:** {join_count}\n"
            f"**Time window:** {raid_window} seconds\n"
            f"**Latest member:** {member.mention}\n\n"
            "Automatic lockdown flag enabled. "
            "Administrator review is required."
        )


@bot.listen("on_member_join")
async def malarvaadi_anti_raid_listener(member):

    try:
        await process_raid_join(member)
    except Exception:
        logger.exception("Anti-raid processing failed.")


# ------------------------------------------------------------
# CONFIGURE ANTI-RAID
# ------------------------------------------------------------

@bot.hybrid_command(
    name="antiraid",
    description="Configure the anti-raid detection system."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def antiraid(
    ctx,
    action: str,
    threshold: int = 8,
    window: int = 20
):

    action = action.lower()

    if action not in ("enable", "disable"):
        return await ctx.send(
            "❌ Use `enable` or `disable`."
        )

    if not 2 <= threshold <= 100:
        return await ctx.send(
            "❌ Threshold must be between 2 and 100."
        )

    if not 5 <= window <= 300:
        return await ctx.send(
            "❌ Window must be between 5 and 300 seconds."
        )

    await update_security_config(
        ctx.guild.id,
        "raid_enabled",
        1 if action == "enable" else 0
    )

    await update_security_config(
        ctx.guild.id,
        "raid_threshold",
        threshold
    )

    await update_security_config(
        ctx.guild.id,
        "raid_window",
        window
    )

    await ctx.send(
        f"🛡️ Anti-raid {action}d.\n"
        f"Threshold: `{threshold}` joins\n"
        f"Window: `{window}` seconds"
    )


# ------------------------------------------------------------
# SECURITY STATUS
# ------------------------------------------------------------

@bot.command(
    name="securitystatus",
    description="View server security configuration."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def securitystatus(ctx):

    config = await get_security_config(ctx.guild.id)

    if not config:
        return await ctx.send(
            "❌ Security configuration has not been initialized."
        )

    (
        verification_channel_id,
        verification_role_id,
        verified_role_id,
        log_channel_id,
        min_age,
        raid_enabled,
        raid_threshold,
        raid_window,
        lockdown
    ) = config

    embed = make_embed(
        "🛡️ Malarvaadi Security Status",
        "Current server security configuration."
    )

    embed.add_field(
        name="Verification Channel",
        value=f"<#{verification_channel_id}>" if verification_channel_id else "Not configured",
        inline=True
    )

    embed.add_field(
        name="Verified Role",
        value=f"<@&{verified_role_id}>" if verified_role_id else "Not configured",
        inline=True
    )

    embed.add_field(
        name="Security Logs",
        value=f"<#{log_channel_id}>" if log_channel_id else "Not configured",
        inline=True
    )

    embed.add_field(
        name="Minimum Account Age",
        value=f"{min_age} days",
        inline=True
    )

    embed.add_field(
        name="Anti-Raid",
        value="Enabled" if raid_enabled else "Disabled",
        inline=True
    )

    embed.add_field(
        name="Raid Threshold",
        value=f"{raid_threshold} joins / {raid_window}s",
        inline=True
    )

    embed.add_field(
        name="Lockdown Flag",
        value="Active" if lockdown else "Inactive",
        inline=True
    )

    await ctx.send(embed=embed)


# ============================================================
# END OF VERIFICATION & ANTI-RAID ENGINE
# ============================================================

# ============================================================
#       MALARVAADI SERVER STATISTICS & ANALYTICS
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_analytics_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS server_analytics (
            guild_id INTEGER PRIMARY KEY,
            total_joins INTEGER DEFAULT 0,
            total_leaves INTEGER DEFAULT 0,
            messages_today INTEGER DEFAULT 0,
            last_reset INTEGER DEFAULT 0
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS member_activity (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            messages INTEGER DEFAULT 0,
            last_message INTEGER DEFAULT 0,
            PRIMARY KEY(guild_id, user_id)
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS daily_analytics (
            guild_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            joins INTEGER DEFAULT 0,
            leaves INTEGER DEFAULT 0,
            messages INTEGER DEFAULT 0,
            PRIMARY KEY(guild_id, date)
        )
    """)

    await bot.db.commit()


# ------------------------------------------------------------
# DATE HELPER
# ------------------------------------------------------------

def analytics_today():

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ------------------------------------------------------------
# ENSURE GUILD ANALYTICS
# ------------------------------------------------------------

async def ensure_guild_analytics(guild_id):

    await ensure_analytics_schema()

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO server_analytics
        (guild_id, total_joins, total_leaves,
         messages_today, last_reset)
        VALUES (?, 0, 0, 0, ?)
        """,
        (guild_id, int(time.time()))
    )

    await bot.db.commit()


# ------------------------------------------------------------
# RECORD MEMBER JOIN
# ------------------------------------------------------------

async def record_analytics_join(guild_id):

    await ensure_guild_analytics(guild_id)

    today = analytics_today()

    await bot.db.execute(
        """
        UPDATE server_analytics
        SET total_joins = total_joins + 1
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    await bot.db.execute(
        """
        INSERT INTO daily_analytics
        (guild_id, date, joins, leaves, messages)
        VALUES (?, ?, 1, 0, 0)
        ON CONFLICT(guild_id, date)
        DO UPDATE SET joins = joins + 1
        """,
        (guild_id, today)
    )

    await bot.db.commit()


# ------------------------------------------------------------
# RECORD MEMBER LEAVE
# ------------------------------------------------------------

async def record_analytics_leave(guild_id):

    await ensure_guild_analytics(guild_id)

    today = analytics_today()

    await bot.db.execute(
        """
        UPDATE server_analytics
        SET total_leaves = total_leaves + 1
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    await bot.db.execute(
        """
        INSERT INTO daily_analytics
        (guild_id, date, joins, leaves, messages)
        VALUES (?, ?, 0, 1, 0)
        ON CONFLICT(guild_id, date)
        DO UPDATE SET leaves = leaves + 1
        """,
        (guild_id, today)
    )

    await bot.db.commit()


# ------------------------------------------------------------
# RECORD MESSAGE ACTIVITY
# ------------------------------------------------------------

async def record_message_activity(guild_id, user_id):

    await ensure_guild_analytics(guild_id)

    now = int(time.time())
    today = analytics_today()

    await bot.db.execute(
        """
        INSERT INTO member_activity
        (guild_id, user_id, messages, last_message)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(guild_id, user_id)
        DO UPDATE SET
            messages = messages + 1,
            last_message = excluded.last_message
        """,
        (guild_id, user_id, now)
    )

    await bot.db.execute(
        """
        UPDATE server_analytics
        SET messages_today = messages_today + 1
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    await bot.db.execute(
        """
        INSERT INTO daily_analytics
        (guild_id, date, joins, leaves, messages)
        VALUES (?, ?, 0, 0, 1)
        ON CONFLICT(guild_id, date)
        DO UPDATE SET messages = messages + 1
        """,
        (guild_id, today)
    )

    await bot.db.commit()


# ------------------------------------------------------------
# ANALYTICS EVENT LISTENERS
# ------------------------------------------------------------

@bot.listen("on_member_join")
async def malarvaadi_analytics_join(member):

    try:
        await record_analytics_join(member.guild.id)
    except Exception:
        logger.exception("Analytics join tracking failed.")


@bot.listen("on_member_remove")
async def malarvaadi_analytics_leave(member):

    try:
        await record_analytics_leave(member.guild.id)
    except Exception:
        logger.exception("Analytics leave tracking failed.")


@bot.listen("on_message")
async def malarvaadi_analytics_message(message):

    if message.guild is None or message.author.bot:
        return

    try:
        await record_message_activity(
            message.guild.id,
            message.author.id
        )
    except Exception:
        logger.exception("Analytics message tracking failed.")


# ============================================================
# ANALYTICS COMMANDS
# ============================================================

# ------------------------------------------------------------
# SERVER ANALYTICS DASHBOARD
# ------------------------------------------------------------

@bot.hybrid_command(
    name="serverstats",
    description="View the server analytics dashboard."
)
@commands.guild_only()
async def serverstats(ctx):

    await ensure_guild_analytics(ctx.guild.id)

    cursor = await bot.db.execute(
        """
        SELECT total_joins, total_leaves, messages_today
        FROM server_analytics
        WHERE guild_id = ?
        """,
        (ctx.guild.id,)
    )

    total_joins, total_leaves, messages_today = (
        await cursor.fetchone()
    )

    cursor = await bot.db.execute(
        """
        SELECT COUNT(*)
        FROM member_activity
        WHERE guild_id = ?
        """,
        (ctx.guild.id,)
    )

    tracked_members = (await cursor.fetchone())[0]

    embed = make_embed(
        "📊 Server Analytics Dashboard",
        f"Statistics for **{ctx.guild.name}**"
    )

    embed.set_thumbnail(
        url=ctx.guild.icon.url if ctx.guild.icon else discord.Embed.Empty
    )

    embed.add_field(
        name="👥 Current Members",
        value=f"`{ctx.guild.member_count}`",
        inline=True
    )

    embed.add_field(
        name="📥 Total Joins",
        value=f"`{total_joins}`",
        inline=True
    )

    embed.add_field(
        name="📤 Total Leaves",
        value=f"`{total_leaves}`",
        inline=True
    )

    embed.add_field(
        name="💬 Messages Today",
        value=f"`{messages_today}`",
        inline=True
    )

    embed.add_field(
        name="📈 Tracked Members",
        value=f"`{tracked_members}`",
        inline=True
    )

    embed.add_field(
        name="📅 Server Created",
        value=f"<t:{int(ctx.guild.created_at.timestamp())}:D>",
        inline=True
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# TOP ACTIVE MEMBERS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="activityleaderboard",
    description="View the most active server members."
)
@commands.guild_only()
async def activityleaderboard(ctx):

    await ensure_analytics_schema()

    cursor = await bot.db.execute(
        """
        SELECT user_id, messages
        FROM member_activity
        WHERE guild_id = ?
        ORDER BY messages DESC
        LIMIT 10
        """,
        (ctx.guild.id,)
    )

    records = await cursor.fetchall()

    if not records:
        return await ctx.send(
            "📭 No activity data has been collected yet."
        )

    description = []

    for index, (user_id, messages) in enumerate(records, 1):

        member = ctx.guild.get_member(user_id)

        name = member.display_name if member else f"User {user_id}"

        description.append(
            f"**{index}.** {name} — `{messages}` messages"
        )

    embed = make_embed(
        "🏆 Activity Leaderboard",
        "\n".join(description)
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# DAILY ANALYTICS
# ------------------------------------------------------------

@bot.command(
    name="dailyreport",
    description="View today's server activity report."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def dailyreport(ctx):

    await ensure_analytics_schema()

    today = analytics_today()

    cursor = await bot.db.execute(
        """
        SELECT joins, leaves, messages
        FROM daily_analytics
        WHERE guild_id = ? AND date = ?
        """,
        (ctx.guild.id, today)
    )

    record = await cursor.fetchone()

    if not record:
        joins, leaves, messages = 0, 0, 0
    else:
        joins, leaves, messages = record

    embed = make_embed(
        "📅 Daily Server Report",
        f"Activity report for **{today}**."
    )

    embed.add_field(
        name="📥 New Members",
        value=f"`{joins}`",
        inline=True
    )

    embed.add_field(
        name="📤 Departures",
        value=f"`{leaves}`",
        inline=True
    )

    embed.add_field(
        name="💬 Messages",
        value=f"`{messages}`",
        inline=True
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# WEEKLY ANALYTICS
# ------------------------------------------------------------

@bot.command(
    name="weeklyreport",
    description="View the last seven days of server activity."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def weeklyreport(ctx):

    await ensure_analytics_schema()

    today = datetime.now(timezone.utc).date()
    start_date = (today - timedelta(days=6)).strftime("%Y-%m-%d")

    cursor = await bot.db.execute(
        """
        SELECT
            COALESCE(SUM(joins), 0),
            COALESCE(SUM(leaves), 0),
            COALESCE(SUM(messages), 0)
        FROM daily_analytics
        WHERE guild_id = ?
        AND date >= ?
        """,
        (ctx.guild.id, start_date)
    )

    joins, leaves, messages = await cursor.fetchone()

    embed = make_embed(
        "📈 Weekly Server Report",
        "Activity over the last seven days."
    )

    embed.add_field(
        name="📥 New Members",
        value=f"`{joins}`",
        inline=True
    )

    embed.add_field(
        name="📤 Departures",
        value=f"`{leaves}`",
        inline=True
    )

    embed.add_field(
        name="💬 Messages",
        value=f"`{messages}`",
        inline=True
    )

    await ctx.send(embed=embed)


# ============================================================
# END OF SERVER ANALYTICS ENGINE
# ============================================================

# ============================================================
#       MALARVAADI TEMPORARY VOICE CHANNEL ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_voice_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS voice_config (
            guild_id INTEGER PRIMARY KEY,
            lobby_channel_id INTEGER,
            category_id INTEGER
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS temporary_voice_rooms (
            channel_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            locked INTEGER DEFAULT 0
        )
    """)

    await bot.db.commit()


# ------------------------------------------------------------
# VOICE CONFIGURATION
# ------------------------------------------------------------

async def get_voice_config(guild_id):

    await ensure_voice_schema()

    cursor = await bot.db.execute(
        """
        SELECT lobby_channel_id, category_id
        FROM voice_config
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    return await cursor.fetchone()


# ------------------------------------------------------------
# SET JOIN-TO-CREATE LOBBY
# ------------------------------------------------------------

@bot.hybrid_command(
    name="setvoicecreate",
    description="Configure the Join-to-Create voice lobby."
)
@commands.guild_only()
@commands.has_permissions(manage_channels=True)
async def setvoicecreate(
    ctx,
    lobby: discord.VoiceChannel,
    category: discord.CategoryChannel = None
):

    await ensure_voice_schema()

    if category is None:
        category = lobby.category

    await bot.db.execute(
        """
        INSERT INTO voice_config
        (guild_id, lobby_channel_id, category_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id)
        DO UPDATE SET
            lobby_channel_id = excluded.lobby_channel_id,
            category_id = excluded.category_id
        """,
        (
            ctx.guild.id,
            lobby.id,
            category.id if category else None
        )
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Join-to-Create configured!\n"
        f"Lobby: {lobby.mention}\n"
        f"Category: {category.name if category else 'None'}"
    )


# ------------------------------------------------------------
# DISABLE JOIN-TO-CREATE
# ------------------------------------------------------------

@bot.command(
    name="disablevoicecreate",
    description="Disable Join-to-Create."
)
@commands.guild_only()
@commands.has_permissions(manage_channels=True)
async def disablevoicecreate(ctx):

    await ensure_voice_schema()

    await bot.db.execute(
        "DELETE FROM voice_config WHERE guild_id = ?",
        (ctx.guild.id,)
    )

    await bot.db.commit()

    await ctx.send("✅ Join-to-Create disabled.")


# ------------------------------------------------------------
# CREATE TEMPORARY ROOM
# ------------------------------------------------------------

async def create_temporary_voice_room(member, category):

    guild = member.guild

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            connect=True
        ),
        member: discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            manage_channels=True,
            move_members=True
        )
    }

    room = await guild.create_voice_channel(
        name=f"🔊 {member.display_name}'s Room",
        category=category,
        overwrites=overwrites,
        reason="Malarvaadi Join-to-Create"
    )

    await bot.db.execute(
        """
        INSERT OR REPLACE INTO temporary_voice_rooms
        (channel_id, guild_id, owner_id, locked)
        VALUES (?, ?, ?, 0)
        """,
        (room.id, guild.id, member.id)
    )

    await bot.db.commit()

    try:
        await member.move_to(room)
    except discord.HTTPException:
        await room.delete(
            reason="Could not move room owner into temporary room"
        )
        await bot.db.execute(
            "DELETE FROM temporary_voice_rooms WHERE channel_id = ?",
            (room.id,)
        )
        await bot.db.commit()
        raise

    return room


# ------------------------------------------------------------
# VOICE JOIN LISTENER
# ------------------------------------------------------------

@bot.listen("on_voice_state_update")
async def malarvaadi_voice_create_listener(
    member,
    before,
    after
):

    if member.bot or after.channel is None:
        return

    await ensure_voice_schema()

    config = await get_voice_config(member.guild.id)

    if not config:
        return

    lobby_id, category_id = config

    if after.channel.id != lobby_id:
        return

    category = (
        member.guild.get_channel(category_id)
        if category_id else after.channel.category
    )

    try:
        await create_temporary_voice_room(
            member,
            category
        )
    except discord.Forbidden:
        logger.warning(
            "Missing permissions to create temporary voice room."
        )
    except discord.HTTPException:
        logger.exception(
            "Temporary voice room creation failed."
        )


# ------------------------------------------------------------
# TEMPORARY ROOM CLEANUP
# ------------------------------------------------------------

@bot.listen("on_voice_state_update")
async def malarvaadi_voice_cleanup_listener(
    member,
    before,
    after
):

    if before.channel is None:
        return

    await ensure_voice_schema()

    cursor = await bot.db.execute(
        """
        SELECT channel_id
        FROM temporary_voice_rooms
        WHERE channel_id = ?
        """,
        (before.channel.id,)
    )

    record = await cursor.fetchone()

    if not record:
        return

    channel = before.channel

    if len(channel.members) > 0:
        return

    try:
        await channel.delete(
            reason="Malarvaadi temporary room is empty"
        )
    except discord.HTTPException:
        logger.exception(
            "Temporary voice room deletion failed."
        )
        return

    await bot.db.execute(
        """
        DELETE FROM temporary_voice_rooms
        WHERE channel_id = ?
        """,
        (channel.id,)
    )

    await bot.db.commit()


# ------------------------------------------------------------
# ROOM OWNER CHECK
# ------------------------------------------------------------

async def get_owned_voice_room(ctx):

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(
            "❌ Join your temporary voice room first."
        )
        return None

    channel = ctx.author.voice.channel

    cursor = await bot.db.execute(
        """
        SELECT owner_id
        FROM temporary_voice_rooms
        WHERE channel_id = ?
        AND guild_id = ?
        """,
        (channel.id, ctx.guild.id)
    )

    record = await cursor.fetchone()

    if not record:
        await ctx.send(
            "❌ This is not a Malarvaadi temporary room."
        )
        return None

    if record[0] != ctx.author.id and ctx.author.id != ctx.guild.owner_id:
        await ctx.send(
            "❌ Only the room owner can use this command."
        )
        return None

    return channel


# ------------------------------------------------------------
# RENAME ROOM
# ------------------------------------------------------------

@bot.hybrid_command(
    name="roomname",
    description="Rename your temporary voice room."
)
@commands.guild_only()
async def roomname(ctx, *, name: str):

    if not 1 <= len(name) <= 90:
        return await ctx.send("❌ Room name must be 1–90 characters.")

    channel = await get_owned_voice_room(ctx)

    if channel is None:
        return

    try:
        await channel.edit(name=name)
        await ctx.send(f"✅ Room renamed to **{name}**.")
    except discord.Forbidden:
        await ctx.send("❌ I cannot rename this room.")


# ------------------------------------------------------------
# SET ROOM LIMIT
# ------------------------------------------------------------

@bot.hybrid_command(
    name="roomlimit",
    description="Set the member limit for your room."
)
@commands.guild_only()
async def roomlimit(ctx, limit: int):

    if not 0 <= limit <= 99:
        return await ctx.send(
            "❌ Limit must be between 0 and 99. Use 0 for unlimited."
        )

    channel = await get_owned_voice_room(ctx)

    if channel is None:
        return

    try:
        await channel.edit(user_limit=limit)

        await ctx.send(
            f"✅ Room limit set to `{limit or 'Unlimited'}`."
        )

    except discord.Forbidden:
        await ctx.send("❌ I cannot change this room limit.")


# ------------------------------------------------------------
# LOCK ROOM
# ------------------------------------------------------------

@bot.hybrid_command(
    name="roomlock",
    description="Lock your temporary voice room."
)
@commands.guild_only()
async def roomlock(ctx):

    channel = await get_owned_voice_room(ctx)

    if channel is None:
        return

    try:

        overwrite = channel.overwrites_for(
            ctx.guild.default_role
        )

        overwrite.connect = False

        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrite
        )

        await bot.db.execute(
            """
            UPDATE temporary_voice_rooms
            SET locked = 1
            WHERE channel_id = ?
            """,
            (channel.id,)
        )

        await bot.db.commit()

        await ctx.send("🔒 Your voice room is now locked.")

    except discord.Forbidden:
        await ctx.send("❌ I cannot lock this room.")


# ------------------------------------------------------------
# UNLOCK ROOM
# ------------------------------------------------------------

@bot.hybrid_command(
    name="roomunlock",
    description="Unlock your temporary voice room."
)
@commands.guild_only()
async def roomunlock(ctx):

    channel = await get_owned_voice_room(ctx)

    if channel is None:
        return

    try:

        overwrite = channel.overwrites_for(
            ctx.guild.default_role
        )

        overwrite.connect = None

        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrite
        )

        await bot.db.execute(
            """
            UPDATE temporary_voice_rooms
            SET locked = 0
            WHERE channel_id = ?
            """,
            (channel.id,)
        )

        await bot.db.commit()

        await ctx.send("🔓 Your voice room is now unlocked.")

    except discord.Forbidden:
        await ctx.send("❌ I cannot unlock this room.")


# ------------------------------------------------------------
# TRANSFER ROOM OWNERSHIP
# ------------------------------------------------------------

@bot.command(
    name="roomtransfer",
    description="Transfer your temporary room to another member."
)
@commands.guild_only()
async def roomtransfer(ctx, member: discord.Member):

    channel = await get_owned_voice_room(ctx)

    if channel is None:
        return

    if member.bot or member.id == ctx.author.id:
        return await ctx.send(
            "❌ Choose another human server member."
        )

    if member not in channel.members:
        return await ctx.send(
            "❌ The new owner must be inside your room."
        )

    await bot.db.execute(
        """
        UPDATE temporary_voice_rooms
        SET owner_id = ?
        WHERE channel_id = ?
        """,
        (member.id, channel.id)
    )

    await bot.db.commit()

    await ctx.send(
        f"👑 Room ownership transferred to {member.mention}."
    )


# ------------------------------------------------------------
# ROOM INFORMATION
# ------------------------------------------------------------

@bot.hybrid_command(
    name="roominfo",
    description="View your temporary voice room information."
)
@commands.guild_only()
async def roominfo(ctx):

    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send(
            "❌ Join a voice channel first."
        )

    channel = ctx.author.voice.channel

    cursor = await bot.db.execute(
        """
        SELECT owner_id, locked
        FROM temporary_voice_rooms
        WHERE channel_id = ?
        """,
        (channel.id,)
    )

    record = await cursor.fetchone()

    if not record:
        return await ctx.send(
            "❌ This is not a temporary room."
        )

    owner = ctx.guild.get_member(record[0])

    embed = make_embed(
        "🎙️ Temporary Room Information",
        f"**Room:** {channel.name}\n"
        f"**Owner:** {owner.mention if owner else 'Unknown'}\n"
        f"**Members:** {len(channel.members)}\n"
        f"**Limit:** {channel.user_limit or 'Unlimited'}\n"
        f"**Locked:** {'Yes' if record[1] else 'No'}"
    )

    await ctx.send(embed=embed)


# ============================================================
# END OF TEMPORARY VOICE ENGINE
# ============================================================

# ============================================================
#       MALARVAADI ADVANCED GAMES ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_games_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS game_stats (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    await bot.db.commit()


async def record_game(guild_id, user_id, won):

    await ensure_games_schema()

    await bot.db.execute(
        """
        INSERT INTO game_stats
        (guild_id, user_id, wins, losses, games_played)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(guild_id, user_id)
        DO UPDATE SET
            wins = wins + excluded.wins,
            losses = losses + excluded.losses,
            games_played = games_played + 1
        """,
        (
            guild_id,
            user_id,
            1 if won else 0,
            0 if won else 1
        )
    )

    await bot.db.commit()


# ------------------------------------------------------------
# COIN FLIP
# ------------------------------------------------------------

@bot.hybrid_command(
    name="coinflip",
    description="Flip a coin."
)
@commands.guild_only()
async def coinflip(ctx):

    result = random.choice(["Heads", "Tails"])

    embed = make_embed(
        "🪙 Coin Flip",
        f"The coin landed on **{result}**!"
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# DICE ROLL
# ------------------------------------------------------------

@bot.hybrid_command(
    name="dice",
    description="Roll one or more dice."
)
@commands.guild_only()
async def dice(ctx, sides: int = 6, amount: int = 1):

    if not 2 <= sides <= 100:
        return await ctx.send(
            "❌ Dice must have between 2 and 100 sides."
        )

    if not 1 <= amount <= 10:
        return await ctx.send(
            "❌ You can roll between 1 and 10 dice."
        )

    results = [
        random.randint(1, sides)
        for _ in range(amount)
    ]

    embed = make_embed(
        "🎲 Dice Roll",
        f"**Results:** {', '.join(map(str, results))}\n"
        f"**Total:** {sum(results)}"
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# ROCK PAPER SCISSORS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="rps",
    description="Play Rock Paper Scissors."
)
@commands.guild_only()
async def rps(ctx, choice: str):

    choice = choice.lower()

    choices = ["rock", "paper", "scissors"]

    if choice not in choices:
        return await ctx.send(
            "❌ Choose rock, paper or scissors."
        )

    bot_choice = random.choice(choices)

    if choice == bot_choice:
        result = "🤝 It's a draw!"
        outcome = None

    elif (
        (choice == "rock" and bot_choice == "scissors")
        or (choice == "paper" and bot_choice == "rock")
        or (choice == "scissors" and bot_choice == "paper")
    ):
        result = "🏆 You win!"
        outcome = True

    else:
        result = "💀 You lose!"
        outcome = False

    if outcome is not None:
        await record_game(
            ctx.guild.id,
            ctx.author.id,
            outcome
        )

    embed = make_embed(
        "✂️ Rock Paper Scissors",
        f"**Your choice:** {choice.title()}\n"
        f"**My choice:** {bot_choice.title()}\n\n"
        f"{result}"
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# NUMBER GUESSING
# ------------------------------------------------------------

NUMBER_GAMES = {}


@bot.hybrid_command(
    name="guess",
    description="Start a number guessing game."
)
@commands.guild_only()
async def guess(ctx):

    key = (ctx.guild.id, ctx.author.id)

    if key in NUMBER_GAMES:
        return await ctx.send(
            "❌ You already have an active guessing game."
        )

    number = random.randint(1, 100)

    NUMBER_GAMES[key] = {
        "number": number,
        "attempts": 0
    }

    await ctx.send(
        "🔢 **Number Guessing Game!**\n"
        "I'm thinking of a number between **1 and 100**.\n"
        "You have **7 attempts**.\n"
        "Use `+guessnumber <number>` to guess."
    )


@bot.hybrid_command(
    name="guessnumber",
    description="Submit your number guessing attempt."
)
@commands.guild_only()
async def guessnumber(ctx, number: int):

    key = (ctx.guild.id, ctx.author.id)

    game = NUMBER_GAMES.get(key)

    if game is None:
        return await ctx.send(
            "❌ Start a game first using `+guess`."
        )

    if not 1 <= number <= 100:
        return await ctx.send(
            "❌ Choose a number between 1 and 100."
        )

    game["attempts"] += 1

    if number == game["number"]:

        await record_game(
            ctx.guild.id,
            ctx.author.id,
            True
        )

        del NUMBER_GAMES[key]

        return await ctx.send(
            f"🏆 Correct! The number was **{number}**.\n"
            f"You guessed it in **{game['attempts']} attempts**!"
        )

    if game["attempts"] >= 7:

        answer = game["number"]

        await record_game(
            ctx.guild.id,
            ctx.author.id,
            False
        )

        del NUMBER_GAMES[key]

        return await ctx.send(
            f"💀 Game over! The number was **{answer}**."
        )

    hint = "higher" if number < game["number"] else "lower"

    await ctx.send(
        f"❌ Not quite! Try **{hint}**.\n"
        f"Attempts remaining: **{7 - game['attempts']}**"
    )


# ------------------------------------------------------------
# TRIVIA QUESTION BANK
# ------------------------------------------------------------

TRIVIA_QUESTIONS = [
    {
        "question": "Which planet is known as the Red Planet?",
        "options": ["Earth", "Mars", "Venus", "Jupiter"],
        "answer": 1
    },
    {
        "question": "What is the largest ocean on Earth?",
        "options": ["Atlantic", "Indian", "Pacific", "Arctic"],
        "answer": 2
    },
    {
        "question": "How many sides does a hexagon have?",
        "options": ["5", "6", "7", "8"],
        "answer": 1
    },
    {
        "question": "Which language is primarily used with discord.py?",
        "options": ["Java", "Python", "C++", "Ruby"],
        "answer": 1
    },
    {
        "question": "What is the chemical symbol for gold?",
        "options": ["Ag", "Fe", "Au", "Cu"],
        "answer": 2
    },
    {
        "question": "Which animal is the largest living mammal?",
        "options": ["Elephant", "Blue whale", "Giraffe", "Shark"],
        "answer": 1
    },
    {
        "question": "How many continents are there?",
        "options": ["5", "6", "7", "8"],
        "answer": 2
    }
]


TRIVIA_ACTIVE = {}


@bot.hybrid_command(
    name="trivia",
    description="Start a trivia challenge."
)
@commands.guild_only()
async def trivia(ctx):

    key = (ctx.guild.id, ctx.author.id)

    if key in TRIVIA_ACTIVE:
        return await ctx.send(
            "❌ You already have an active trivia question."
        )

    question = random.choice(TRIVIA_QUESTIONS)

    TRIVIA_ACTIVE[key] = question["answer"]

    options = "\n".join(
        f"**{index + 1}.** {option}"
        for index, option in enumerate(question["options"])
    )

    embed = make_embed(
        "🧠 Malarvaadi Trivia",
        f"**{question['question']}**\n\n"
        f"{options}\n\n"
        "Answer using `+triviaanswer <1-4>`.\n"
        "You have 30 seconds."
    )

    await ctx.send(embed=embed)

    await asyncio.sleep(30)

    if key in TRIVIA_ACTIVE:
        del TRIVIA_ACTIVE[key]


@bot.hybrid_command(
    name="triviaanswer",
    description="Answer your active trivia question."
)
@commands.guild_only()
async def triviaanswer(ctx, answer: int):

    key = (ctx.guild.id, ctx.author.id)

    if key not in TRIVIA_ACTIVE:
        return await ctx.send(
            "❌ No active trivia question. Start with `+trivia`."
        )

    if not 1 <= answer <= 4:
        return await ctx.send(
            "❌ Choose an answer between 1 and 4."
        )

    correct = TRIVIA_ACTIVE.pop(key)

    won = answer - 1 == correct

    await record_game(
        ctx.guild.id,
        ctx.author.id,
        won
    )

    if won:
        await ctx.send("🏆 Correct answer! You earned a win.")
    else:
        await ctx.send(
            f"❌ Incorrect! The correct answer was **{correct + 1}**."
        )


# ------------------------------------------------------------
# CANCEL GUESSING GAME
# ------------------------------------------------------------

@bot.hybrid_command(
    name="cancelguess",
    description="Cancel your number guessing game."
)
@commands.guild_only()
async def cancelguess(ctx):

    key = (ctx.guild.id, ctx.author.id)

    if key not in NUMBER_GAMES:
        return await ctx.send(
            "❌ You don't have an active guessing game."
        )

    del NUMBER_GAMES[key]

    await ctx.send("✅ Guessing game cancelled.")


# ------------------------------------------------------------
# GAME LEADERBOARD
# ------------------------------------------------------------

@bot.hybrid_command(
    name="gameleaderboard",
    description="View the game leaderboard."
)
@commands.guild_only()
async def gameleaderboard(ctx):

    await ensure_games_schema()

    cursor = await bot.db.execute(
        """
        SELECT user_id, wins, losses, games_played
        FROM game_stats
        WHERE guild_id = ?
        ORDER BY wins DESC, games_played ASC
        LIMIT 10
        """,
        (ctx.guild.id,)
    )

    records = await cursor.fetchall()

    if not records:
        return await ctx.send(
            "🎮 Nobody has played a tracked game yet."
        )

    lines = []

    for index, record in enumerate(records, 1):

        user_id, wins, losses, played = record

        member = ctx.guild.get_member(user_id)

        name = member.display_name if member else f"User {user_id}"

        lines.append(
            f"**{index}.** {name}\n"
            f"🏆 `{wins}` wins | 💀 `{losses}` losses | 🎮 `{played}` games"
        )

    embed = make_embed(
        "🏆 Malarvaadi Game Leaderboard",
        "\n\n".join(lines)
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# MY GAME STATISTICS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="gamestats",
    description="View your personal game statistics."
)
@commands.guild_only()
async def gamestats(ctx):

    await ensure_games_schema()

    cursor = await bot.db.execute(
        """
        SELECT wins, losses, games_played
        FROM game_stats
        WHERE guild_id = ? AND user_id = ?
        """,
        (ctx.guild.id, ctx.author.id)
    )

    record = await cursor.fetchone()

    if not record:
        wins, losses, played = 0, 0, 0
    else:
        wins, losses, played = record

    win_rate = (
        round((wins / played) * 100, 1)
        if played else 0
    )

    embed = make_embed(
        "🎮 Your Game Statistics",
        f"**Wins:** `{wins}`\n"
        f"**Losses:** `{losses}`\n"
        f"**Games played:** `{played}`\n"
        f"**Win rate:** `{win_rate}%`"
    )

    await ctx.send(embed=embed)


# ============================================================
# END OF ADVANCED GAMES ENGINE
# ============================================================

# ============================================================
#       MALARVAADI ADVANCED ADMIN ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_admin_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS disabled_commands (
            guild_id INTEGER NOT NULL,
            command_name TEXT NOT NULL,
            disabled_by INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (guild_id, command_name)
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS admin_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            moderator_id INTEGER,
            action TEXT,
            details TEXT,
            created_at INTEGER
        )
    """)

    await bot.db.commit()


# ------------------------------------------------------------
# ADMIN AUDIT LOG
# ------------------------------------------------------------

async def record_admin_action(
    guild_id,
    moderator_id,
    action,
    details=""
):

    await ensure_admin_schema()

    await bot.db.execute(
        """
        INSERT INTO admin_audit
        (guild_id, moderator_id, action, details, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            guild_id,
            moderator_id,
            action,
            details,
            int(time.time())
        )
    )

    await bot.db.commit()


# ------------------------------------------------------------
# OWNER CHECK
# ------------------------------------------------------------

def is_bot_owner(ctx):

    return (
        OWNER_ID != 0
        and ctx.author.id == OWNER_ID
    )


# ------------------------------------------------------------
# BOT DIAGNOSTICS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="botinfo",
    description="View Malarvaadi bot information."
)
@commands.guild_only()
async def botinfo(ctx):

    latency = round(bot.latency * 1000)

    uptime = int(time.time() - START_TIME)

    days, remainder = divmod(uptime, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    embed = make_embed(
        "🤖 Malarvaadi System Information",
        "Advanced Discord Community Management Bot"
    )

    embed.add_field(
        name="Version",
        value=f"`{BOT_VERSION}`",
        inline=True
    )

    embed.add_field(
        name="Latency",
        value=f"`{latency} ms`",
        inline=True
    )

    embed.add_field(
        name="Servers",
        value=f"`{len(bot.guilds)}`",
        inline=True
    )

    embed.add_field(
        name="Users",
        value=f"`{sum(g.member_count or 0 for g in bot.guilds):,}`",
        inline=True
    )

    embed.add_field(
        name="Uptime",
        value=f"`{days}d {hours}h {minutes}m {seconds}s`",
        inline=True
    )

    embed.add_field(
        name="Commands",
        value=f"`{len(bot.commands)}`",
        inline=True
    )

    embed.set_thumbnail(
        url=bot.user.display_avatar.url
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# DATABASE STATUS
# ------------------------------------------------------------

@bot.command(
    name="dbstatus",
    description="Check the bot database status."
)
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def dbstatus(ctx):

    try:

        cursor = await bot.db.execute(
            "PRAGMA quick_check"
        )

        result = await cursor.fetchone()

        if result and result[0] == "ok":
            status = "🟢 Healthy"
        else:
            status = "🔴 Check required"

        cursor = await bot.db.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'table'
            """
        )

        table_count = (await cursor.fetchone())[0]

        embed = make_embed(
            "🗄️ Database Diagnostics",
            f"**Database:** `{DATABASE}`\n"
            f"**Integrity:** {status}\n"
            f"**Tables:** `{table_count}`"
        )

        await ctx.send(embed=embed)

    except Exception:

        logger.exception("Database diagnostics failed.")

        await ctx.send(
            "❌ Database diagnostics failed."
        )


# ------------------------------------------------------------
# SERVER CONFIGURATION OVERVIEW
# ------------------------------------------------------------

@bot.command(
    name="serverconfig",
    description="View Malarvaadi server configuration."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def serverconfig(ctx):

    config = await get_config(ctx.guild.id)

    embed = make_embed(
        "⚙️ Server Configuration",
        f"Configuration overview for **{ctx.guild.name}**."
    )

    if config:

        embed.add_field(
            name="Welcome Channel",
            value=f"<#{config[1]}>" if config[1] else "Not set",
            inline=True
        )

        embed.add_field(
            name="Goodbye Channel",
            value=f"<#{config[2]}>" if config[2] else "Not set",
            inline=True
        )

        embed.add_field(
            name="Log Channel",
            value=f"<#{config[3]}>" if config[3] else "Not set",
            inline=True
        )

        embed.add_field(
            name="Autorole",
            value=f"<@&{config[4]}>" if config[4] else "Not set",
            inline=True
        )

        embed.add_field(
            name="Moderation Logs",
            value=f"<#{config[5]}>" if config[5] else "Not set",
            inline=True
        )

    else:

        embed.description = (
            "No server configuration has been created yet."
        )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# DISABLE COMMAND
# ------------------------------------------------------------

@bot.command(
    name="disablecommand",
    description="Disable a command in this server."
)
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def disablecommand(ctx, *, command_name: str):

    await ensure_admin_schema()

    command = bot.get_command(command_name.lower())

    if command is None:
        return await ctx.send(
            "❌ Command not found."
        )

    if command.name in (
        "help",
        "disablecommand",
        "enablecommand"
    ):
        return await ctx.send(
            "❌ This command cannot be disabled."
        )

    await bot.db.execute(
        """
        INSERT OR REPLACE INTO disabled_commands
        (guild_id, command_name, disabled_by, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            ctx.guild.id,
            command.name,
            ctx.author.id,
            int(time.time())
        )
    )

    await bot.db.commit()

    await record_admin_action(
        ctx.guild.id,
        ctx.author.id,
        "disable_command",
        command.name
    )

    await ctx.send(
        f"🔒 Command `{command.name}` disabled for this server."
    )


# ------------------------------------------------------------
# ENABLE COMMAND
# ------------------------------------------------------------

@bot.command(
    name="enablecommand",
    description="Enable a previously disabled command."
)
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def enablecommand(ctx, *, command_name: str):

    await ensure_admin_schema()

    command = bot.get_command(command_name.lower())

    if command is None:
        return await ctx.send(
            "❌ Command not found."
        )

    cursor = await bot.db.execute(
        """
        DELETE FROM disabled_commands
        WHERE guild_id = ? AND command_name = ?
        """,
        (ctx.guild.id, command.name)
    )

    await bot.db.commit()

    if cursor.rowcount == 0:
        return await ctx.send(
            "❌ This command was not disabled."
        )

    await record_admin_action(
        ctx.guild.id,
        ctx.author.id,
        "enable_command",
        command.name
    )

    await ctx.send(
        f"🔓 Command `{command.name}` enabled."
    )


# ------------------------------------------------------------
# COMMAND DISABLED CHECK
# ------------------------------------------------------------

@bot.check
async def malarvaadi_command_control(ctx):

    if ctx.guild is None:
        return True

    if ctx.author.id == ctx.guild.owner_id:
        return True

    await ensure_admin_schema()

    cursor = await bot.db.execute(
        """
        SELECT command_name
        FROM disabled_commands
        WHERE guild_id = ?
        """,
        (ctx.guild.id,)
    )

    disabled = {
        row[0]
        for row in await cursor.fetchall()
    }

    if ctx.command and ctx.command.name in disabled:
        raise commands.CheckFailure(
            "This command has been disabled in this server."
        )

    return True


# ------------------------------------------------------------
# ADMIN AUDIT HISTORY
# ------------------------------------------------------------

@bot.command(
    name="adminhistory",
    description="View recent administrator actions."
)
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def adminhistory(ctx):

    await ensure_admin_schema()

    cursor = await bot.db.execute(
        """
        SELECT moderator_id, action, details, created_at
        FROM admin_audit
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (ctx.guild.id,)
    )

    records = await cursor.fetchall()

    if not records:
        return await ctx.send(
            "📭 No administrator actions recorded."
        )

    lines = []

    for moderator_id, action, details, created_at in records:

        lines.append(
            f"**{action}**\n"
            f"Moderator: <@{moderator_id}>\n"
            f"Details: `{details or 'None'}`\n"
            f"<t:{created_at}:R>"
        )

    embed = make_embed(
        "📋 Administrator Audit History",
        "\n\n".join(lines)
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# BOT OWNER MAINTENANCE
# ------------------------------------------------------------

@bot.command(
    name="maintenance",
    description="Enable or disable bot maintenance mode."
)
async def maintenance(ctx, action: str):

    if not is_bot_owner(ctx):
        return await ctx.send(
            "❌ Only the bot owner can use this command."
        )

    action = action.lower()

    if action not in ("on", "off"):
        return await ctx.send(
            "❌ Use `on` or `off`."
        )

    bot.maintenance_mode = action == "on"

    await ctx.send(
        f"🛠️ Maintenance mode: **{action.upper()}**"
    )


# ------------------------------------------------------------
# MAINTENANCE COMMAND CHECK
# ------------------------------------------------------------

@bot.check
async def malarvaadi_maintenance_check(ctx):

    if not getattr(bot, "maintenance_mode", False):
        return True

    if is_bot_owner(ctx):
        return True

    if ctx.command and ctx.command.name in (
        "help",
        "botinfo"
    ):
        return True

    raise commands.CheckFailure(
        "Malarvaadi is currently undergoing maintenance."
    )


# ============================================================
# END OF ADVANCED ADMIN ENGINE
# ============================================================

# ============================================================
#       MALARVAADI EVENT MANAGEMENT ENGINE
# ============================================================

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

async def ensure_event_schema():

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS server_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            creator_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            starts_at INTEGER NOT NULL,
            ends_at INTEGER NOT NULL,
            status TEXT DEFAULT 'scheduled',
            announcement_message_id INTEGER
        )
    """)

    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS event_participants (
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at INTEGER NOT NULL,
            PRIMARY KEY(event_id, user_id)
        )
    """)

    await bot.db.commit()


# ------------------------------------------------------------
# EVENT EMBED
# ------------------------------------------------------------

async def build_event_embed(event_id):

    cursor = await bot.db.execute(
        """
        SELECT guild_id, title, description, starts_at,
               ends_at, status
        FROM server_events
        WHERE event_id = ?
        """,
        (event_id,)
    )

    event = await cursor.fetchone()

    if not event:
        return None

    guild_id, title, description, starts_at, ends_at, status = event

    cursor = await bot.db.execute(
        """
        SELECT COUNT(*)
        FROM event_participants
        WHERE event_id = ?
        """,
        (event_id,)
    )

    participants = (await cursor.fetchone())[0]

    status_labels = {
        "scheduled": "🟡 Scheduled",
        "live": "🟢 Live",
        "completed": "🏁 Completed",
        "cancelled": "🔴 Cancelled"
    }

    embed = make_embed(
        f"🎉 {title}",
        description or "No description provided."
    )

    embed.add_field(
        name="Event ID",
        value=f"`{event_id}`",
        inline=True
    )

    embed.add_field(
        name="Status",
        value=status_labels.get(status, status),
        inline=True
    )

    embed.add_field(
        name="Participants",
        value=f"`{participants}`",
        inline=True
    )

    embed.add_field(
        name="Starts",
        value=f"<t:{starts_at}:F>\n<t:{starts_at}:R>",
        inline=True
    )

    embed.add_field(
        name="Ends",
        value=f"<t:{ends_at}:F>",
        inline=True
    )

    embed.set_footer(
        text="Malarvaadi Event Management"
    )

    return embed


# ------------------------------------------------------------
# CREATE EVENT
# ------------------------------------------------------------

@bot.hybrid_command(
    name="eventcreate",
    description="Schedule a new server event."
)
@commands.guild_only()
@commands.has_permissions(manage_events=True)
async def eventcreate(
    ctx,
    start_in: str,
    duration: str,
    title: str,
    *,
    description: str
):

    await ensure_event_schema()

    start_seconds = parse_duration(start_in)
    event_seconds = parse_duration(duration)

    if start_seconds is None or event_seconds is None:
        return await ctx.send(
            "❌ Invalid duration. Examples: `30m`, `2h`, `1d`."
        )

    if start_seconds > 2592000:
        return await ctx.send(
            "❌ Events can be scheduled up to 30 days ahead."
        )

    if event_seconds > 604800:
        return await ctx.send(
            "❌ Maximum event duration is 7 days."
        )

    if not 1 <= len(title) <= 150:
        return await ctx.send(
            "❌ Event title must contain 1–150 characters."
        )

    if not 1 <= len(description) <= 1500:
        return await ctx.send(
            "❌ Description must contain 1–1500 characters."
        )

    starts_at = int(time.time()) + start_seconds
    ends_at = starts_at + event_seconds

    cursor = await bot.db.execute(
        """
        INSERT INTO server_events
        (guild_id, channel_id, creator_id, title,
         description, starts_at, ends_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled')
        """,
        (
            ctx.guild.id,
            ctx.channel.id,
            ctx.author.id,
            title,
            description,
            starts_at,
            ends_at
        )
    )

    event_id = cursor.lastrowid

    await bot.db.commit()

    embed = await build_event_embed(event_id)

    message = await ctx.send(embed=embed)

    await bot.db.execute(
        """
        UPDATE server_events
        SET announcement_message_id = ?
        WHERE event_id = ?
        """,
        (message.id, event_id)
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ Event created successfully!\n"
        f"**Event ID:** `{event_id}`"
    )


# ------------------------------------------------------------
# JOIN EVENT
# ------------------------------------------------------------

@bot.hybrid_command(
    name="eventjoin",
    description="Register for a server event."
)
@commands.guild_only()
async def eventjoin(ctx, event_id: int):

    await ensure_event_schema()

    cursor = await bot.db.execute(
        """
        SELECT status, starts_at, guild_id
        FROM server_events
        WHERE event_id = ?
        """,
        (event_id,)
    )

    event = await cursor.fetchone()

    if not event or event[2] != ctx.guild.id:
        return await ctx.send("❌ Event not found.")

    status, starts_at, guild_id = event

    if status != "scheduled" or starts_at <= int(time.time()):
        return await ctx.send(
            "❌ Registration is closed for this event."
        )

    await bot.db.execute(
        """
        INSERT OR IGNORE INTO event_participants
        (event_id, user_id, joined_at)
        VALUES (?, ?, ?)
        """,
        (event_id, ctx.author.id, int(time.time()))
    )

    await bot.db.commit()

    await ctx.send(
        f"✅ You're registered for event `{event_id}`!"
    )


# ------------------------------------------------------------
# LEAVE EVENT
# ------------------------------------------------------------

@bot.hybrid_command(
    name="eventleave",
    description="Cancel your event registration."
)
@commands.guild_only()
async def eventleave(ctx, event_id: int):

    await ensure_event_schema()

    cursor = await bot.db.execute(
        """
        SELECT guild_id, status
        FROM server_events
        WHERE event_id = ?
        """,
        (event_id,)
    )

    event = await cursor.fetchone()

    if not event or event[0] != ctx.guild.id:
        return await ctx.send("❌ Event not found.")

    if event[1] != "scheduled":
        return await ctx.send(
            "❌ Registration is already closed."
        )

    cursor = await bot.db.execute(
        """
        DELETE FROM event_participants
        WHERE event_id = ? AND user_id = ?
        """,
        (event_id, ctx.author.id)
    )

    await bot.db.commit()

    if cursor.rowcount == 0:
        return await ctx.send(
            "❌ You are not registered for this event."
        )

    await ctx.send("✅ Your registration has been cancelled.")


# ------------------------------------------------------------
# EVENT PARTICIPANTS
# ------------------------------------------------------------

@bot.hybrid_command(
    name="eventparticipants",
    description="View registered event participants."
)
@commands.guild_only()
async def eventparticipants(ctx, event_id: int):

    await ensure_event_schema()

    cursor = await bot.db.execute(
        """
        SELECT guild_id, title
        FROM server_events
        WHERE event_id = ?
        """,
        (event_id,)
    )

    event = await cursor.fetchone()

    if not event or event[0] != ctx.guild.id:
        return await ctx.send("❌ Event not found.")

    cursor = await bot.db.execute(
        """
        SELECT user_id
        FROM event_participants
        WHERE event_id = ?
        ORDER BY joined_at ASC
        LIMIT 50
        """,
        (event_id,)
    )

    participants = await cursor.fetchall()

    if not participants:
        return await ctx.send(
            "📭 No one has registered yet."
        )

    lines = [
        f"{index}. <@{row[0]}>"
        for index, row in enumerate(participants, 1)
    ]

    embed = make_embed(
        f"👥 Participants — {event[1]}",
        "\n".join(lines)
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# EVENT INFORMATION
# ------------------------------------------------------------

@bot.hybrid_command(
    name="eventinfo",
    description="View detailed event information."
)
@commands.guild_only()
async def eventinfo(ctx, event_id: int):

    await ensure_event_schema()

    cursor = await bot.db.execute(
        """
        SELECT guild_id
        FROM server_events
        WHERE event_id = ?
        """,
        (event_id,)
    )

    record = await cursor.fetchone()

    if not record or record[0] != ctx.guild.id:
        return await ctx.send("❌ Event not found.")

    embed = await build_event_embed(event_id)

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# CANCEL EVENT
# ------------------------------------------------------------

@bot.hybrid_command(
    name="eventcancel",
    description="Cancel a scheduled server event."
)
@commands.guild_only()
@commands.has_permissions(manage_events=True)
async def eventcancel(ctx, event_id: int):

    await ensure_event_schema()

    cursor = await bot.db.execute(
        """
        SELECT guild_id, status, channel_id,
               announcement_message_id
        FROM server_events
        WHERE event_id = ?
        """,
        (event_id,)
    )

    event = await cursor.fetchone()

    if not event or event[0] != ctx.guild.id:
        return await ctx.send("❌ Event not found.")

    if event[1] not in ("scheduled", "live"):
        return await ctx.send(
            "❌ This event cannot be cancelled."
        )

    await bot.db.execute(
        """
        UPDATE server_events
        SET status = 'cancelled'
        WHERE event_id = ?
        """,
        (event_id,)
    )

    await bot.db.commit()

    embed = await build_event_embed(event_id)

    channel = ctx.guild.get_channel(event[2])

    if channel and event[3]:

        try:
            message = await channel.fetch_message(event[3])
            await message.edit(embed=embed)
        except discord.HTTPException:
            pass

    await ctx.send(
        f"🔴 Event `{event_id}` cancelled."
    )


# ------------------------------------------------------------
# EVENT LIST
# ------------------------------------------------------------

@bot.hybrid_command(
    name="eventlist",
    description="View upcoming and active server events."
)
@commands.guild_only()
async def eventlist(ctx):

    await ensure_event_schema()

    cursor = await bot.db.execute(
        """
        SELECT event_id, title, starts_at, status
        FROM server_events
        WHERE guild_id = ?
        AND status IN ('scheduled', 'live')
        ORDER BY starts_at ASC
        LIMIT 15
        """,
        (ctx.guild.id,)
    )

    records = await cursor.fetchall()

    if not records:
        return await ctx.send(
            "📭 No upcoming events."
        )

    lines = []

    for event_id, title, starts_at, status in records:

        lines.append(
            f"**#{event_id} — {title}**\n"
            f"Status: `{status}`\n"
            f"Starts: <t:{starts_at}:R>"
        )

    embed = make_embed(
        "📅 Server Events",
        "\n\n".join(lines)
    )

    await ctx.send(embed=embed)


# ------------------------------------------------------------
# EVENT SCHEDULER
# ------------------------------------------------------------

async def process_server_events():

    await ensure_event_schema()

    now = int(time.time())

    cursor = await bot.db.execute(
        """
        SELECT event_id, guild_id, channel_id,
               announcement_message_id, status
        FROM server_events
        WHERE
            (status = 'scheduled' AND starts_at <= ?)
            OR
            (status = 'live' AND ends_at <= ?)
        LIMIT 50
        """,
        (now, now)
    )

    records = await cursor.fetchall()

    for record in records:

        event_id, guild_id, channel_id, message_id, status = record

        if status == "scheduled":
            new_status = "live"
        else:
            new_status = "completed"

        await bot.db.execute(
            """
            UPDATE server_events
            SET status = ?
            WHERE event_id = ? AND status = ?
            """,
            (new_status, event_id, status)
        )

        await bot.db.commit()

        guild = bot.get_guild(guild_id)

        if guild is None:
            continue

        channel = guild.get_channel(channel_id)

        if channel is None:
            continue

        embed = await build_event_embed(event_id)

        if message_id:

            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
            except discord.HTTPException:
                pass

        if new_status == "live":
            await channel.send(
                f"🎉 **Event #{event_id} is now live!**"
            )

        elif new_status == "completed":
            await channel.send(
                f"🏁 **Event #{event_id} has ended.**"
            )


@tasks.loop(seconds=30)
async def malarvaadi_event_scheduler():

    await process_server_events()


@malarvaadi_event_scheduler.before_loop
async def before_event_scheduler():

    await bot.wait_until_ready()


@bot.listen("on_ready")
async def start_event_scheduler():

    if not malarvaadi_event_scheduler.is_running():
        malarvaadi_event_scheduler.start()


# ============================================================
# END OF EVENT MANAGEMENT ENGINE
# ============================================================


# ============================================================
# MALARVAADI GENERAL LOGGING ENGINE
# ============================================================

async def get_general_log_channel(guild):
    await bot.db.execute(
        "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
        (guild.id,)
    )
    await bot.db.commit()

    cursor = await bot.db.execute(
        "SELECT log_channel FROM guild_config WHERE guild_id = ?",
        (guild.id,)
    )
    row = await cursor.fetchone()

    if not row or not row[0]:
        return None

    channel = guild.get_channel(row[0])
    if channel is None:
        try:
            channel = await guild.fetch_channel(row[0])
        except discord.HTTPException:
            return None

    return channel if isinstance(channel, discord.TextChannel) else None


async def send_general_log(guild, embed, category="server"):
    cursor = await bot.db.execute(
        "SELECT channel_id, enabled FROM logging_config "
        "WHERE guild_id = ? AND category = ?",
        (guild.id, category)
    )
    config = await cursor.fetchone()

    if config and not config[1]:
        return

    channel = None

    if config and config[0]:
        channel = guild.get_channel(config[0])
        if channel is None:
            try:
                channel = await guild.fetch_channel(config[0])
            except discord.HTTPException:
                channel = None

    if channel is None:
        channel = await get_general_log_channel(guild)

    if not isinstance(channel, discord.TextChannel):
        return

    try:
        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none()
        )
    except discord.HTTPException:
        logger.warning(
            "Could not send a %s log in guild %s",
            category, guild.id
        )


@bot.hybrid_command(
    name="setlogs",
    description="Set the server's general audit-log channel."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setlogs(ctx, channel: discord.TextChannel):
    await bot.db.execute(
        "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
        (ctx.guild.id,)
    )
    await bot.db.execute(
        "UPDATE guild_config SET log_channel = ? WHERE guild_id = ?",
        (channel.id, ctx.guild.id)
    )
    await bot.db.commit()

    await ctx.send(f"✅ General server logs will be sent to {channel.mention}.")


@bot.hybrid_command(
    name="logs",
    description="Check or disable the general audit-log system."
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def logs(ctx, action: str = "status"):
    action = action.lower().strip()

    if action == "off":
        await bot.db.execute(
            "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
            (ctx.guild.id,)
        )
        await bot.db.execute(
            "UPDATE guild_config SET log_channel = NULL WHERE guild_id = ?",
            (ctx.guild.id,)
        )
        await bot.db.commit()
        return await ctx.send("✅ General server logging has been disabled.")

    if action != "status":
        return await ctx.send("Use `+logs` or `+logs off`.")

    channel = await get_general_log_channel(ctx.guild)
    if channel is None:
        return await ctx.send("ℹ️ No general log channel is configured. Use `+setlogs #channel`.")

    await ctx.send(f"📋 General logs are active in {channel.mention}.")



# ============================================================
# MALARVAADI ADVANCED LOGGING DASHBOARD
# ============================================================

LOGGING_CATEGORIES = {
    "members": "Member Logs",
    "messages": "Message Logs",
    "voice": "Voice Logs",
    "profile": "Profile Logs",
    "server": "Server Logs",
}


async def get_logging_config(guild_id, category):
    cursor = await bot.db.execute(
        "SELECT channel_id, enabled FROM logging_config "
        "WHERE guild_id = ? AND category = ?",
        (guild_id, category)
    )
    return await cursor.fetchone()


class LoggingCategorySelect(discord.ui.Select):
    def __init__(self, dashboard):
        self.dashboard = dashboard
        options = [
            discord.SelectOption(
                label=label,
                value=key,
                emoji="📋"
            )
            for key, label in LOGGING_CATEGORIES.items()
        ]
        super().__init__(
            placeholder="Choose a logging category...",
            options=options,
            custom_id="malarvaadi_logging_category"
        )

    async def callback(self, interaction):
        self.dashboard.category = self.values[0]
        await interaction.response.edit_message(
            embed=await self.dashboard.build_embed(),
            view=self.dashboard
        )


class LoggingChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, dashboard):
        self.dashboard = dashboard
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Choose a log channel...",
            min_values=1,
            max_values=1,
            custom_id="malarvaadi_logging_channel"
        )

    async def callback(self, interaction):
        channel = self.values[0]

        await bot.db.execute(
            """
            INSERT INTO logging_config
                (guild_id, category, channel_id, enabled)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(guild_id, category)
            DO UPDATE SET channel_id = excluded.channel_id
            """,
            (
                interaction.guild.id,
                self.dashboard.category,
                channel.id
            )
        )
        await bot.db.commit()

        await interaction.response.edit_message(
            content=f"✅ {LOGGING_CATEGORIES[self.dashboard.category]} "
                    f"channel saved: {channel.mention}",
            embed=await self.dashboard.build_embed(),
            view=self.dashboard
        )


class MalarvaadiLoggingDashboard(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.category = "members"
        self.add_item(LoggingCategorySelect(self))
        self.add_item(LoggingChannelSelect(self))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This logging dashboard belongs to another administrator.",
                ephemeral=True
            )
            return False

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need Manage Server permission to use this dashboard.",
                ephemeral=True
            )
            return False

        return True

    async def build_embed(self):
        config = await get_logging_config(
            self.guild_id,
            self.category
        )

        channel_id = config[0] if config else None
        enabled = bool(config[1]) if config else True

        channel_text = (
            f"<#{channel_id}>" if channel_id else "Not configured"
        )

        embed = discord.Embed(
            title="📋 Malarvaadi Logging Dashboard",
            description=(
                "Configure your server's audit-log destinations.\n\n"
                f"**Selected category:** "
                f"{LOGGING_CATEGORIES[self.category]}\n"
                f"**Channel:** {channel_text}\n"
                f"**Status:** {'🟢 Enabled' if enabled else '🔴 Disabled'}"
            ),
            color=COLOR
        )
        embed.add_field(
            name="Available categories",
            value="Members • Messages • Voice • Profile • Server",
            inline=False
        )
        embed.set_footer(
            text="Malarvaadi • Logging Control Center"
        )
        return embed

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(
        label="Enable",
        emoji="🟢",
        style=discord.ButtonStyle.success,
        custom_id="malarvaadi_logging_enable"
    )
    async def enable_logging(self, interaction, button):
        await bot.db.execute(
            """
            INSERT INTO logging_config
                (guild_id, category, enabled)
            VALUES (?, ?, 1)
            ON CONFLICT(guild_id, category)
            DO UPDATE SET enabled = 1
            """,
            (interaction.guild.id, self.category)
        )
        await bot.db.commit()

        await interaction.response.edit_message(
            content="✅ Category logging enabled.",
            embed=await self.build_embed(),
            view=self
        )

    @discord.ui.button(
        label="Disable",
        emoji="🔴",
        style=discord.ButtonStyle.danger,
        custom_id="malarvaadi_logging_disable"
    )
    async def disable_logging(self, interaction, button):
        await bot.db.execute(
            """
            INSERT INTO logging_config
                (guild_id, category, enabled)
            VALUES (?, ?, 0)
            ON CONFLICT(guild_id, category)
            DO UPDATE SET enabled = 0
            """,
            (interaction.guild.id, self.category)
        )
        await bot.db.commit()

        await interaction.response.edit_message(
            content="🔴 Category logging disabled.",
            embed=await self.build_embed(),
            view=self
        )

    @discord.ui.button(
        label="Test Log",
        emoji="🧪",
        style=discord.ButtonStyle.primary,
        custom_id="malarvaadi_logging_test"
    )
    async def test_logging(self, interaction, button):
        config = await get_logging_config(
            interaction.guild.id,
            self.category
        )

        if config and not config[1]:
            return await interaction.response.send_message(
                "This category is disabled. Enable it before testing.",
                ephemeral=True
            )

        channel_id = config[0] if config else None
        channel = (
            interaction.guild.get_channel(channel_id)
            if channel_id else None
        )

        if channel is None:
            channel = await get_general_log_channel(interaction.guild)

        if channel is None:
            return await interaction.response.send_message(
                "No channel is configured for this category.",
                ephemeral=True
            )

        test_embed = discord.Embed(
            title="🧪 Logging Test",
            description=(
                f"Your **{LOGGING_CATEGORIES[self.category]}** "
                "destination is working."
            ),
            color=SUCCESS,
            timestamp=datetime.now(timezone.utc)
        )
        test_embed.set_footer(text="Malarvaadi Logging System")

        try:
            await channel.send(
                embed=test_embed,
                allowed_mentions=discord.AllowedMentions.none()
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                "I couldn't send the test log. Check my channel permissions.",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"✅ Test log sent to {channel.mention}.",
            ephemeral=True
        )


@bot.command(name="logging")
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def logging_dashboard(ctx):
    dashboard = MalarvaadiLoggingDashboard(ctx.author.id)
    dashboard.guild_id = ctx.guild.id

    await ctx.send(
        embed=await dashboard.build_embed(),
        view=dashboard
    )

# ============================================================
# END MALARVAADI ADVANCED LOGGING DASHBOARD
# ============================================================

# PROFILE PICTURE CHANGES: OLD + NEW AVATAR
@bot.listen("on_user_update")
async def malarvaadi_avatar_logging(before, after):
    if before.avatar == after.avatar:
        return

    for guild in bot.guilds:
        member = guild.get_member(after.id)
        if member is None:
            continue

        embed = discord.Embed(
            title="🖼️ Member Profile Picture Changed",
            description=f"**Member:** {member.mention}\n**User ID:** `{after.id}`",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Before", value="Previous profile picture", inline=True)
        embed.add_field(name="After", value="New profile picture", inline=True)
        embed.set_thumbnail(url=before.display_avatar.replace(size=256).url)
        embed.set_image(url=after.display_avatar.replace(size=1024).url)
        embed.set_footer(text="Malarvaadi • Profile Audit")

        await send_general_log(guild, embed, category='profile')


# MEMBER NICKNAME AND ROLE CHANGES
@bot.listen("on_member_update")
async def malarvaadi_member_update_logging(before, after):
    if before.nick != after.nick:
        embed = discord.Embed(
            title="✏️ Member Nickname Changed",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Member", value=after.mention, inline=False)
        embed.add_field(name="Before", value=before.nick or before.name, inline=True)
        embed.add_field(name="After", value=after.nick or after.name, inline=True)
        await send_general_log(after.guild, embed, category='members')

    before_roles = {role.id: role for role in before.roles if role != before.guild.default_role}
    after_roles = {role.id: role for role in after.roles if role != after.guild.default_role}

    added = [role.mention for role_id, role in after_roles.items() if role_id not in before_roles]
    removed = [role.mention for role_id, role in before_roles.items() if role_id not in after_roles]

    if added or removed:
        embed = discord.Embed(
            title="🎭 Member Roles Updated",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Member", value=after.mention, inline=False)
        if added:
            embed.add_field(name="Roles Added", value="\n".join(added)[:1024], inline=False)
        if removed:
            embed.add_field(name="Roles Removed", value="\n".join(removed)[:1024], inline=False)
        await send_general_log(after.guild, embed, category='members')


# MESSAGE EDIT LOGGING
@bot.listen("on_message_edit")
async def malarvaadi_message_edit_logging(before, after):
    if after.guild is None or before.author.bot or before.content == after.content:
        return

    embed = discord.Embed(
        title="📝 Message Edited",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Author", value=before.author.mention, inline=True)
    embed.add_field(name="Channel", value=before.channel.mention, inline=True)
    embed.add_field(name="Before", value=(before.content or "[No text]")[:1024], inline=False)
    embed.add_field(name="After", value=(after.content or "[No text]")[:1024], inline=False)
    embed.add_field(name="Jump to Message", value=f"[Open message]({after.jump_url})", inline=False)

    await send_general_log(after.guild, embed, category='messages')


# MESSAGE DELETE LOGGING
@bot.listen("on_message_delete")
async def malarvaadi_message_delete_logging(message):
    if message.guild is None or message.author.bot:
        return

    embed = discord.Embed(
        title="🗑️ Message Deleted",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Author", value=message.author.mention, inline=True)
    embed.add_field(name="Channel", value=message.channel.mention, inline=True)
    embed.add_field(name="Content", value=(message.content or "[No text content]")[:1024], inline=False)

    await send_general_log(message.guild, embed, category='messages')


# ============================================================
# END OF MALARVAADI GENERAL LOGGING ENGINE
# ============================================================



# ============================================================
# MALARVAADI VOICE ACTIVITY LOGGER
# ============================================================

@bot.listen("on_voice_state_update")
async def malarvaadi_voice_activity_logger(member, before, after):
    if member.bot or member.guild is None:
        return

    changes = []

    if before.channel != after.channel:
        if before.channel is None and after.channel is not None:
            changes.append(
                f"🔊 **Joined voice channel:** {after.channel.mention}"
            )
        elif before.channel is not None and after.channel is None:
            changes.append(
                f"📴 **Left voice channel:** {before.channel.mention}"
            )
        elif before.channel is not None and after.channel is not None:
            changes.append(
                f"🔀 **Moved voice channel:** {before.channel.mention} "
                f"→ {after.channel.mention}"
            )

    checks = [
        ("self_mute", "Microphone", "Muted", "Unmuted"),
        ("mute", "Server mute", "Muted", "Unmuted"),
        ("self_deaf", "Self deafened", "Deafened", "Undeafened"),
        ("deaf", "Server deafened", "Deafened", "Undeafened"),
        ("self_video", "Camera", "Enabled", "Disabled"),
        ("self_stream", "Screen sharing", "Started", "Stopped"),
    ]

    for attribute, label, enabled_text, disabled_text in checks:
        old_value = getattr(before, attribute, False)
        new_value = getattr(after, attribute, False)

        if old_value != new_value:
            status = enabled_text if new_value else disabled_text
            changes.append(f"🎛️ **{label}:** {status}")

    if not changes:
        return

    embed = discord.Embed(
        title="🎙️ Voice Activity",
        description="\n".join(changes),
        color=COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(
        name="Member",
        value=f"{member.mention}\n`{member.id}`",
        inline=True
    )
    embed.add_field(
        name="Server",
        value=member.guild.name,
        inline=True
    )
    embed.set_footer(text="Malarvaadi • Voice Audit")

    await send_general_log(
        member.guild,
        embed,
        category="voice"
    )

# ============================================================
# END MALARVAADI VOICE ACTIVITY LOGGER
# ============================================================



# ============================================================
# MALARVAADI SERVER SETUP DASHBOARD
# ============================================================

class MalarvaadiSetupMessageModal(discord.ui.Modal):
    def __init__(self, guild_id, column, title):
        super().__init__(title=title)
        self.guild_id = guild_id
        self.column = column
        self.message = discord.ui.TextInput(
            label="Message",
            placeholder="Use {user}, {username}, {server}, {membercount}",
            style=discord.TextStyle.paragraph,
            max_length=1800,
            required=True
        )
        self.add_item(self.message)

    async def on_submit(self, interaction):
        await ensure_onboarding_schema()
        await bot.db.execute(
            "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
            (self.guild_id,)
        )
        await bot.db.execute(
            f"UPDATE guild_config SET {self.column} = ? WHERE guild_id = ?",
            (str(self.message.value), self.guild_id)
        )
        await bot.db.commit()
        await interaction.response.send_message(
            "✅ Message saved successfully.", ephemeral=True
        )


class MalarvaadiSetupDashboard(discord.ui.View):
    def __init__(self, author_id, guild_id):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.guild_id = guild_id

        self.add_item(discord.ui.ChannelSelect(
            placeholder="Select Welcome Channel",
            channel_types=[discord.ChannelType.text],
            custom_id="malarvaadi_setup_welcome"
        ))
        self.add_item(discord.ui.ChannelSelect(
            placeholder="Select Goodbye Channel",
            channel_types=[discord.ChannelType.text],
            custom_id="malarvaadi_setup_goodbye"
        ))
        self.add_item(discord.ui.RoleSelect(
            placeholder="Select Automatic Member Role",
            custom_id="malarvaadi_setup_autorole"
        ))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This dashboard belongs to another user.",
                ephemeral=True
            )
            return False
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need Manage Server permission.",
                ephemeral=True
            )
            return False
        return True

    async def save(self, interaction, column, value, message):
        await ensure_onboarding_schema()
        await bot.db.execute(
            "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
            (self.guild_id,)
        )
        await bot.db.execute(
            f"UPDATE guild_config SET {column} = ? WHERE guild_id = ?",
            (value, self.guild_id)
        )
        await bot.db.commit()
        await interaction.response.send_message(
            f"✅ {message}", ephemeral=True
        )

    @discord.ui.button(label="Welcome Message", emoji="👋",
                       style=discord.ButtonStyle.primary, row=3)
    async def welcome_message(self, interaction, button):
        await interaction.response.send_modal(
            MalarvaadiSetupMessageModal(
                self.guild_id, "welcome_message", "Configure Welcome Message"
            )
        )

    @discord.ui.button(label="Goodbye Message", emoji="👋",
                       style=discord.ButtonStyle.primary, row=3)
    async def goodbye_message(self, interaction, button):
        await interaction.response.send_modal(
            MalarvaadiSetupMessageModal(
                self.guild_id, "goodbye_message", "Configure Goodbye Message"
            )
        )

    @discord.ui.button(label="Toggle Onboarding", emoji="🛡️",
                       style=discord.ButtonStyle.success, row=4)
    async def toggle_onboarding(self, interaction, button):
        await ensure_onboarding_schema()
        await bot.db.execute(
            "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
            (self.guild_id,)
        )
        cur = await bot.db.execute(
            "SELECT onboarding_enabled FROM guild_config WHERE guild_id = ?",
            (self.guild_id,)
        )
        row = await cur.fetchone()
        new_value = 0 if row and row[0] else 1
        await bot.db.execute(
            "UPDATE guild_config SET onboarding_enabled = ? WHERE guild_id = ?",
            (new_value, self.guild_id)
        )
        await bot.db.commit()
        await interaction.response.send_message(
            "✅ Onboarding " + ("enabled." if new_value else "disabled."),
            ephemeral=True
        )

    @discord.ui.button(label="Refresh", emoji="🔄",
                       style=discord.ButtonStyle.secondary, row=4)
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(
            embed=await build_malarvaadi_setup_embed(self.guild_id),
            view=self
        )


async def build_malarvaadi_setup_embed(guild_id):
    await ensure_onboarding_schema()
    await bot.db.execute(
        "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
        (guild_id,)
    )
    cur = await bot.db.execute(
        """SELECT welcome_channel, goodbye_channel, autorole,
                  welcome_message, goodbye_message, onboarding_enabled
           FROM guild_config WHERE guild_id = ?""",
        (guild_id,)
    )
    row = await cur.fetchone()
    welcome, goodbye, role, welcome_msg, goodbye_msg, onboarding = row

    embed = discord.Embed(
        title="⚙️ Malarvaadi Server Setup",
        description="Configure your server using the selectors and buttons below.",
        color=COLOR
    )
    embed.add_field(
        name="👋 Welcome Channel",
        value=f"<#{welcome}>" if welcome else "Not configured",
        inline=True
    )
    embed.add_field(
        name="👋 Goodbye Channel",
        value=f"<#{goodbye}>" if goodbye else "Not configured",
        inline=True
    )
    embed.add_field(
        name="🎭 Automatic Role",
        value=f"<@&{role}>" if role else "Not configured",
        inline=True
    )
    embed.add_field(
        name="📝 Welcome Message",
        value="Custom message saved" if welcome_msg else "Default message",
        inline=True
    )
    embed.add_field(
        name="📝 Goodbye Message",
        value="Custom message saved" if goodbye_msg else "Default message",
        inline=True
    )
    embed.add_field(
        name="🛡️ Onboarding",
        value="Enabled" if onboarding else "Disabled",
        inline=True
    )
    embed.set_footer(text="Malarvaadi • Server Configuration")
    return embed


@bot.command(name="setupdashboard")
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def setupdashboard(ctx):
    view = MalarvaadiSetupDashboard(ctx.author.id, ctx.guild.id)
    await ctx.send(
        embed=await build_malarvaadi_setup_embed(ctx.guild.id),
        view=view
    )

# ================= END SERVER SETUP DASHBOARD =================


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("Malarvaadi shutdown requested.")
