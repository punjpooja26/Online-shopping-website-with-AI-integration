from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/api/admin", tags=["Admin Portal"])

@router.get("/stats", response_model=schemas.AdminStatsResponse)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_admin_user)
):
    # Sum total sales from completed/delivered orders, or all non-cancelled orders
    total_sales = db.query(func.sum(models.Order.total_amount)).filter(
        models.Order.status != "Cancelled"
    ).scalar() or 0.0
    
    total_orders = db.query(models.Order).count()
    total_users = db.query(models.User).count()
    total_products = db.query(models.Product).count()
    total_leads = db.query(models.Lead).count()
    total_pageviews = db.query(models.VisitorLog).count()
    avg_session_duration = db.query(func.avg(models.VisitorLog.duration)).scalar() or 0.0
    
    return {
        "total_sales": float(total_sales),
        "total_orders": total_orders,
        "total_users": total_users,
        "total_products": total_products,
        "total_leads": total_leads,
        "total_pageviews": total_pageviews,
        "avg_session_duration": round(float(avg_session_duration), 1)
    }


@router.get("/orders", response_model=List[schemas.OrderResponse])
def get_all_orders(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_admin_user)
):
    # Return all system orders for admin management
    return db.query(models.Order).order_by(models.Order.id.desc()).all()


@router.get("/customers", response_model=List[schemas.UserResponse])
def get_all_customers(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_admin_user)
):
    # Return all registered users for customer management (excluding sensitive passwords)
    return db.query(models.User).order_by(models.User.id.desc()).all()


@router.delete("/customers/{customer_id}", status_code=status.HTTP_200_OK)
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_admin_user)
):
    # Find customer
    customer = db.query(models.User).filter(models.User.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found."
        )
    if customer.is_admin:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System administrators cannot be deleted."
        )
        
    db.delete(customer)
    db.commit()
    return {"message": "Customer record deleted successfully."}
