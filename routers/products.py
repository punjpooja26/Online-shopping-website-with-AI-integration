from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/api/products", tags=["Products"])

@router.get("/", response_model=dict)
def get_products(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    min_rating: Optional[float] = Query(None),
    sort_by: Optional[str] = Query(None, description="price_asc, price_desc, rating_desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=100)
):
    query = db.query(models.Product)
    
    # Filter conditions list
    filters = []
    
    if search:
        filters.append(
            or_(
                models.Product.name.ilike(f"%{search}%"),
                models.Product.description.ilike(f"%{search}%")
            )
        )
    
    if category_id:
        filters.append(models.Product.category_id == category_id)
        
    if min_price is not None:
        filters.append(models.Product.price >= min_price)
        
    if max_price is not None:
        filters.append(models.Product.price <= max_price)
        
    if min_rating is not None:
        filters.append(models.Product.rating >= min_rating)
        
    if filters:
        query = query.filter(and_(*filters))
        
    # Sorting
    if sort_by == "price_asc":
        query = query.order_by(models.Product.price.asc())
    elif sort_by == "price_desc":
        query = query.order_by(models.Product.price.desc())
    elif sort_by == "rating_desc":
        query = query.order_by(models.Product.rating.desc())
    else:
        query = query.order_by(models.Product.id.desc())
        
    # Count totals
    total_count = query.count()
    
    # Paginate
    offset = (page - 1) * limit
    products = query.offset(offset).limit(limit).all()
    
    # Convert relationships
    products_res = []
    for p in products:
        p_res = schemas.ProductResponse.from_orm(p)
        products_res.append(p_res)
        
    return {
        "products": products_res,
        "total": total_count,
        "page": page,
        "pages": (total_count + limit - 1) // limit
    }


@router.get("/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found."
        )
    return product


@router.post("/", response_model=schemas.ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product_in: schemas.ProductCreate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_admin_user)
):
    # Verify category exists
    category = db.query(models.Category).filter(models.Category.id == product_in.category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target category does not exist."
        )
        
    new_product = models.Product(**product_in.dict())
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return new_product


@router.put("/{product_id}", response_model=schemas.ProductResponse)
def update_product(
    product_id: int,
    product_in: schemas.ProductCreate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_admin_user)
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found."
        )
        
    # Verify category
    category = db.query(models.Category).filter(models.Category.id == product_in.category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target category does not exist."
        )
        
    for key, val in product_in.dict().items():
        setattr(product, key, val)
        
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_200_OK)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_admin_user)
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found."
        )
        
    db.delete(product)
    db.commit()
    return {"message": "Product successfully deleted."}
