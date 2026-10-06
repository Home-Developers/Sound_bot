import discord
from discord.ext import commands
from typing import Dict, Optional, Literal
import logging

from music.resolver import MusicResolver, TrackInfo
from music.player import GuildMusicPlayer

logger = logging.getLogger("music_bot.cog")

class MusicCog(commands.Cog, name="Музика"):
    """Основний музичний модуль з підтримкою Spotify, SoundCloud, Deezer"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.resolver = MusicResolver()
        self.players: Dict[int, GuildMusicPlayer] = {}

    def get_player(self, guild: discord.Guild) -> GuildMusicPlayer:
        """Отримує або створює плеєр для сервера"""
        if guild.id not in self.players:
            self.players[guild.id] = GuildMusicPlayer(self.bot, guild, self.resolver)
        return self.players[guild.id]

    async def ensure_voice(self, ctx: commands.Context) -> Optional[discord.VoiceClient]:
        """Перевіряє голосовий канал та підключає бота"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ Спочатку зайдіть у будь-який голосовий канал!")
            return None

        user_channel = ctx.author.voice.channel
        player = self.get_player(ctx.guild)

        if not ctx.voice_client:
            try:
                vc = await user_channel.connect(self_deaf=False)
                player.voice_client = vc
                return vc
            except Exception as e:
                logger.error(f"Помилка підключення до голосового каналу: {e}")
                await ctx.send(f"❌ Не вдалося підключитися до голосового каналу: `{e}`")
                return None
        else:
            vc = ctx.voice_client
            player.voice_client = vc
            if vc.channel != user_channel:
                # Якщо у поточному каналі бот один, переходимо до користувача
                members_count = len([m for m in vc.channel.members if not m.bot])
                if members_count == 0:
                    await vc.move_to(user_channel)
                else:
                    await ctx.send(f"⚠️ Бот вже грає у каналі **{vc.channel.name}**!")
                    return None
            return vc

    async def require_player_voice(self, ctx: commands.Context) -> Optional[GuildMusicPlayer]:
        """Повертає плеєр, якщо автор команди в каналі з ботом."""
        if not ctx.guild:
            await ctx.send("❌ Ця команда доступна лише на сервері Discord.")
            return None

        player = self.players.get(ctx.guild.id)
        voice_client = player.voice_client if player else None
        if not voice_client or not voice_client.is_connected():
            await ctx.send("❌ Бот не підключений до голосового каналу.")
            return None

        user_voice = getattr(ctx.author, "voice", None)
        if not user_voice or user_voice.channel != voice_client.channel:
            await ctx.send(f"❌ Зайдіть у голосовий канал **{voice_client.channel.name}**, щоб керувати плеєром.")
            return None

        return player

    @commands.hybrid_command(
        name="play",
        aliases=["p"],
        description="Грати музику за посиланням (Spotify, SoundCloud, Deezer) або за пошуковим запитом"
    )
    async def play(self, ctx: commands.Context, *, query: str):
        """
        Відтворює трек або додає плейлист у чергу.
        Підтримує посилання:
        • Spotify: треки, альбоми, плейлисти
        • SoundCloud: окремі треки, плейлисти
        • Deezer: треки, альбоми, плейлисти
        • Прямий пошук за назвою або виконавцем
        """
        vc = await self.ensure_voice(ctx)
        if not vc:
            return

        # Відкладаємо відповідь на взаємодію, оскільки пошук та резолвінг можуть зайняти кілька секунд
        await ctx.defer()

        player = self.get_player(ctx.guild)
        player.voice_client = vc

        try:
            tracks, info_name = await self.resolver.resolve(query, ctx.author)
            if not tracks:
                await ctx.send("❌ Не вдалося знайти або обробити аудіо за вашим запитом.")
                return

            if len(tracks) == 1:
                track = tracks[0]
                # Якщо зараз нічого не грає, трек запуститься одразу через player.add_tracks
                is_currently_playing = vc.is_playing() or vc.is_paused()
                await player.add_tracks(tracks, ctx.channel)

                if is_currently_playing:
                    embed = discord.Embed(
                        title="Додано в чергу 🎵",
                        description=f"**[{track.full_title}]({track.source_url})**",
                        color=player.get_color_for_source(track.source_type)
                    )
                    if track.thumbnail:
                        embed.set_thumbnail(url=track.thumbnail)
                    embed.add_field(name="Джерело", value=track.badge, inline=True)
                    embed.add_field(name="Тривалість", value=f"`{track.formatted_duration}`", inline=True)
                    embed.add_field(name="Позиція в черзі", value=f"#{len(player.queue)}", inline=True)
                    embed.set_footer(text=f"Замовив(ла): {ctx.author.display_name}")
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f"🔍 Завантажую та розпочинаю відтворення: **{track.full_title}** ({track.badge})...")

            else:
                # Додавання цілого альбому або плейлиста
                await player.add_tracks(tracks, ctx.channel)
                first_track = tracks[0]
                embed = discord.Embed(
                    title="Додано колекцію до черги 📚",
                    description=f"**{info_name}**\nУспішно додано **{len(tracks)}** треків!",
                    color=player.get_color_for_source(first_track.source_type)
                )
                if first_track.thumbnail:
                    embed.set_thumbnail(url=first_track.thumbnail)
                embed.add_field(name="Джерело", value=first_track.badge, inline=True)
                embed.add_field(name="Замовив(ла)", value=ctx.author.mention, inline=True)
                embed.set_footer(text=f"Всього треків у черзі: {len(player.queue)}")
                await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Помилка при виконанні команди play: {e}")
            await ctx.send(f"❌ Помилка під час пошуку або завантаження треку: `{e}`")

    @commands.hybrid_command(name="pause", description="Призупинити поточне відтворення")
    async def pause(self, ctx: commands.Context):
        player = await self.require_player_voice(ctx)
        if not player:
            return
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.pause()
            await ctx.send("⏸️ Відтворення призупинено.")
        else:
            await ctx.send("❌ Музика наразі не грає або вже на паузі.")

    @commands.hybrid_command(name="resume", description="Продовжити відтворення музики")
    async def resume(self, ctx: commands.Context):
        player = await self.require_player_voice(ctx)
        if not player:
            return
        if player.voice_client and player.voice_client.is_paused():
            player.voice_client.resume()
            await ctx.send("▶️ Відтворення продовжено.")
        else:
            await ctx.send("❌ Музика не на паузі.")

    @commands.hybrid_command(name="skip", aliases=["s", "next"], description="Пропустити поточний трек")
    async def skip(self, ctx: commands.Context):
        player = await self.require_player_voice(ctx)
        if not player:
            return
        if not player.voice_client or not (player.voice_client.is_playing() or player.voice_client.is_paused()):
            await ctx.send("❌ Немає активного треку для пропуску.")
            return

        current_title = player.current_track.full_title if player.current_track else "трек"
        await ctx.send(f"⏭️ Пропущено: **{current_title}**")
        await player.skip()

    @commands.hybrid_command(name="stop", aliases=["disconnect", "leave"], description="Зупинити музику та вийти з голосового каналу")
    async def stop(self, ctx: commands.Context):
        player = await self.require_player_voice(ctx)
        if not player:
            return

        await player.stop()
        await ctx.send("⏹️ Відтворення зупинено, чергу очищено. До зустрічі!")

    @commands.hybrid_command(name="queue", aliases=["q"], description="Показати список треків у черзі")
    async def queue(self, ctx: commands.Context):
        player = self.get_player(ctx.guild)
        embed = player.get_queue_embed()
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Показати інформацію про поточний трек")
    async def now_playing(self, ctx: commands.Context):
        player = self.get_player(ctx.guild)
        if not player.current_track or not player.voice_client or not (player.voice_client.is_playing() or player.voice_client.is_paused()):
            await ctx.send("❌ Зараз нічого не грає.")
            return

        await player.send_now_playing()
        await ctx.send("✅ Інформацію про поточний трек оновлено нижче.", ephemeral=True)

    @commands.hybrid_command(name="loop", description="Перемкнути режим повтору (off / track / queue)")
    async def loop(self, ctx: commands.Context, mode: Optional[Literal["off", "track", "queue"]] = None):
        player = await self.require_player_voice(ctx)
        if not player:
            return

        if mode is None:
            # Циклічне перемикання
            modes = ["off", "track", "queue"]
            curr_idx = modes.index(player.loop_mode)
            mode = modes[(curr_idx + 1) % len(modes)]

        player.loop_mode = mode
        mode_names = {
            "off": "❌ Вимкнено",
            "track": "🔂 Повтор поточного треку",
            "queue": "🔁 Повтор усієї черги"
        }
        await ctx.send(f"Режим повтору змінено на: **{mode_names[mode]}**")

    @commands.hybrid_command(name="shuffle", description="Перемішати треки у черзі у випадковому порядку")
    async def shuffle(self, ctx: commands.Context):
        player = await self.require_player_voice(ctx)
        if not player:
            return
        if len(player.queue) < 2:
            await ctx.send("❌ Для перемішування у черзі має бути щонайменше 2 треки.")
            return

        player.shuffle()
        await ctx.send(f"🔀 Успішно перемішано **{len(player.queue)}** треків у черзі!")

    @commands.hybrid_command(name="clear", description="Очистити всі треки з черги")
    async def clear(self, ctx: commands.Context):
        player = await self.require_player_voice(ctx)
        if not player:
            return
        count = len(player.queue)
        player.clear()
        await ctx.send(f"🗑️ Очищено **{count}** треків з черги.")

    @commands.hybrid_command(name="volume", aliases=["vol"], description="Встановити гучність бота (від 1 до 200%)")
    async def volume(self, ctx: commands.Context, percent: int):
        if not (1 <= percent <= 200):
            await ctx.send("❌ Будь ласка, вкажіть гучність у діапазоні від 1 до 200%.")
            return

        player = await self.require_player_voice(ctx)
        if not player:
            return
        player.set_volume(percent / 100.0)
        await ctx.send(f"🔊 Гучність встановлено на **{percent}%**.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Автоматичний вихід, якщо всі користувачі покинули голосовий канал з ботом"""
        # Якщо дію здійснив бот — ігноруємо
        if member.id == self.bot.user.id:
            # Якщо бота примусово відключили
            if before.channel and not after.channel:
                if before.channel.guild.id in self.players:
                    player = self.players[before.channel.guild.id]
                    player.clear()
                    player.current_track = None
                    player.cancel_idle_timer()
            return

        # Перевіряємо голосовий канал, який покинув користувач
        if before.channel:
            bot_member = before.channel.guild.me
            if bot_member in before.channel.members:
                # Рахуємо людей (не ботів)
                non_bots = [m for m in before.channel.members if not m.bot]
                if len(non_bots) == 0:
                    # Всі вийшли, запускаємо таймер простою
                    player = self.get_player(before.channel.guild)
                    player.start_idle_timer()


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
