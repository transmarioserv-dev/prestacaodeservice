import os
import re
import time
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

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
            print("WARNING: DATABASE_URL might be missing the '@' separator between credentials and hostname.")
            url = "postgresql://" + url
        
    return url

SQLALCHEMY_DATABASE_URL = get_db_url()

# Retry logic for database connection (especially for Docker Compose)
max_retries = 5
retry_interval = 5
engine = None

for i in range(max_retries):
    try:
        engine = create_engine(SQLALCHEMY_DATABASE_URL)
        # Test connection
        with engine.connect() as conn:
            print("Successfully connected to the database!")
        break
    except OperationalError as e:
        if i < max_retries - 1:
            print(f"Database connection failed. Retrying in {retry_interval} seconds... ({i+1}/{max_retries})")
            time.sleep(retry_interval)
        else:
            print("Could not connect to the database after several retries.")
            raise e

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
