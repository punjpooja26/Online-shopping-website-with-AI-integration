from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/api/wishlist", tags=["Wishlist"])

@router.get("/", response_model=List[schemas.WishlistItemResponse])
def get_wishlist(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.WishlistItem).filter(models.WishlistItem.user_id == current_user.id).all()


@router.post("/{product_id}", response_model=schemas.WishlistItemResponse, status_code=status.HTTP_201_CREATED)
def add_to_wishlist(
    product_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # Verify product
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found."
        )
        
    # Check if exists
    existing = db.query(models.WishlistItem).filter(
        models.WishlistItem.user_id == current_user.id,
        models.WishlistItem.product_id == product_id
    ).first()
    
    if existing:
        return existing
        
    new_wish_item = models.WishlistItem(
        user_id=current_user.id,
        product_id=product_id
    )
    db.add(new_wish_item)
    db.commit()
    db.refresh(new_wish_item)
    return new_wish_item


@router.delete("/{product_id}", status_code=status.HTTP_200_OK)
def delete_from_wishlist(
    product_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    wish_item = db.query(models.WishlistItem).filter(
        models.WishlistItem.user_id == current_user.id,
        models.WishlistItem.product_id == product_id
    ).first()
    
    if not wish_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not in wishlist."
        )
        
    db.delete(wish_item)
    db.commit()
    return {"message": "Item removed from wishlist."}
