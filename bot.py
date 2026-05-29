import discord
from discord.ext import commands
import os
from discord import FFmpegPCMAudio

# ========================= НАЛАШТУВАННЯ =========================
token = "MTQ5ODM3NzE4MTYzMjY1OTUxNg.GJnUhF.1YgQNiG3Ewbd8FChBsjt_Y-otv1r67_RTLITus"  # ← ВСТАВ СВІЙ ТОКЕН
SOUNDS_FOLDER = "sounds"

# Інтенти
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)  # префікс змінили на "!", бо / тепер для slash-команд

available_sounds = {}

if os.path.exists(SOUNDS_FOLDER):
    for filename in os.listdir(SOUNDS_FOLDER):
        if filename.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a')):
            name = os.path.splitext(filename)[0].lower()
            available_sounds[name] = os.path.join(SOUNDS_FOLDER, filename)
else:
    print(f"⚠️ Папка '{SOUNDS_FOLDER}' не знайдена!")


@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущений!')
    print(f'🎵 Завантажено звуків: {len(available_sounds)}')

    # Синхронізація slash-команд
    try:
        synced = await bot.tree.sync()
        print(f'✅ Slash-команди синхронізовано! ({len(synced)} команд)')
    except Exception as e:
        print(f'❌ Помилка синхронізації: {e}')


# ======================== SLASH-КОМАНДИ ========================

@bot.hybrid_command(name="hello", description="Привіт від бота")
async def hello(ctx):
    await ctx.reply('hello!')


@bot.hybrid_command(name="join", description="Приєднати бота до голосового каналу")
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.reply("✅ Приєднався до голосового каналу!")
    else:
        await ctx.reply("❌ Ти повинен бути в голосовому каналі!")


@bot.hybrid_command(name="leave", description="Виключити бота з голосового каналу")
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.reply("✅ Вийшов з голосового каналу.")
    else:
        await ctx.reply("Я і так не в голосовому каналі.")


@bot.hybrid_command(name="sounds", description="Показати список всіх звуків")
async def sounds(ctx):
    if not available_sounds:
        await ctx.reply("❌ Немає звуків. Створи папку sounds!")
        return
    sound_list = ", ".join(sorted(available_sounds.keys()))
    await ctx.reply(f"🎵 Доступні звуки ({len(available_sounds)}): {sound_list}")


@bot.hybrid_command(name="play", description="Відтворити спеціальний звук")
async def play(ctx, sound_name: str):
    sound_name = sound_name.lower()
    if sound_name not in available_sounds:
        await ctx.reply(f"❌ Звук {sound_name} не знайдено! Використовуй /sounds")
        return

    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.reply("❌ Ти повинен бути в голосовому каналі!")
            return

    vc = ctx.voice_client
    if vc.is_playing():
        vc.stop()

    try:
        source = FFmpegPCMAudio(available_sounds[sound_name])
        vc.play(source)
        await ctx.reply(f"▶️ Відтворюю: {sound_name} 🎵")
    except Exception as e:
        await ctx.reply(f"❌ Помилка: {e}")


@bot.hybrid_command(name="stop", description="Зупинити поточний звук")
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.reply("⏹️ Відтворення зупинено.")
    else:
        await ctx.reply("Нічого не грає.")


# ======================== ЗАПУСК ========================
bot.run(token)