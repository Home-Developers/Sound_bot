import os
import shutil
import glob
from dotenv import load_dotenv

# Завантажуємо змінні оточення з .env
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()


def find_ffmpeg() -> str:
    """Знаходить шлях до виконуваного файлу ffmpeg на системі"""
    # 1. Явний шлях з .env
    env_path = os.getenv("FFMPEG_PATH", "").strip().strip('"')
    if env_path and os.path.isfile(env_path):
        return env_path
    if env_path and os.path.isdir(env_path):
        exe = os.path.join(env_path, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if os.path.isfile(exe):
            return exe

    # 2. Перевірка в PATH
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg

    # 3. Пошук у папці проекту або ./bin
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "ffmpeg.exe"),
        os.path.join(base_dir, "bin", "ffmpeg.exe"),
        os.path.join(base_dir, "ffmpeg", "bin", "ffmpeg.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    # 4. Пошук у пакетах WinGet / стандартних каталогах Windows
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA", "")
        if local_app_data:
            winget_pattern = os.path.join(
                local_app_data, "Microsoft", "WinGet", "Packages",
                "*FFmpeg*", "*", "bin", "ffmpeg.exe"
            )
            matches = glob.glob(winget_pattern)
            if matches and os.path.isfile(matches[0]):
                return matches[0]

        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]
        for cp in common_paths:
            if os.path.isfile(cp):
                return cp

    return "ffmpeg"


FFMPEG_EXECUTABLE = find_ffmpeg()


def is_ffmpeg_available() -> bool:
    """Перевіряє, чи дійсно доступний FFmpeg для запуску"""
    if os.path.isfile(FFMPEG_EXECUTABLE):
        return True
    return shutil.which(FFMPEG_EXECUTABLE) is not None


# Налаштування yt-dlp для стабільного стрімінгу та якісного аудіо
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
            "skip": ["translated_subs", "dash", "hls"],
        }
    },
}

# Опції FFmpeg для стабільної трансляції аудіопотоків без переривань
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# Час очікування бездіяльності в секундах перед виходом з голосового каналу (3 хвилини)
IDLE_DISCONNECT_SECONDS = 180
