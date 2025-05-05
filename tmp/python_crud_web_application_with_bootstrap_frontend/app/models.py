# Generated implementation: app/models.py

from pydantic import BaseModel
from typing import Optional

__all__ = ["EntityModel"]

class EntityModel(BaseModel):
    """
    Represents the data transfer object for the entity.
    
    Attributes:
        id (int): Unique identifier for the entity. Auto-incremented in backend logic.
        name (str): Name of the entity.
        description (Optional[str]): Optional description of the entity.
    """
    id: int
    name: str
    description: Optional[str] = None