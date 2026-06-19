from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Use SQLite for development
SQLALCHEMY_DATABASE_URL = "sqlite:///./ecommerce.db"

# Create Database Engine
# connect_args={"check_same_thread": False} is required only for SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Create Session Maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base model class
Base = declarative_base()

# Dependency to yield database sessions to API endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
