import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

def get_db_url():
    url = os.getenv("DATABASE_URL")
    
    if not url:
        return "postgresql://user:password@localhost/transport_db"
    
    # Clean whitespace and quotes
    url = url.strip().strip("\"'")
    
    # Fix 'postgres://' for SQLAlchemy 1.4+
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    # If the prefix is missing but it looks like a connection string (contains @ and :)
    # Example: user:pass@host:port/db
    if not url.startswith("postgresql://") and "@" in url and ":" in url:
        url = "postgresql://" + url
        
    # Final check: if it still doesn't look like a valid SQLAlchemy URL, fallback to local
    if not url.startswith("postgresql://"):
        return "postgresql://user:password@localhost/transport_db"
        
    return url

SQLALCHEMY_DATABASE_URL = get_db_url()

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
