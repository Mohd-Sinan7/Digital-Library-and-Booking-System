"""Request bodies and validation for the catalog admin endpoints (FR-C1, FR-C2, NFR-C2)."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

Text255 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Genre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


def normalize_isbn(value: str) -> str:
    """Strip hyphens and spaces and check the ISBN-10 or ISBN-13 check digit."""
    isbn = value.replace("-", "").replace(" ", "").upper()
    if len(isbn) == 10 and isbn[:9].isdigit() and (isbn[9].isdigit() or isbn[9] == "X"):
        digits = [10 if c == "X" else int(c) for c in isbn]
        if sum((10 - i) * d for i, d in enumerate(digits)) % 11 == 0:
            return isbn
    elif len(isbn) == 13 and isbn.isdigit():
        if sum((3 if i % 2 else 1) * int(c) for i, c in enumerate(isbn)) % 10 == 0:
            return isbn
    raise ValueError("ISBN must be a valid ISBN-10 or ISBN-13")


class _BookFields(BaseModel):
    @field_validator("isbn", check_fields=False)
    @classmethod
    def _isbn(cls, v):
        return None if v is None else normalize_isbn(v)

    @field_validator("year", check_fields=False)
    @classmethod
    def _year(cls, v):
        if v is not None and v > date.today().year:
            raise ValueError("year cannot be in the future")
        return v

    @field_validator("cover_url", check_fields=False)
    @classmethod
    def _url(cls, v):
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("cover_url must start with http:// or https://")
        return v


class BookCreate(_BookFields):
    title: Text255
    author: Text255
    isbn: str
    genre: Genre
    page_count: int = Field(ge=1)
    total_copies: int = Field(ge=0)
    description: str = Field("", max_length=2000)
    year: int | None = None
    cover_url: str | None = Field(None, max_length=500)


REQUIRED = {"title", "author", "isbn", "genre", "page_count", "total_copies", "description"}


class BookUpdate(_BookFields):
    """Any subset of the BookCreate fields. Omitted fields stay unchanged."""

    title: Text255 | None = None
    author: Text255 | None = None
    isbn: str | None = None
    genre: Genre | None = None
    page_count: int | None = Field(None, ge=1)
    total_copies: int | None = Field(None, ge=0)
    description: str | None = Field(None, max_length=2000)
    year: int | None = None
    cover_url: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _no_null_required(self):
        # Only year and cover_url may be cleared with null.
        nulls = [f for f in self.model_fields_set & REQUIRED if getattr(self, f) is None]
        if nulls:
            raise ValueError(f"{', '.join(sorted(nulls))} cannot be null")
        return self
