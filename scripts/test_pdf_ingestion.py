import sys
import os
from sqlalchemy.orm import Session
# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal
from app import utils

def test_ingestion():
    db = SessionLocal()
    file_path = "relatorios/fuel_fillings_report_2026_06_11_00_00_00_2026_06_11_23_40_00_17812143258262.pdf"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"Testing ingestion for: {file_path}")
    success = utils.process_report_file(file_path, db)
    
    if success:
        print("SUCCESS: Report processed successfully by utils.process_report_file.")
    else:
        print("FAILURE: Report format still not recognized.")
    
    db.close()

if __name__ == "__main__":
    test_ingestion()
