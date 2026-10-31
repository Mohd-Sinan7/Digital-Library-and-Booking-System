"""Book Catalog module. Other modules call these functions in-process (see docs/api-contract.md)."""

from src.catalog.service import (
    change_available_copies,
    get_availability,
    get_book,
    get_books,
)

__all__ = ["change_available_copies", "get_availability", "get_book", "get_books"]
