import asyncio
import logging
import sys
import discord
from discord.ext import commands

# Встановлюємо UTF-8 для виводу в термінал Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("music_bot")

# Інтенції Discord
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

class SoundBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(config.COMMAND_PREFIX),
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        """Завантаження розширень (cogs) та синхронізація слеш-команд"""
        logger.info("Завантаження музичного модуля...")
        await self.load_extension("cogs.music_cog")

        try:
            synced = await self.tree.sync()
            logger.info(f"Успішно синхронізовано {len(synced)} слеш-команд (/) з Discord")
        except Exception as e:
            logger.error(f"Помилка синхронізації слеш-команд: {e}")

    async def on_ready(self):
        logger.info(f"==================================================")
        logger.info(f"Бот успішно увійшов як: {self.user} (ID: {self.user.id})")
        logger.info(f"Підключено до серверів: {len(self.guilds)}")
        logger.info(f"Префікс команд: '{config.COMMAND_PREFIX}' та слеш-команди '/'")
        logger.info(f"Підтримка: Spotify, SoundCloud, Deezer")
        logger.info(f"==================================================")

        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f"/play | Spotify, SoundCloud, Deezer"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Глобальний обробник помилок текстових команд"""
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Пропущено обов'язковий аргумент: `{error.param.name}`. Приклад: `{config.COMMAND_PREFIX}play <посилання>`")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("❌ У вас недостатньо прав для виконання цієї команди.")
        else:
            logger.error(f"Неопрацьована помилка команди {ctx.command}: {error}")
            try:
                await ctx.send(f"⚠️ Виникла помилка: `{error}`")
            except Exception:
                pass


def main():
    token = config.DISCORD_TOKEN.strip()
    if not token or token == "your_discord_bot_token_here":
        print("\n" + "=" * 70)
        print(" УВАГА: Не вказано токен Discord бота!")
        print(" 1. Відкрийте або створіть файл .env у папці бота.")
        print(" 2. Вкажіть ваш DISCORD_TOKEN=ваш_токен")
        print(" 3. Отримати токен можна тут: https://discord.com/developers/applications")
        print("=" * 70 + "\n")
        sys.exit(1)

    bot = SoundBot()
    try:
        bot.run(token)
    except discord.errors.LoginFailure:
        logger.critical("❌ Невірний токен Discord бота. Перевірте файл .env!")
    except Exception as e:
        logger.critical(f"❌ Критична помилка під час запуску: {e}")

if __name__ == "__main__":
    main()
