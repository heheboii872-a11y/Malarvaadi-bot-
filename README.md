# Discord Command Center Bot

A fresh Railway-ready Discord bot with an interactive `/help` command browser inspired by the supplied reference screenshots.

## Included categories

📋 All Commands, 🎂 Birthday, 👥 Community, ℹ️ Core, 💰 Economy, 🎮 Fun, 🎉 Giveaway, 🔨 Join To Create, 📊 Leveling, 🔎 Logging, 🛡️ Moderation, 🎵 Music, 🔎 Reactionroles, 🔎 Search, 🔎 Server Stats, 🎟️ Ticket, 🛠️ Tools, 🔧 Utility, ✅ Verification, 👋 Welcome.

## 1. Create the Discord application

1. Open the Discord Developer Portal.
2. Create a new application.
3. Add a Bot.
4. Copy the bot token.
5. Under **Privileged Gateway Intents**, enable:
   - Server Members Intent
   - Message Content Intent
   - Presence Intent (optional but useful for stats)
6. Invite the bot with the `bot` and `applications.commands` scopes.
7. Give it only the permissions your server actually needs.

## 2. Test locally

```bash
python -m venv .venv
# activate the environment
pip install -r requirements.txt
cp .env.example .env
# put your token in .env
python bot.py
```

## 3. GitHub

Create an empty repository, then from this folder:

```bash
git init
git add .
git commit -m "Initial all-in-one Discord bot"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

Never commit `.env` or your bot token.

## 4. Railway

1. Create a Railway project.
2. Choose **Deploy from GitHub repo**.
3. Select this repository.
4. Add the variable `DISCORD_TOKEN`.
5. Optionally add `GUILD_ID` with your test server ID.
6. Deploy.

The included `Procfile` starts the bot with:

```bash
python bot.py
```

`nixpacks.toml` requests FFmpeg for future music/audio support.

## Important

The bot is intentionally structured so more commands can be added as separate cogs without replacing the whole application.

The music commands currently provide the voice controls and a safe integration point; a production music provider/source can be plugged into `/play` next.

## Persistence

SQLite is used for economy, leveling, birthdays, warnings, and settings. On Railway, attach persistent storage if you want the SQLite database to survive service replacement/redeployment.
