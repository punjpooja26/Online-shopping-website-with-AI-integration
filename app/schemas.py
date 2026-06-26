from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

# ==========================================================================
# USER SCHEMAS
# ==========================================================================
class UserBase(BaseModel):
    email: EmailStr
    name: str

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: int
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[int] = None
    is_admin: bool = False

# ==========================================================================
# CATEGORY SCHEMAS
# ==========================================================================
class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryResponse(CategoryBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================================================
# PRODUCT SCHEMAS
# ==========================================================================
class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    original_price: Optional[float] = None
    stock: int = Field(..., ge=0)
    category_id: int
    image_url: Optional[str] = None
    gallery_images: Optional[str] = None
    sizes: Optional[str] = None
    colors: Optional[str] = None
    specifications: Optional[str] = None

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int
    rating: float
    created_at: datetime
    category: Optional[CategoryResponse] = None

    class Config:
        from_attributes = True

# ==========================================================================
# CART SCHEMAS
# ==========================================================================
class CartItemBase(BaseModel):
    product_id: int
    quantity: int = Field(1, ge=1)

class CartItemCreate(CartItemBase):
    pass

class CartItemUpdate(BaseModel):
    quantity: int = Field(..., ge=1)

class CartItemResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    quantity: int
    created_at: datetime
    product: ProductResponse

    class Config:
        from_attributes = True

# ==========================================================================
# WISHLIST SCHEMAS
# ==========================================================================
class WishlistItemResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    created_at: datetime
    product: ProductResponse

    class Config:
        from_attributes = True

# ==========================================================================
# REVIEW SCHEMAS
# ==========================================================================
class ReviewCreate(BaseModel):
    product_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class ReviewResponse(ReviewCreate):
    id: int
    user_id: int
    created_at: datetime
    user: Optional[UserResponse] = None

    class Config:
        from_attributes = True

# ==========================================================================
# PAYMENT SCHEMAS
# ==========================================================================
class PaymentResponse(BaseModel):
    id: int
    payment_method: str
    status: str
    transaction_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================================================
# ORDER SCHEMAS
# ==========================================================================
class OrderItemResponse(BaseModel):
    id: int
    product_id: Optional[int]
    quantity: int
    price: float
    product: Optional[ProductResponse] = None

    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    shipping_address: str
    payment_method: str = Field("COD", description="COD, Credit Card, PayPal, UPI")
    total_amount: Optional[float] = None
    coupon_code: Optional[str] = None

class OrderResponse(BaseModel):
    id: int
    user_id: int
    status: str
    total_amount: float
    shipping_address: str
    created_at: datetime
    items: List[OrderItemResponse] = []
    payment: Optional[PaymentResponse] = None

    class Config:
        from_attributes = True

# ==========================================================================
# CHATBOT SCHEMAS
# ==========================================================================
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str

# ==========================================================================
# ADMIN STATS SCHEMAS
# ==========================================================================
class AdminStatsResponse(BaseModel):
    total_sales: float
    total_orders: int
    total_users: int
    total_products: int
    total_leads: int
    total_pageviews: int
    avg_session_duration: float

# ==========================================================================
# VISITOR & ANALYTICS SCHEMAS
# ==========================================================================
class VisitorLogBase(BaseModel):
    session_id: str
    page_url: str
    product_id: Optional[int] = None
    cart_activity: Optional[str] = None
    duration: Optional[float] = 0.0

class VisitorLogCreate(VisitorLogBase):
    pass

class VisitorLogResponse(VisitorLogBase):
    id: int
    user_id: Optional[int] = None
    visited_at: datetime
    product: Optional[ProductResponse] = None

    class Config:
        from_attributes = True

# ==========================================================================
# CHAT HISTORY SCHEMAS
# ==========================================================================
class ChatHistoryBase(BaseModel):
    session_id: str
    sender: str
    message: str

class ChatHistoryCreate(ChatHistoryBase):
    pass

class ChatHistoryResponse(ChatHistoryBase):
    id: int
    user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================================================
# LEAD SCHEMAS
# ==========================================================================
class LeadBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None

class LeadCreate(LeadBase):
    pass

class LeadResponse(LeadBase):
    id: int
    hubspot_contact_id: Optional[str] = None
    hubspot_sync_status: str
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================================================
# FORGOT PASSWORD SCHEMA
# ==========================================================================
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

# ==========================================================================
# RESET PASSWORD SCHEMA
# ==========================================================================
class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)

# ==========================================================================
# VISITOR HEARTBEAT SCHEMA
# ==========================================================================
class VisitorHeartbeat(BaseModel):
    session_id: str
    page_url: str
    duration: float


# ==========================================================================
# FAQ SCHEMAS
# ==========================================================================
class FAQBase(BaseModel):
    question: str
    answer: str
    keywords: Optional[str] = None

class FAQCreate(FAQBase):
    pass

class FAQResponse(FAQBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True



