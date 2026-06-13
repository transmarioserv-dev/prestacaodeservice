import sys
import os
from datetime import date
from sqlalchemy.orm import Session
# Add the project root to sys.path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal
from app import models

# Data extracted from OCR of relatorios/fuel_fillings_report_2026_06_11...pdf
fuel_data = {
    "ADJ-868-MP": {"count": 1, "volume": 173.81},
    "AEM-973-MP": {"count": 2, "volume": 117.1},
    "AHO-519-MP": {"count": 2, "volume": 365.53},
    "AHQ-168-MP": {"count": 1, "volume": 15.37},
    "AIP-793-MC": {"count": 2, "volume": 731.64},
    "AIT-150-MC": {"count": 1, "volume": 88.71},
    "AJB-829-MC": {"count": 1, "volume": 51.9},
    "AJD-073-MC": {"count": 1, "volume": 72.29},
    "AJD-081-MC": {"count": 4, "volume": 114.87},
    "AKK-607-MC": {"count": 1, "volume": 85.24},
    "AKK-942-MP": {"count": 1, "volume": 11.88},
    "AKL-017-MP": {"count": 2, "volume": 67.85},
    "AKN-684-MP": {"count": 1, "volume": 11.38},
    "AKN-713-MP": {"count": 1, "volume": 65.91},
    "AKO-543-MC": {"count": 1, "volume": 79.5},
    "AKX-117-MC": {"count": 1, "volume": 48.91},
    "ALZ-088-MC": {"count": 5, "volume": 1058.59},
    "AOE-310-MC": {"count": 1, "volume": 33.11},
}

def ingest_fuel_fillings():
    db = SessionLocal()
    report_date = date(2026, 6, 11)
    
    try:
        for plate, data in fuel_data.items():
            print(f"Processing {plate}...")
            # Find or create vehicle
            vehicle = db.query(models.Vehicle).filter(models.Vehicle.plate == plate).first()
            if not vehicle:
                print(f"Vehicle {plate} not found. Creating...")
                vehicle = models.Vehicle(plate=plate, status="Disponível")
                db.add(vehicle)
                db.commit()
                db.refresh(vehicle)
            
            # Find or create telemetry record for this date
            telemetry = db.query(models.VehicleTelemetry).filter(
                models.VehicleTelemetry.vehicle_id == vehicle.id,
                models.VehicleTelemetry.date == report_date
            ).first()
            
            if not telemetry:
                print(f"No telemetry record for {plate} on {report_date}. Creating...")
                telemetry = models.VehicleTelemetry(
                    vehicle_id=vehicle.id,
                    date=report_date,
                    refueling_count=data["count"],
                    refueling_volume=data["volume"]
                )
                db.add(telemetry)
            else:
                print(f"Updating existing telemetry record for {plate} on {report_date}.")
                telemetry.refueling_count = data["count"]
                telemetry.refueling_volume = data["volume"]
            
            # Calculate efficiency if route_length is available
            if telemetry.route_length and telemetry.refueling_volume > 0:
                telemetry.fuel_efficiency = telemetry.route_length / telemetry.refueling_volume
            
        db.commit()
        print("Successfully ingested fuel filling data for 2026-06-11.")
    except Exception as e:
        print(f"Error during ingestion: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    ingest_fuel_fillings()
