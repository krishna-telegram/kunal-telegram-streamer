from pyrogram import Client
from typing import Any, Optional
from pyrogram.types import Message
from pyrogram.file_id import FileId
from pyrogram.raw.types.messages import Messages
from kunal.server.exceptions import FIleNotFound


async def parse_file_id(message: "Message") -> Optional[FileId]:
    media = get_media_from_message(message)
    if media:
        return FileId.decode(media.file_id)

async def parse_file_unique_id(message: "Messages") -> Optional[str]:
    media = get_media_from_message(message)
    if media:
        return media.file_unique_id

async def get_file_ids(client: Client, chat_id: int, id: int) -> Optional[FileId]:
    message = await client.get_messages(chat_id, id)
    if message.empty:
        raise FIleNotFound
    media = get_media_from_message(message)
    file_unique_id = await parse_file_unique_id(message)
    file_id = await parse_file_id(message)
    setattr(file_id, "file_size", getattr(media, "file_size", 0))
    setattr(file_id, "mime_type", getattr(media, "mime_type", ""))
    setattr(file_id, "file_name", getattr(media, "file_name", ""))
    setattr(file_id, "unique_id", file_unique_id)
    return file_id

def get_media_from_message(message: "Message") -> Any:
    media_types = (
        "audio",
        "document",
        "photo",
        "sticker",
        "animation",
        "video",
        "voice",
        "video_note",
    )
    for attr in media_types:
        media = getattr(message, attr, None)
        if media:
            return media


def get_hash(media_msg: Message) -> str:
    media = get_media_from_message(media_msg)
    return getattr(media, "file_unique_id", "")[:6]

def get_name(media_msg: Message) -> str:
    media = get_media_from_message(media_msg)
    return getattr(media, 'file_name', "")

def get_media_file_size(m):
    media = get_media_from_message(m)
    return getattr(media, "file_size", 0)

class MockMedia:
    def __init__(self, file_name=None, file_size=0, mime_type=None, file_unique_id=None):
        self.file_name = file_name
        self.file_size = file_size
        self.mime_type = mime_type
        self.file_unique_id = file_unique_id

class MockMessage:
    def __init__(self, id, media_type, file_name, file_hash, file_size=0, mime_type=None):
        self.id = id
        self.empty = False
        media_obj = MockMedia(
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            file_unique_id=file_hash
        )
        setattr(self, media_type, media_obj)

def create_mock_message(id, media_type, file_name, file_hash, file_size=0, mime_type=None):
    return MockMessage(id, media_type, file_name, file_hash, file_size, mime_type)
