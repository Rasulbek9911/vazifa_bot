from aiogram import types
from aiogram.dispatcher.filters import BoundFilter


class IsPrivate(BoundFilter):
    """
    Filter - faqat private chat (DM) uchun
    Guruhlardagi messagelarni e'tibor berishin
    """
    async def check(self, message: types.Message) -> bool:
        return message.chat.type == types.ChatType.PRIVATE
