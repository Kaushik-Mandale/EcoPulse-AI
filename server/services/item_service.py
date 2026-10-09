from sqlalchemy.orm import Session
from typing import List, Optional
from server.models.item import Item
from server.models.user import User
from server.schemas.item import ItemCreate, ItemResponse

class ItemService:
    @staticmethod
    def get_all_items(db: Session) -> List[ItemResponse]:
        items = db.query(Item).all()
        if not items:
            ItemService.seed_default_items(db)
            items = db.query(Item).all()

        return [ItemService._to_response(i) for i in items]

    @staticmethod
    def get_item_by_id(db: Session, item_id: int) -> ItemResponse:
        item = db.query(Item).filter(Item.id == item_id).first()
        if item:
            return ItemService._to_response(item)
        return None

    @staticmethod
    def create_item(db: Session, payload: ItemCreate, current_user: Optional[User] = None) -> ItemResponse:
        owner_name = (current_user.full_name or current_user.email) if current_user else "Anonymous"
        owner_id = current_user.id if current_user else None
        new_item = Item(
            owner_id=owner_id,
            owner_name=owner_name,
            title=payload.title,
            category=payload.category,
            offered_city=payload.offered_city,
            desired_city=payload.desired_city,
            description=payload.description,
            image_url=payload.image_url,
        )
        db.add(new_item)
        db.commit()
        db.refresh(new_item)
        return ItemService._to_response(new_item)

    @staticmethod
    def seed_default_items(db: Session):
        seeds = [
            Item(id=1, title="Vintage Bicycle", category="Transportation", offered_city="New York", desired_city="London", description="Restored 1980s road bike in excellent condition.", owner_name="Alice"),
            Item(id=2, title="Apartment Stay (1 Week)", category="Housing", offered_city="Tokyo", desired_city="Paris", description="Cozy 1BR in Shibuya available for home swap.", owner_name="Kenji"),
            Item(id=3, title="DSLR Camera Kit", category="Electronics", offered_city="Berlin", desired_city="Barcelona", description="Canon DSLR with 18-55mm & 50mm lenses.", owner_name="Elena"),
        ]
        db.add_all(seeds)
        db.commit()

    @staticmethod
    def _to_response(i: Item) -> ItemResponse:
        return ItemResponse(
            id=i.id,
            title=i.title,
            category=i.category,
            offered_city=i.offered_city,
            desired_city=i.desired_city,
            description=i.description,
            owner=i.owner_name or "Anonymous",
            status=i.status or "Available",
            image_url=i.image_url
        )
