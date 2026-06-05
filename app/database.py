import os
import re
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

def get_db_url():
    url = os.getenv("DATABASE_URL")
    
    if not url:
        print("DATABASE_URL not found in environment, using local fallback.")
        return "postgresql://user:password@localhost/transport_db"
    
    # Clean whitespace and quotes
    url = url.strip().strip("\"'")
    
    # Debug info (masked for safety)
    has_scheme = url.startswith("postgres")
    has_at = "@" in url
    print(f"DEBUG: URL length: {len(url)}, Has scheme: {has_scheme}, Has @: {has_at}")
    
    # Fix 'postgres://' for SQLAlchemy 1.4+
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    # If the prefix is missing but it looks like a connection string
    if not url.startswith("postgresql://"):
        if "@" in url:
            url = "postgresql://" + url
        else:
            # If it's just host:port/db or similar, add prefix
            # But if it's missing @, it might be the cause of the ValueError
            print("WARNING: DATABASE_URL might be missing the '@' separator between credentials and hostname.")
            url = "postgresql://" + url
        
    return url

SQLALCHEMY_DATABASE_URL = get_db_url()

try:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    # Test connection creation (doesn't connect yet)
    print("SQLAlchemy engine created successfully.")
except Exception as e:
    print(f"ERROR creating SQLAlchemy engine: {e}")
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
