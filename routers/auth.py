from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email is already registered."
        )
    
    # Create new user
    hashed_pass = auth.get_password_hash(user_in.password)
    new_user = models.User(
        name=user_in.name,
        email=user_in.email,
        password_hash=hashed_pass,
        is_admin=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Sync new user registration contact with HubSpot CRM
    try:
        from app.routers.chatbot import get_or_create_hubspot_contact
        get_or_create_hubspot_contact(email=new_user.email, name=new_user.name)
    except Exception as hs_err:
        print(f"HubSpot registration sync failed for {new_user.email}: {hs_err}")
    return new_user


@router.post("/login", response_model=schemas.Token)
def login(user_in: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if not user or not auth.verify_password(user_in.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )
    
    # Generate token
    token_data = {"sub": user.email, "user_id": user.id, "is_admin": user.is_admin}
    access_token = auth.create_access_token(data=token_data)
    return {"access_token": access_token, "token_type": "bearer"}


# Swagger Form Login endpoint
@router.post("/login-form", response_model=schemas.Token)
def login_form(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )
    
    token_data = {"sub": user.email, "user_id": user.id, "is_admin": user.is_admin}
    access_token = auth.create_access_token(data=token_data)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.post("/forgot-password")
def forgot_password(req: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email).first()
    if not user:
        return {"message": "Recovery instructions simulated. Please check server logs."}
    
    # Simulated recovery token
    reset_token = auth.create_access_token(data={"sub": user.email, "action": "password_reset"})
    return {
        "message": "Recovery instructions simulated. Reset link generated successfully.",
        "simulated_reset_token": reset_token,
        "simulated_reset_link": f"/reset-password.html?token={reset_token}"
    }


@router.post("/reset-password")
def reset_password(req: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Could not validate reset token or token has expired.",
    )
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(req.token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email: str = payload.get("sub")
        action: str = payload.get("action")
        if email is None or action != "password_reset":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User associated with token not found."
        )
        
    user.password_hash = auth.get_password_hash(req.new_password)
    db.commit()
    return {"message": "Password has been successfully reset. Directing to login grid."}

