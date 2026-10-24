"""Domain models: albums and the photos inside them."""

from datetime import datetime

from pydantic import BaseModel


class Photo(BaseModel):
    """One image in an album, as known from Drive."""

    file_id: str
    name: str
    mime_type: str
    md5_checksum: str | None = None
    modified_time: datetime


class Album(BaseModel):
    """One Drive subfolder of the portfolio root."""

    folder_id: str
    name: str
    title: str
    slug: str
    photos: list[Photo]
    cover: Photo | None = None
