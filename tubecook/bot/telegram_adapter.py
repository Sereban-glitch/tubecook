"""Telegram-адаптер на aiogram 3.x (опциональная зависимость).

Ставится отдельно: pip install 'aiogram>=3.13'
Запускается только при наличии TUBECOOK_TOKEN; иначе сервис работает
в консольном режиме и вся логика остаётся той же (ядро transport-agnostic).

Внимание: длинная polling-сессия зависит от сети и аккумулятора ноутбука;
автоматических вебхуков нет (ТЗ: их не обещано).
"""
from __future__ import annotations


class TelegramTransport:
    def __init__(self, core, token: str):
        self.core = core
        self.token = token

    async def run(self) -> None:
        try:
            from aiogram import Bot, Dispatcher, F
            from aiogram.filters import Command
            from aiogram.types import FSInputFile, Message
        except ImportError as e:
            raise RuntimeError(
                "aiogram не установлен: pip install 'aiogram>=3.13' "
                f"({e})") from e

        bot = Bot(token=self.token)
        dp = Dispatcher()
        core = self.core

        @dp.message(F.text)
        async def on_message(message: Message):
            sender = message.from_user.id if message.from_user else 0
            replies = core.handle_update({"sender_id": sender,
                                          "text": message.text or "",
                                          "chat_id": message.chat.id})
            for r in replies:
                if r.get("file"):
                    await bot.send_video(message.chat.id,
                                         FSInputFile(r["file"]),
                                         caption=r["text"][:900])
                else:
                    await bot.send_message(message.chat.id, r["text"][:4000])

        async def pump_notifications():
            import asyncio
            while True:
                while core.notifications:
                    n = core.notifications.pop(0)
                    for admin in core.cfg.admin_ids:
                        if n.get("file"):
                            from aiogram.types import FSInputFile
                            await bot.send_video(admin, FSInputFile(n["file"]),
                                                 caption=n["text"][:900])
                        else:
                            await bot.send_message(admin, n["text"][:4000])
                await asyncio.sleep(2)

        import asyncio
        await asyncio.gather(dp.start_polling(bot), pump_notifications())
