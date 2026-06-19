from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid
from typing import List
from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/api/orders", tags=["Orders"])

@router.post("/", response_model=schemas.OrderResponse, status_code=status.HTTP_201_CREATED)
def checkout_order(
    order_in: schemas.OrderCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # Fetch user cart items
    cart_items = db.query(models.CartItem).filter(models.CartItem.user_id == current_user.id).all()
    if not cart_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your shopping cart is empty."
        )
        
    # Verify stock availability for all products and calculate total
    calculated_subtotal = 0.0
    products_to_update = []
    
    for item in cart_items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product ID {item.product_id} no longer exists."
            )
        if product.stock < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product '{product.name}' has insufficient inventory stock ({product.stock} units available)."
            )
        calculated_subtotal += product.price * item.quantity
        products_to_update.append((product, item.quantity))
        
    # Apply coupon discount
    discount = 0.0
    if order_in.coupon_code:
        c_code = order_in.coupon_code.upper()
        if c_code == "SAVE10":
            discount = calculated_subtotal * 0.10
        elif c_code == "AURA20":
            discount = calculated_subtotal * 0.20
        elif c_code == "WELCOME50":
            discount = calculated_subtotal * 0.50
            
    subtotal_after_discount = calculated_subtotal - discount
    tax = subtotal_after_discount * 0.05
    shipping = 0.0 if subtotal_after_discount >= 100.0 else 10.0
    final_total = subtotal_after_discount + tax + shipping
    
    # Check if client submitted a verified total
    if order_in.total_amount is not None:
        if abs(order_in.total_amount - final_total) < 1.0:
            final_total = order_in.total_amount
        
    # Create Order
    new_order = models.Order(
        user_id=current_user.id,
        status="Pending",
        total_amount=final_total,
        shipping_address=order_in.shipping_address
    )
    db.add(new_order)
    db.commit()  # Commit to generate new_order.id
    
    # Create Order Items and update product stock
    for product, qty in products_to_update:
        order_item = models.OrderItem(
            order_id=new_order.id,
            product_id=product.id,
            quantity=qty,
            price=product.price
        )
        product.stock -= qty  # Deduct stock
        db.add(order_item)
        
    # Create Payment Log
    payment = models.Payment(
        order_id=new_order.id,
        payment_method=order_in.payment_method,
        status="Success" if order_in.payment_method != "COD" else "Pending",
        transaction_id=str(uuid.uuid4()) if order_in.payment_method != "COD" else None
    )
    db.add(payment)
    
    # Empty User Cart
    db.query(models.CartItem).filter(models.CartItem.user_id == current_user.id).delete()
    
    db.commit()
    db.refresh(new_order)
    return new_order


@router.get("/", response_model=List[schemas.OrderResponse])
def get_order_history(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.Order).filter(models.Order.user_id == current_user.id).order_by(models.Order.id.desc()).all()


@router.get("/{order_id}", response_model=schemas.OrderResponse)
def get_order_detail(
    order_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found."
        )
    # Verify owner or admin
    if order.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this order."
        )
    return order


@router.put("/{order_id}/status", response_model=schemas.OrderResponse)
def update_order_status(
    order_id: int,
    status_update: str,  # Pending, Shipped, Delivered, Cancelled
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_admin_user)
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found."
        )
        
    valid_statuses = ["Pending", "Shipped", "Delivered", "Cancelled"]
    if status_update not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order status. Must be one of {valid_statuses}."
        )
        
    order.status = status_update
    
    # Update payment status if COD goes to Delivered
    if order.payment and order.payment.payment_method == "COD" and status_update == "Delivered":
        order.payment.status = "Success"
        order.payment.transaction_id = str(uuid.uuid4())
        
    db.commit()
    db.refresh(order)
    return order
