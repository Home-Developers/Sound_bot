import asyncio
import logging
import random
import time
from typing import List, Optional
import discord
from discord.ext import commands

from config import FFMPEG_OPTIONS, IDLE_DISCONNECT_SECONDS
from music.resolver import TrackInfo, MusicResolver
from music.views import MusicControlView

logger = logging.getLogger("music_bot.player")

class GuildMusicPlayer:
    def __init__(self, bot: commands.Bot, guild: discord.Guild, resolver: MusicResolver):
        self.bot = bot
        self.guild = guild
        self.resolver = resolver

        self.voice_client: Optional[discord.VoiceClient] = None
        self.text_channel: Optional[discord.TextChannel] = None
        
        self.queue: List[TrackInfo] = []
        self.current_track: Optional[TrackInfo] = None
        self.current_message: Optional[discord.Message] = None
        self.start_playback_time: float = 0.0

        self.loop_mode: str = "off"  # "off", "track", "queue"
        self.volume: float = 1.0  # 1.0 = 100%
        self._idle_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def get_color_for_source(self, source_type: str) -> int:
        colors = {
            "spotify": 0x1DB954,    # Spotify зелений
            "soundcloud": 0xFF5500, # SoundCloud помаранчевий
            "deezer": 0xA238FF,     # Deezer фіолетовий
            "youtube": 0xFF0000,    # YouTube червоний
        }
        return colors.get(source_type, 0x5865F2)

    def cancel_idle_timer(self):
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
            self._idle_task = None

    def start_idle_timer(self):
        self.cancel_idle_timer()
        self._idle_task = self.bot.loop.create_task(self._idle_disconnect())

    async def _idle_disconnect(self):
        try:
            await asyncio.sleep(IDLE_DISCONNECT_SECONDS)
            if self.voice_client and self.voice_client.is_connected() and not self.voice_client.is_playing():
                if self.text_channel:
                    await self.text_channel.send(
                        "💤 Бот покинув голосовий канал через відсутність активності.",
                        delete_after=15
                    )
                await self.stop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Помилка в idle_disconnect: {e}")

    async def add_tracks(self, tracks: List[TrackInfo], text_channel: discord.TextChannel):
        """Додає один або кілька треків у чергу та запускає програвання, якщо бот вільний"""
        self.text_channel = text_channel
        self.cancel_idle_timer()
        self.queue.extend(tracks)

        if not self.voice_client or not self.voice_client.is_playing() and not self.voice_client.is_paused():
            await self.play_next()

    async def play_next(self):
        async with self._lock:
            if not self.voice_client or not self.voice_client.is_connected():
                return

            # Обробка повтору поточного треку
            if self.loop_mode == "track" and self.current_track:
                track_to_play = self.current_track
            elif self.queue:
                # Якщо режим повтору черги, попередній трек відправляємо в кінець
                if self.loop_mode == "queue" and self.current_track:
                    self.queue.append(self.current_track)
                track_to_play = self.queue.pop(0)
            else:
                self.current_track = None
                self.start_idle_timer()
                if self.text_channel:
                    await self.text_channel.send("🏁 Черга завершилась. Додайте ще треків за допомогою `/play`!")
                return

            self.current_track = track_to_play
            self.cancel_idle_timer()

            try:
                # Отримуємо прямий аудіопотік
                stream_url = await self.resolver.get_stream_url(track_to_play)
                
                # Створюємо FFmpeg аудіоджерело
                audio_source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
                volume_source = discord.PCMVolumeTransformer(audio_source, volume=self.volume)

                def after_callback(error):
                    if error:
                        logger.error(f"Помилка після відтворення: {error}")
                    coro = self.play_next()
                    asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

                self.voice_client.play(volume_source, after=after_callback)
                self.start_playback_time = time.time()

                # Надсилаємо Now Playing Embed з кнопками керування
                await self.send_now_playing()

            except Exception as e:
                logger.error(f"Не вдалося відтворити трек {track_to_play.full_title}: {e}")
                if self.text_channel:
                    await self.text_channel.send(
                        f"⚠️ Не вдалося відтворити **{track_to_play.full_title}**: `{e}`. Переходжу до наступного..."
                    )
                # Пробуємо наступний трек
                self.bot.loop.create_task(self.play_next())

    async def send_now_playing(self):
        """Формує та надсилає гарний ембед поточного треку з інтерактивними кнопками"""
        if not self.text_channel or not self.current_track:
            return

        track = self.current_track
        color = self.get_color_for_source(track.source_type)

        embed = discord.Embed(
            title=track.full_title,
            url=track.source_url if track.source_url.startswith("http") else None,
            color=color
        )
        embed.set_author(name="Зараз грає 🎶", icon_url=self.bot.user.display_avatar.url)
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        embed.add_field(name="Платформа", value=track.badge, inline=True)
        embed.add_field(name="Тривалість", value=f"⏱️ `{track.formatted_duration}`", inline=True)
        embed.add_field(name="Замовив(ла)", value=track.requester_mention, inline=True)

        mode_badge = {"off": "Вимкнено", "track": "🔂 Трек", "queue": "🔁 Черга"}.get(self.loop_mode, "Вимкнено")
        embed.add_field(name="Повтор", value=f"`{mode_badge}`", inline=True)
        embed.add_field(name="Гучність", value=f"🔊 `{int(self.volume * 100)}%`", inline=True)
        embed.add_field(name="Треків у черзі", value=f"🔢 `{len(self.queue)}`", inline=True)

        view = MusicControlView(self)
        try:
            self.current_message = await self.text_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Помилка надсилання повідомлення Now Playing: {e}")

    def get_queue_embed(self) -> discord.Embed:
        """Створює гарне вікно зі списком черги"""
        embed = discord.Embed(title="📜 Черга відтворення", color=0x5865F2)

        if self.current_track:
            embed.description = f"**Зараз грає:** [{self.current_track.full_title}]({self.current_track.source_url}) ({self.current_track.badge}) — `{self.current_track.formatted_duration}`\n\n"
        else:
            embed.description = "Наразі нічого не відтворюється.\n\n"

        if not self.queue:
            embed.description += "*Черга порожня.*"
            return embed

        # Показуємо перші 10 треків
        lines = []
        for idx, t in enumerate(self.queue[:10], start=1):
            lines.append(f"`{idx}.` **[{t.full_title}]({t.source_url})** `{t.formatted_duration}` — {t.badge}")

        if len(self.queue) > 10:
            lines.append(f"\n*...та ще {len(self.queue) - 10} треків у черзі.*")

        embed.add_field(name="Наступні треки:", value="\n".join(lines), inline=False)
        embed.set_footer(text=f"Всього треків: {len(self.queue)} | Режим повтору: {self.loop_mode}")
        return embed

    def shuffle(self):
        """Перемішує чергу"""
        random.shuffle(self.queue)

    def clear(self):
        """Очищує чергу"""
        self.queue.clear()

    def set_volume(self, volume: float):
        """Встановлює гучність (0.0 - 2.0)"""
        self.volume = max(0.0, min(volume, 2.0))
        if self.voice_client and self.voice_client.source and isinstance(self.voice_client.source, discord.PCMVolumeTransformer):
            self.voice_client.source.volume = self.volume

    async def skip(self):
        """Пропускає поточний трек"""
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()

    async def stop(self):
        """Повністю зупиняє відтворення, очищує чергу та відключається"""
        self.clear()
        self.current_track = None
        self.cancel_idle_timer()

        if self.voice_client:
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
            if self.voice_client.is_connected():
                await self.voice_client.disconnect()
            self.voice_client = None
