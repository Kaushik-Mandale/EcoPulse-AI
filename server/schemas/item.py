from pydantic import BaseModel, ConfigDict
from typing import Optional

class ItemCreate(BaseModel):
    title: str
    category: str
    offered_city: str
    desired_city: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    owner: Optional[str] = None  # Ignored; derived strictly from authenticated user

class ItemResponse(BaseModel):
    id: int
    title: str
    category: str
    offered_city: str
    desired_city: str
    description: Optional[str] = None
    owner: str
    status: str
    image_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
