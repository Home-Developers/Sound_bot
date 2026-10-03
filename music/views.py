import discord
from discord.ui import View, Button, button
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from music.player import GuildMusicPlayer

class MusicControlView(View):
    def __init__(self, player: "GuildMusicPlayer"):
        super().__init__(timeout=None)
        self.player = player
        self._update_buttons()

    def _update_buttons(self):
        # Оновлення лейблів/кольорів кнопок відповідно до стану
        for child in self.children:
            if isinstance(child, Button):
                if child.custom_id == "play_pause":
                    if self.player.voice_client and self.player.voice_client.is_paused():
                        child.emoji = "▶️"
                        child.label = "Продовжити"
                        child.style = discord.ButtonStyle.green
                    else:
                        child.emoji = "⏸️"
                        child.label = "Пауза"
                        child.style = discord.ButtonStyle.secondary
                elif child.custom_id == "loop_mode":
                    mode = self.player.loop_mode
                    if mode == "track":
                        child.emoji = "🔂"
                        child.label = "Трек"
                        child.style = discord.ButtonStyle.primary
                    elif mode == "queue":
                        child.emoji = "🔁"
                        child.label = "Черга"
                        child.style = discord.ButtonStyle.primary
                    else:
                        child.emoji = "➡️"
                        child.label = "Повтор: Вимк"
                        child.style = discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Перевірка: чи користувач перебуває у тому ж голосовому каналі, що й бот
        bot_vc = self.player.voice_client
        if not bot_vc or not bot_vc.channel:
            await interaction.response.send_message("❌ Бот наразі не підключений до голосового каналу.", ephemeral=True)
            return False

        if not interaction.user.voice or interaction.user.voice.channel != bot_vc.channel:
            await interaction.response.send_message(
                f"❌ Щоб керувати плеєром, зайдіть у голосовий канал **{bot_vc.channel.name}**!",
                ephemeral=True
            )
            return False

        return True

    @button(label="Пауза", style=discord.ButtonStyle.secondary, emoji="⏸️", custom_id="play_pause")
    async def play_pause_button(self, interaction: discord.Interaction, btn: Button):
        vc = self.player.voice_client
        if not vc:
            return

        if vc.is_playing():
            vc.pause()
            self._update_buttons()
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("⏸️ Відтворення призупинено.", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            self._update_buttons()
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("▶️ Відтворення продовжено.", ephemeral=True)
        else:
            await interaction.response.send_message("Нічого не грає.", ephemeral=True)

    @button(label="Пропустити", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="skip")
    async def skip_button(self, interaction: discord.Interaction, btn: Button):
        vc = self.player.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await interaction.response.send_message("Немає активного треку для пропуску.", ephemeral=True)
            return

        current_title = self.player.current_track.full_title if self.player.current_track else "трек"
        await interaction.response.send_message(f"⏭️ {interaction.user.mention} пропустив(ла) **{current_title}**.")
        vc.stop()

    @button(label="Повтор", style=discord.ButtonStyle.secondary, emoji="➡️", custom_id="loop_mode")
    async def loop_button(self, interaction: discord.Interaction, btn: Button):
        # Циклічне перемикання режиму повтору: off -> track -> queue -> off
        modes = ["off", "track", "queue"]
        curr_idx = modes.index(self.player.loop_mode)
        new_mode = modes[(curr_idx + 1) % len(modes)]
        self.player.loop_mode = new_mode
        self._update_buttons()
        await interaction.response.edit_message(view=self)

        mode_names = {
            "off": "❌ Вимкнено",
            "track": "🔂 Повтор поточного треку",
            "queue": "🔁 Повтор усієї черги"
        }
        await interaction.followup.send(f"Режим повтору змінено на: **{mode_names[new_mode]}**", ephemeral=True)

    @button(label="Черга", style=discord.ButtonStyle.secondary, emoji="📜", custom_id="show_queue")
    async def queue_button(self, interaction: discord.Interaction, btn: Button):
        embed = self.player.get_queue_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @button(label="Зупинити", style=discord.ButtonStyle.danger, emoji="⏹️", custom_id="stop")
    async def stop_button(self, interaction: discord.Interaction, btn: Button):
        await interaction.response.send_message(f"⏹️ {interaction.user.mention} зупинив(ла) відтворення.")
        await self.player.stop()
