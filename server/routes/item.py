from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from server.database.db import get_db
from server.schemas.item import ItemCreate, ItemResponse
from server.services.item_service import ItemService
from server.utils.security import get_current_user
from server.models.user import User

router = APIRouter(prefix="/api/items", tags=["Items"])

@router.get("", response_model=List[ItemResponse])
def get_items(db: Session = Depends(get_db)):
    """Retrieve all available swap items."""
    return ItemService.get_all_items(db)

@router.get("/{item_id}", response_model=ItemResponse)
def get_item(item_id: int, db: Session = Depends(get_db)):
    """Retrieve a single swap item by ID."""
    item = ItemService.get_item_by_id(db, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID {item_id} not found"
        )
    return item

@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    item_data: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new swap item listing for the authenticated user."""
    return ItemService.create_item(db, item_data, current_user)
