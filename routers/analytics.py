from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
import datetime
import re
from jose import jwt, JWTError

from app.database import get_db
from app import models, schemas, auth
from app.routers.chatbot import log_activity_to_hubspot

router = APIRouter(prefix="/api/analytics", tags=["Visitor Tracking & Analytics"])

def get_optional_user(request: Request, db: Session) -> Optional[models.User]:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        user_id = payload.get("user_id")
        if user_id:
            return db.query(models.User).filter(models.User.id == user_id).first()
    except JWTError:
        pass
    return None

def get_lead_email(db: Session, session_id: Optional[str], user_id: Optional[int]) -> Optional[str]:
    if user_id:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user:
            return user.email
    if session_id:
        chats = db.query(models.ChatHistory).filter(
            models.ChatHistory.session_id == session_id,
            models.ChatHistory.sender == "user"
        ).all()
        for chat in chats:
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', chat.message)
            if email_match:
                email = email_match.group(0).strip().lower()
                lead = db.query(models.Lead).filter(models.Lead.email.ilike(email)).first()
                if lead:
                    return lead.email
    return None

def sync_activity_note_to_hubspot(db: Session, payload: schemas.VisitorLogCreate, user_id: Optional[int]):
    email = get_lead_email(db, payload.session_id, user_id)
    if not email:
        return
        
    try:
        activity_str = "viewed page"
        product_detail = ""
        if payload.product_id:
            product = db.query(models.Product).filter(models.Product.id == payload.product_id).first()
            if product:
                product_detail = f" (Product: {product.name}, Price: ${product.price:.2f})"
        
        if payload.cart_activity == "add_to_cart":
            activity_str = "added product to cart"
        elif payload.cart_activity == "checkout_complete":
            activity_str = "completed checkout transaction"
        elif payload.cart_activity == "contact_submit":
            activity_str = "submitted contact/inquiry form"
            
        note_body = f"<strong>Website Activity:</strong> Visitor {activity_str}{product_detail} on page {payload.page_url}"
        log_activity_to_hubspot(email, note_body)
    except Exception as hs_err:
        print(f"Failed to log website activity to HubSpot: {hs_err}")

@router.post("/log", status_code=status.HTTP_201_CREATED)
def log_visit(
    payload: schemas.VisitorLogCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    current_user = get_optional_user(request, db)
    user_id = current_user.id if current_user else None
    
    # Check if a log for this session and URL was created in the last 15 minutes
    time_threshold = datetime.datetime.utcnow() - datetime.timedelta(minutes=15)
    existing_log = db.query(models.VisitorLog).filter(
        models.VisitorLog.session_id == payload.session_id,
        models.VisitorLog.page_url == payload.page_url,
        models.VisitorLog.visited_at >= time_threshold
    ).order_by(models.VisitorLog.visited_at.desc()).first()
    
    if existing_log:
        if payload.duration is not None and payload.duration > existing_log.duration:
            existing_log.duration = payload.duration
        if payload.cart_activity:
            existing_log.cart_activity = payload.cart_activity
        if user_id:
            existing_log.user_id = user_id
        db.commit()
        db.refresh(existing_log)
        
        # Sync to HubSpot CRM
        sync_activity_note_to_hubspot(db, payload, user_id)
        
        return {"log_id": existing_log.id, "message": "Updated existing log."}
        
    # Otherwise create a new log
    new_log = models.VisitorLog(
        session_id=payload.session_id,
        user_id=user_id,
        page_url=payload.page_url,
        product_id=payload.product_id,
        cart_activity=payload.cart_activity,
        duration=payload.duration or 0.0
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    
    # Sync to HubSpot CRM
    sync_activity_note_to_hubspot(db, payload, user_id)
    
    return {"log_id": new_log.id, "message": "Created new visit log."}


@router.post("/heartbeat")
def record_heartbeat(
    payload: schemas.VisitorHeartbeat,
    db: Session = Depends(get_db)
):
    # Find the most recent pageview log for this session and page_url
    log_entry = db.query(models.VisitorLog).filter(
        models.VisitorLog.session_id == payload.session_id,
        models.VisitorLog.page_url == payload.page_url
    ).order_by(models.VisitorLog.visited_at.desc()).first()
    
    if log_entry:
        if payload.duration > log_entry.duration:
            log_entry.duration = payload.duration
            db.commit()
            return {"status": "success", "duration": log_entry.duration}
    return {"status": "not_found"}

@router.get("/dashboard")
def get_analytics_dashboard(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(auth.get_admin_user)
):
    # Overall summary metrics
    total_pageviews = db.query(models.VisitorLog).count()
    total_sessions = db.query(models.VisitorLog.session_id).distinct().count()
    avg_duration = db.query(func.avg(models.VisitorLog.duration)).scalar() or 0.0
    
    # Popular Products viewed
    popular_products_query = db.query(
        models.VisitorLog.product_id,
        models.Product.name,
        models.Product.price,
        func.count(models.VisitorLog.id).label("views")
    ).join(models.Product, models.VisitorLog.product_id == models.Product.id)\
     .group_by(models.VisitorLog.product_id, models.Product.name, models.Product.price)\
     .order_by(func.count(models.VisitorLog.id).desc())\
     .limit(5).all()
     
    popular_products = [
        {"id": row[0], "name": row[1], "price": row[2], "views": row[3]}
        for row in popular_products_query
    ]
    
    # Cart activities aggregation
    cart_activities_query = db.query(
        models.VisitorLog.cart_activity,
        func.count(models.VisitorLog.id)
    ).filter(models.VisitorLog.cart_activity.isnot(None))\
     .group_by(models.VisitorLog.cart_activity).all()
     
    cart_activities = {row[0]: row[1] for row in cart_activities_query}
    
    # Recent Visitor Logs (last 15 entries)
    recent_logs_query = db.query(models.VisitorLog).order_by(models.VisitorLog.visited_at.desc()).limit(15).all()
    recent_logs = []
    for log in recent_logs_query:
        recent_logs.append({
            "id": log.id,
            "session_id": log.session_id,
            "user_name": log.user.name if log.user else "Anonymous",
            "page_url": log.page_url,
            "product_name": log.product.name if log.product else None,
            "cart_activity": log.cart_activity,
            "duration": log.duration,
            "visited_at": log.visited_at.isoformat()
        })
        
    # Leads and HubSpot synchronization rates
    total_leads = db.query(models.Lead).count()
    synced_leads = db.query(models.Lead).filter(models.Lead.hubspot_sync_status == "Synced").count()
    failed_leads = db.query(models.Lead).filter(models.Lead.hubspot_sync_status == "Failed").count()
    
    recent_leads = db.query(models.Lead).order_by(models.Lead.created_at.desc()).limit(10).all()
    leads_list = [{
        "id": lead.id,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "hubspot_id": lead.hubspot_contact_id,
        "sync_status": lead.hubspot_sync_status,
        "created_at": lead.created_at.isoformat()
    } for lead in recent_leads]
    
    return {
        "summary": {
            "total_pageviews": total_pageviews,
            "total_sessions": total_sessions,
            "avg_duration": round(float(avg_duration), 1),
            "total_leads": total_leads,
            "synced_leads": synced_leads,
            "failed_leads": failed_leads
        },
        "popular_products": popular_products,
        "cart_activities": cart_activities,
        "recent_logs": recent_logs,
        "leads": leads_list
    }
