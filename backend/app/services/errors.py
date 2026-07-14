"""Shared service-layer errors."""
from __future__ import annotations


class DishNotFound(Exception):
    """Raised when a referenced dish does not exist."""

    def __init__(self, dish_id: int):
        super().__init__(f"dish {dish_id} not found")
        self.dish_id = dish_id
