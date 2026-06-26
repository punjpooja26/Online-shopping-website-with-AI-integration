from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/api/cart", tags=["Shopping Cart"])

@router.get("/", response_model=List[schemas.CartItemResponse])
def get_cart(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.CartItem).filter(models.CartItem.user_id == current_user.id).all()


@router.post("/", response_model=schemas.CartItemResponse, status_code=status.HTTP_201_CREATED)
def add_to_cart(
    item_in: schemas.CartItemCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # Verify product exists and has stock
    product = db.query(models.Product).filter(models.Product.id == item_in.product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found."
        )
        
    if product.stock < item_in.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {product.stock} units are available in inventory."
        )
        
    # Check if item already in cart
    existing_item = db.query(models.CartItem).filter(
        models.CartItem.user_id == current_user.id,
        models.CartItem.product_id == item_in.product_id
    ).first()
    
    if existing_item:
        new_qty = existing_item.quantity + item_in.quantity
        if product.stock < new_qty:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add quantity. Total cart items would exceed available inventory stock ({product.stock})."
            )
        existing_item.quantity = new_qty
        db.commit()
        db.refresh(existing_item)
        return existing_item
        
    new_cart_item = models.CartItem(
        user_id=current_user.id,
        product_id=item_in.product_id,
        quantity=item_in.quantity
    )
    db.add(new_cart_item)
    db.commit()
    db.refresh(new_cart_item)
    return new_cart_item


@router.put("/{item_id}", response_model=schemas.CartItemResponse)
def update_cart_item(
    item_id: int,
    item_update: schemas.CartItemUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    cart_item = db.query(models.CartItem).filter(
        models.CartItem.id == item_id,
        models.CartItem.user_id == current_user.id
    ).first()
    
    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found."
        )
        
    # Verify stock limits
    product = db.query(models.Product).filter(models.Product.id == cart_item.product_id).first()
    if product.stock < item_update.quantity:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {product.stock} units are available in inventory."
        )
        
    cart_item.quantity = item_update.quantity
    db.commit()
    db.refresh(cart_item)
    return cart_item


@router.delete("/{item_id}", status_code=status.HTTP_200_OK)
def delete_cart_item(
    item_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    cart_item = db.query(models.CartItem).filter(
        models.CartItem.id == item_id,
        models.CartItem.user_id == current_user.id
    ).first()
    
    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found."
        )
        
    db.delete(cart_item)
    db.commit()
    return {"message": "Cart item removed."}


@router.delete("/", status_code=status.HTTP_200_OK)
def clear_cart(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    db.query(models.CartItem).filter(models.CartItem.user_id == current_user.id).delete()
    db.commit()
    return {"message": "Cart cleared successfully."}
