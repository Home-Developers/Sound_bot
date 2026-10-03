import re
import json
import logging
import asyncio
from typing import List, Optional, Tuple
from dataclasses import dataclass
import aiohttp
import yt_dlp

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except ImportError:
    spotipy = None

from config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    YTDL_OPTIONS,
)

logger = logging.getLogger("music_bot.resolver")

@dataclass
class TrackInfo:
    title: str
    artist: str
    source_url: str
    source_type: str  # "spotify", "soundcloud", "deezer", "youtube", "direct"
    duration: int  # в секундах
    thumbnail: str
    search_query: str
    requester_name: str
    requester_id: int
    requester_mention: str
    stream_url: Optional[str] = None

    @property
    def full_title(self) -> str:
        if self.artist and self.artist.lower() not in self.title.lower():
            return f"{self.artist} - {self.title}"
        return self.title

    @property
    def formatted_duration(self) -> str:
        if not self.duration or self.duration <= 0:
            return "Стрім / Невідомо"
        minutes = self.duration // 60
        seconds = self.duration % 60
        hours = minutes // 60
        if hours > 0:
            minutes = minutes % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def badge(self) -> str:
        badges = {
            "spotify": "🟢 Spotify",
            "soundcloud": "🟠 SoundCloud",
            "deezer": "🟣 Deezer",
            "youtube": "🔴 YouTube",
            "direct": "🎵 Пряме посилання",
        }
        return badges.get(self.source_type, "🎶 Музика")


class MusicResolver:
    def __init__(self):
        # Ініціалізація клієнта Spotify, якщо задано ключі
        self.sp = None
        if spotipy and SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=SPOTIFY_CLIENT_ID,
                    client_secret=SPOTIFY_CLIENT_SECRET
                )
                self.sp = spotipy.Spotify(auth_manager=auth_manager)
                logger.info("Успішно підключено офіційний Spotify API")
            except Exception as e:
                logger.warning(f"Не вдалося ініціалізувати Spotify API: {e}")

        # Ініціалізація yt-dlp екстрактора
        ytdl_opts = dict(YTDL_OPTIONS)
        # Додаємо підтримку node js-runtime, якщо доступно
        ytdl_opts["js_runtimes"] = {"node": {}}
        self.ydl = yt_dlp.YoutubeDL(ytdl_opts)

    async def resolve(self, query: str, requester) -> Tuple[List[TrackInfo], str]:
        """
        Головний метод резолвінгу.
        Повертає кортеж: (список треків, назва альбому/плейлиста або статус)
        """
        query = query.strip().strip("<>\"'")

        # 1. Deezer
        if "deezer.com" in query or "deezer.page.link" in query:
            return await self._resolve_deezer(query, requester)

        # 2. Spotify
        if "spotify.com" in query or "spotify.link" in query:
            return await self._resolve_spotify(query, requester)

        # 3. SoundCloud
        if "soundcloud.com" in query or "on.soundcloud.com" in query:
            return await self._resolve_soundcloud(query, requester)

        # 4. Загальний пошук або інші URL (YouTube тощо)
        return await self._resolve_generic(query, requester)

    async def _resolve_deezer(self, query: str, requester) -> Tuple[List[TrackInfo], str]:
        """Парсинг посилань Deezer через безкоштовний відкритий REST API"""
        async with aiohttp.ClientSession() as session:
            # Обробка коротких посилань deezer.page.link
            if "deezer.page.link" in query:
                try:
                    async with session.get(query, allow_redirects=True) as resp:
                        query = str(resp.url)
                except Exception as e:
                    logger.error(f"Помилка редиректу Deezer: {e}")

            # Визначаємо тип та ID: track, album, playlist
            track_match = re.search(r"track/(\d+)", query)
            album_match = re.search(r"album/(\d+)", query)
            playlist_match = re.search(r"playlist/(\d+)", query)

            if track_match:
                track_id = track_match.group(1)
                api_url = f"https://api.deezer.com/track/{track_id}"
                async with session.get(api_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        title = data.get("title", "Невідомий трек")
                        artist = data.get("artist", {}).get("name", "Невідомий виконавець")
                        duration = data.get("duration", 0)
                        cover = data.get("album", {}).get("cover_xl") or data.get("album", {}).get("cover_medium") or ""
                        track = TrackInfo(
                            title=title,
                            artist=artist,
                            source_url=data.get("link", query),
                            source_type="deezer",
                            duration=duration,
                            thumbnail=cover,
                            search_query=f"{artist} - {title}",
                            requester_name=requester.display_name,
                            requester_id=requester.id,
                            requester_mention=requester.mention
                        )
                        return [track], title

            elif album_match:
                album_id = album_match.group(1)
                api_url = f"https://api.deezer.com/album/{album_id}"
                async with session.get(api_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        album_title = data.get("title", "Альбом Deezer")
                        cover = data.get("cover_xl") or data.get("cover_medium") or ""
                        tracks_data = data.get("tracks", {}).get("data", [])
                        tracks = []
                        for t in tracks_data:
                            t_title = t.get("title", "")
                            t_artist = t.get("artist", {}).get("name", data.get("artist", {}).get("name", ""))
                            tracks.append(TrackInfo(
                                title=t_title,
                                artist=t_artist,
                                source_url=t.get("link", query),
                                source_type="deezer",
                                duration=t.get("duration", 0),
                                thumbnail=cover,
                                search_query=f"{t_artist} - {t_title}",
                                requester_name=requester.display_name,
                                requester_id=requester.id,
                                requester_mention=requester.mention
                            ))
                        return tracks, f"Альбом Deezer: {album_title}"

            elif playlist_match:
                playlist_id = playlist_match.group(1)
                api_url = f"https://api.deezer.com/playlist/{playlist_id}"
                async with session.get(api_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        pl_title = data.get("title", "Плейлист Deezer")
                        cover = data.get("picture_xl") or data.get("picture_medium") or ""
                        tracks_data = data.get("tracks", {}).get("data", [])
                        tracks = []
                        for t in tracks_data:
                            t_title = t.get("title", "")
                            t_artist = t.get("artist", {}).get("name", "")
                            tracks.append(TrackInfo(
                                title=t_title,
                                artist=t_artist,
                                source_url=t.get("link", query),
                                source_type="deezer",
                                duration=t.get("duration", 0),
                                thumbnail=cover,
                                search_query=f"{t_artist} - {t_title}",
                                requester_name=requester.display_name,
                                requester_id=requester.id,
                                requester_mention=requester.mention
                            ))
                        return tracks, f"Плейлист Deezer: {pl_title}"

        # Якщо не вдалося через API, шукаємо як звичайний запит
        return await self._resolve_generic(query, requester)

    async def _resolve_spotify(self, query: str, requester) -> Tuple[List[TrackInfo], str]:
        """Парсинг Spotify (через Spotipy або публічний розумний парсер Embed)"""
        # Якщо підключено офіційний клієнт Spotify
        if self.sp:
            try:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, self._resolve_spotify_api, query, requester)
            except Exception as e:
                logger.warning(f"Spotify API помилка, спроба використати Embed парсер: {e}")

        # Fallback: парсинг через Spotify Embed та oEmbed
        return await self._resolve_spotify_embed(query, requester)

    def _resolve_spotify_api(self, query: str, requester) -> Tuple[List[TrackInfo], str]:
        """Синхронний виклик Spotipy API у фоновому потоці"""
        tracks = []
        if "track/" in query:
            match = re.search(r"track/([a-zA-Z0-9]+)", query)
            if not match:
                raise ValueError("Невірне посилання на трек Spotify")
            track_id = match.group(1)
            t = self.sp.track(track_id)
            title = t["name"]
            artist = ", ".join([a["name"] for a in t["artists"]])
            duration = int(t["duration_ms"] / 1000)
            images = t.get("album", {}).get("images", [])
            cover = images[0]["url"] if images else ""
            track = TrackInfo(
                title=title,
                artist=artist,
                source_url=t.get("external_urls", {}).get("spotify", query),
                source_type="spotify",
                duration=duration,
                thumbnail=cover,
                search_query=f"{artist} - {title}",
                requester_name=requester.display_name,
                requester_id=requester.id,
                requester_mention=requester.mention
            )
            return [track], title

        elif "album/" in query:
            match = re.search(r"album/([a-zA-Z0-9]+)", query)
            if not match:
                raise ValueError("Невірне посилання на альбом Spotify")
            album_id = match.group(1)
            album = self.sp.album(album_id)
            album_name = album["name"]
            cover = album["images"][0]["url"] if album.get("images") else ""
            for item in album["tracks"]["items"]:
                t_title = item["name"]
                t_artist = ", ".join([a["name"] for a in item["artists"]])
                tracks.append(TrackInfo(
                    title=t_title,
                    artist=t_artist,
                    source_url=item.get("external_urls", {}).get("spotify", query),
                    source_type="spotify",
                    duration=int(item["duration_ms"] / 1000),
                    thumbnail=cover,
                    search_query=f"{t_artist} - {t_title}",
                    requester_name=requester.display_name,
                    requester_id=requester.id,
                    requester_mention=requester.mention
                ))
            return tracks, f"Альбом Spotify: {album_name}"

        elif "playlist/" in query:
            match = re.search(r"playlist/([a-zA-Z0-9]+)", query)
            if not match:
                raise ValueError("Невірне посилання на плейлист Spotify")
            pl_id = match.group(1)
            playlist = self.sp.playlist(pl_id)
            pl_name = playlist["name"]
            cover = playlist["images"][0]["url"] if playlist.get("images") else ""
            results = playlist["tracks"]
            items = results["items"]
            while results["next"] and len(items) < 100:  # Ліміт на 100 треків за раз для стабільності
                results = self.sp.next(results)
                items.extend(results["items"])

            for item in items:
                t = item.get("track")
                if not t or not t.get("name"):
                    continue
                t_title = t["name"]
                t_artist = ", ".join([a["name"] for a in t.get("artists", [])])
                t_images = t.get("album", {}).get("images", [])
                t_cover = t_images[0]["url"] if t_images else cover
                tracks.append(TrackInfo(
                    title=t_title,
                    artist=t_artist,
                    source_url=t.get("external_urls", {}).get("spotify", query),
                    source_type="spotify",
                    duration=int(t.get("duration_ms", 0) / 1000),
                    thumbnail=t_cover,
                    search_query=f"{t_artist} - {t_title}",
                    requester_name=requester.display_name,
                    requester_id=requester.id,
                    requester_mention=requester.mention
                ))
            return tracks, f"Плейлист Spotify: {pl_name}"

        raise ValueError("Непідтримуваний тип Spotify")

    async def _resolve_spotify_embed(self, query: str, requester) -> Tuple[List[TrackInfo], str]:
        """Парсинг без API ключів: використовує embed сторінку Spotify (__NEXT_DATA__)"""
        async with aiohttp.ClientSession() as session:
            # Для треків можна використати oEmbed
            if "track/" in query:
                oembed_url = f"https://open.spotify.com/oembed?url={query}"
                try:
                    async with session.get(oembed_url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            title = data.get("title", "Трек Spotify")
                            thumbnail = data.get("thumbnail_url", "")
                            
                            # Спробуємо отримати артиста зі сторінки
                            artist = ""
                            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                            async with session.get(query, headers=headers) as page_resp:
                                if page_resp.status == 200:
                                    html = await page_resp.text()
                                    m_desc = re.search(r'<meta property="og:description" content="([^"]+)"', html)
                                    if m_desc:
                                        desc = m_desc.group(1)
                                        artist = desc.split("·")[0].strip() if "·" in desc else desc.split("-")[0].strip()

                            track = TrackInfo(
                                title=title,
                                artist=artist,
                                source_url=query,
                                source_type="spotify",
                                duration=0,
                                thumbnail=thumbnail,
                                search_query=f"{artist} - {title}".strip(" -"),
                                requester_name=requester.display_name,
                                requester_id=requester.id,
                                requester_mention=requester.mention
                            )
                            return [track], title
                except Exception as e:
                    logger.error(f"Помилка oEmbed Spotify: {e}")

            # Для альбомів або плейлистів парсимо embed сторінку
            embed_url = query.replace("open.spotify.com/", "open.spotify.com/embed/")
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            try:
                async with session.get(embed_url, headers=headers) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
                        if m:
                            data = json.loads(m.group(1))
                            entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
                            name = entity.get("name", "Колекція Spotify")
                            cover = entity.get("coverArt", {}).get("sources", [{}])[0].get("url", "")
                            track_list = entity.get("trackList", [])
                            tracks = []
                            for t in track_list:
                                t_title = t.get("title", "")
                                t_artist = t.get("subtitle", "")
                                t_duration = int(t.get("duration", 0) / 1000)
                                tracks.append(TrackInfo(
                                    title=t_title,
                                    artist=t_artist,
                                    source_url=query,
                                    source_type="spotify",
                                    duration=t_duration,
                                    thumbnail=cover,
                                    search_query=f"{t_artist} - {t_title}",
                                    requester_name=requester.display_name,
                                    requester_id=requester.id,
                                    requester_mention=requester.mention
                                ))
                            if tracks:
                                return tracks, f"Spotify: {name}"
            except Exception as e:
                logger.error(f"Помилка парсингу embed Spotify: {e}")

        # Якщо не вдалося, робимо generic пошук
        return await self._resolve_generic(query, requester)

    async def _resolve_soundcloud(self, query: str, requester) -> Tuple[List[TrackInfo], str]:
        """Парсинг посилань SoundCloud безпосередньо через yt-dlp"""
        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(
                None,
                lambda: self.ydl.extract_info(query, download=False, process=False)
            )
            if not info:
                return await self._resolve_generic(query, requester)

            # Якщо це плейлист або сет SoundCloud
            if "entries" in info:
                entries = list(info["entries"])
                tracks = []
                for entry in entries[:100]:
                    title = entry.get("title", "SoundCloud трек")
                    artist = entry.get("uploader", "")
                    duration = entry.get("duration", 0)
                    t_url = entry.get("url") or entry.get("webpage_url") or query
                    tracks.append(TrackInfo(
                        title=title,
                        artist=artist,
                        source_url=t_url,
                        source_type="soundcloud",
                        duration=duration,
                        thumbnail=entry.get("thumbnail", ""),
                        search_query=t_url,
                        requester_name=requester.display_name,
                        requester_id=requester.id,
                        requester_mention=requester.mention
                    ))
                playlist_title = info.get("title", "SoundCloud Плейлист")
                return tracks, f"SoundCloud: {playlist_title}"

            # Якщо це окремий трек
            full_info = await loop.run_in_executor(
                None,
                lambda: self.ydl.extract_info(query, download=False)
            )
            title = full_info.get("title", "SoundCloud трек")
            artist = full_info.get("uploader", "")
            duration = full_info.get("duration", 0)
            thumbnail = full_info.get("thumbnail", "")
            stream_url = full_info.get("url")

            track = TrackInfo(
                title=title,
                artist=artist,
                source_url=full_info.get("webpage_url", query),
                source_type="soundcloud",
                duration=duration,
                thumbnail=thumbnail,
                search_query=query,
                requester_name=requester.display_name,
                requester_id=requester.id,
                requester_mention=requester.mention,
                stream_url=stream_url
            )
            return [track], title
        except Exception as e:
            logger.warning(f"Прямий SoundCloud екстрактор дав збій ({e}), використовуємо пошук...")
            return await self._resolve_generic(query, requester)

    async def _resolve_generic(self, query: str, requester) -> Tuple[List[TrackInfo], str]:
        """Загальний пошук треку через YouTube / прямий лінк за допомогою yt-dlp"""
        loop = asyncio.get_running_loop()
        is_url = query.startswith("http://") or query.startswith("https://")
        is_search_prefix = any(query.startswith(p) for p in ("ytsearch", "scsearch"))
        search_target = query if (is_url or is_search_prefix) else f"ytsearch1:{query}"

        try:
            info = await loop.run_in_executor(
                None,
                lambda: self.ydl.extract_info(search_target, download=False)
            )
            if not info:
                raise ValueError("Не знайдено аудіо за вашим запитом")

            if "entries" in info:
                entries = [e for e in info["entries"] if e]
                if not entries:
                    raise ValueError("Не знайдено аудіо за вашим запитом")
                info = entries[0]

            title = info.get("title", "Аудіотрек")
            artist = info.get("uploader", info.get("channel", ""))
            duration = info.get("duration", 0)
            thumbnail = info.get("thumbnail", "")
            stream_url = info.get("url")
            source_type = "youtube" if "youtu" in info.get("webpage_url", "") else "direct"

            track = TrackInfo(
                title=title,
                artist=artist,
                source_url=info.get("webpage_url", query),
                source_type=source_type,
                duration=duration,
                thumbnail=thumbnail,
                search_query=query,
                requester_name=requester.display_name,
                requester_id=requester.id,
                requester_mention=requester.mention,
                stream_url=stream_url
            )
            return [track], title
        except Exception as e:
            logger.error(f"Помилка загального пошуку: {e}")
            raise e

    async def get_stream_url(self, track: TrackInfo) -> str:
        """
        Отримує робочий прямий стрім-URL для FFmpeg.
        Якщо URL вже збережено і це прямий потік, перевіряє його.
        В іншому разі виконує пошук та витягує свіжий стрім.
        """
        if track.stream_url and not track.stream_url.startswith("http://localhost"):
            return track.stream_url

        loop = asyncio.get_running_loop()
        query = track.search_query or f"{track.artist} - {track.title}".strip(" -")
        is_url = query.startswith("http://") or query.startswith("https://")
        search_target = query if is_url else f"ytsearch1:{query}"

        try:
            info = await loop.run_in_executor(
                None,
                lambda: self.ydl.extract_info(search_target, download=False)
            )
            if "entries" in info:
                entries = [e for e in info["entries"] if e]
                if not entries:
                    raise ValueError(f"Не вдалося отримати стрім для {track.full_title}")
                info = entries[0]

            stream_url = info.get("url")
            if not stream_url:
                raise ValueError("Не знайдено аудіопотік у результатах")
            track.stream_url = stream_url
            return stream_url
        except Exception as e:
            logger.error(f"Помилка отримання стріму: {e}")
            # Спробуємо fallback через SoundCloud search
            if not is_url:
                try:
                    sc_target = f"scsearch1:{query}"
                    sc_info = await loop.run_in_executor(
                        None,
                        lambda: self.ydl.extract_info(sc_target, download=False)
                    )
                    if "entries" in sc_info and sc_info["entries"]:
                        stream_url = sc_info["entries"][0].get("url")
                        if stream_url:
                            track.stream_url = stream_url
                            return stream_url
                except Exception as sc_err:
                    logger.error(f"SoundCloud fallback також зазнав невдачі: {sc_err}")
            raise e
