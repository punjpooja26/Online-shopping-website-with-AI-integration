from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/api/reviews", tags=["Reviews"])

@router.post("/", response_model=schemas.ReviewResponse, status_code=status.HTTP_201_CREATED)
def submit_review(
    review_in: schemas.ReviewCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # Verify product
    product = db.query(models.Product).filter(models.Product.id == review_in.product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found."
        )
        
    # Check if user has already reviewed the product
    existing_review = db.query(models.Review).filter(
        models.Review.user_id == current_user.id,
        models.Review.product_id == review_in.product_id
    ).first()
    
    if existing_review:
        # Update existing review
        existing_review.rating = review_in.rating
        existing_review.comment = review_in.comment
        new_review = existing_review
    else:
        new_review = models.Review(
            user_id=current_user.id,
            product_id=review_in.product_id,
            rating=review_in.rating,
            comment=review_in.comment
        )
        db.add(new_review)
        
    db.commit()
    db.refresh(new_review)
    
    # Recalculate product average rating
    avg_rating = db.query(func.avg(models.Review.rating)).filter(
        models.Review.product_id == review_in.product_id
    ).scalar()
    
    product.rating = round(float(avg_rating or 0.0), 1)
    db.commit()
    
    return new_review


@router.get("/{product_id}", response_model=List[schemas.ReviewResponse])
def get_product_reviews(product_id: int, db: Session = Depends(get_db)):
    # Verify product
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found."
        )
        
    return db.query(models.Review).filter(models.Review.product_id == product_id).order_by(models.Review.id.desc()).all()
