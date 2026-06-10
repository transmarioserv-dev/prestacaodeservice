from fastapi import FastAPI, Depends, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import inspect, text, func
from . import models, schemas, database, utils
from .database import engine, get_db
from datetime import date
import os
import shutil

# Create tables
models.Base.metadata.create_all(bind=engine)


# Quick migration for existing databases
def run_migrations():
    print("Checking for database migrations...")
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"Existing tables: {tables}")
        
        if "shipments" in tables:
            columns = [c["name"] for c in inspector.get_columns("shipments")]
            print(f"Columns in 'shipments' table: {columns}")
            if "shipment_date" not in columns:
                print("Attempting to add 'shipment_date' column to 'shipments' table...")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE shipments ADD COLUMN IF NOT EXISTS shipment_date DATE DEFAULT CURRENT_DATE"))
                    conn.commit()
                print("Migration: Added shipment_date column to shipments table.")
            else:
                print("'shipment_date' column already exists.")
        else:
            print("'shipments' table not found, metadata.create_all should handle it.")
    except Exception as e:
        print(f"Migration error: {e}")
        # Try a direct approach if the inspector failed
        try:
            print("Attempting direct migration...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE shipments ADD COLUMN IF NOT EXISTS shipment_date DATE DEFAULT CURRENT_DATE"))
                conn.commit()
            print("Direct migration successful.")
        except Exception as e2:
            print(f"Direct migration failed: {e2}")

run_migrations()

app = FastAPI(title="Mario Transport Service API")
templates = Jinja2Templates(directory="app/templates")

# Ensure reports directory exists
os.makedirs("relatorios", exist_ok=True)

# Mount reports directory as static files
app.mount("/reports_files", StaticFiles(directory="relatorios"), name="reports_files")

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    vehicles_count = db.query(models.Vehicle).count()
    drivers_count = db.query(models.Driver).count()
    shipments_count = db.query(models.Shipment).filter(models.Shipment.status != "Entregue").count()
    latest_shipments = db.query(models.Shipment).order_by(models.Shipment.id.desc()).limit(5).all()
    
    # Telemetry Stats
    total_km = db.query(func.sum(models.VehicleTelemetry.route_length)).scalar() or 0
    avg_fuel_cons = db.query(func.avg(models.VehicleTelemetry.fuel_consumption)).scalar() or 0
    
    # New Stats from Consolidated Report
    total_thefts_vol = db.query(func.sum(models.VehicleTelemetry.theft_volume)).scalar() or 0
    total_refills_vol = db.query(func.sum(models.VehicleTelemetry.refueling_volume)).scalar() or 0
    total_thefts_count = db.query(func.sum(models.VehicleTelemetry.theft_count)).scalar() or 0
    total_refills_count = db.query(func.sum(models.VehicleTelemetry.refueling_count)).scalar() or 0
    avg_efficiency = db.query(func.avg(models.VehicleTelemetry.fuel_efficiency)).filter(models.VehicleTelemetry.fuel_efficiency > 0).scalar() or 0
    
    # Financial loss (estimated US$ 1,20/L)
    estimated_loss = total_thefts_vol * 1.20

    # Critical vehicles (top thefts)
    critical_vehicles = db.query(
        models.Vehicle.plate, 
        func.sum(models.VehicleTelemetry.theft_volume).label("total_theft")
    ).join(models.VehicleTelemetry).group_by(models.Vehicle.plate).filter(models.VehicleTelemetry.theft_volume > 0).order_by(text("total_theft DESC")).limit(5).all()
    
    context = {
        "request": request,
        "vehicles_count": vehicles_count,
        "drivers_count": drivers_count,
        "shipments_count": shipments_count,
        "latest_shipments": latest_shipments,
        "total_km": round(total_km, 2),
        "avg_fuel": round(avg_fuel_cons, 2),
        "total_thefts_vol": round(total_thefts_vol, 2),
        "total_refills_vol": round(total_refills_vol, 2),
        "total_thefts_count": total_thefts_count,
        "total_refills_count": total_refills_count,
        "avg_efficiency": round(avg_efficiency, 2),
        "estimated_loss": round(estimated_loss, 2),
        "critical_vehicles": critical_vehicles
    }
    return templates.TemplateResponse(request=request, name="index.html", context=context)

# --- UI ROUTES ---

@app.get("/ui/reports", response_class=HTMLResponse)
def ui_reports(request: Request):
    reports = []
    relatorios_dir = "relatorios"
    for root, dirs, files in os.walk(relatorios_dir):
        for file in files:
            # Create a relative path from the 'relatorios' directory
            rel_path = os.path.relpath(os.path.join(root, file), relatorios_dir)
            reports.append({
                "name": file,
                "path": rel_path,
                "folder": os.path.basename(root) if root != relatorios_dir else "Principal"
            })
    
    # Sort by name descending (usually dates are in filenames)
    reports.sort(key=lambda x: x["name"], reverse=True)
    
    return templates.TemplateResponse(
        request=request, name="reports.html", context={"request": request, "reports": reports}
    )

@app.post("/ui/reports/upload")
async def ui_upload_report(
    request: Request,
    report_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    relatorios_dir = "relatorios"
    os.makedirs(relatorios_dir, exist_ok=True)
    
    file_path = os.path.join(relatorios_dir, report_file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(report_file.file, buffer)
    
    # Process the file to update database
    success = utils.process_report_file(file_path, db)
    
    # Prepare reports list for re-rendering with message
    reports = []
    for root, dirs, files in os.walk(relatorios_dir):
        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), relatorios_dir)
            reports.append({
                "name": file,
                "path": rel_path,
                "folder": os.path.basename(root) if root != relatorios_dir else "Principal"
            })
    reports.sort(key=lambda x: x["name"], reverse=True)
    
    msg = "Relatório enviado e processado com sucesso!" if success else "Relatório enviado, mas o formato não permitiu a extração automática de dados."
    
    return templates.TemplateResponse(
        request=request, name="reports.html", context={
            "request": request, 
            "reports": reports,
            "success_msg": msg if success else None,
            "info_msg": msg if not success else None
        }
    )

@app.get("/ui/vehicles", response_class=HTMLResponse)
def ui_vehicles(request: Request, db: Session = Depends(get_db)):
    vehicles = db.query(models.Vehicle).all()
    return templates.TemplateResponse(
        request=request, name="vehicles.html", context={"request": request, "vehicles": vehicles}
    )

@app.post("/ui/vehicles")
def ui_create_vehicle(
    plate: str = Form(...), model: str = Form(...), brand: str = Form(...), 
    year: int = Form(...), capacity: float = Form(...), type: str = Form(...),
    db: Session = Depends(get_db)
):
    db_vehicle = models.Vehicle(plate=plate, model=model, brand=brand, year=year, capacity=capacity, type=type)
    db.add(db_vehicle)
    db.commit()
    return RedirectResponse(url="/ui/vehicles", status_code=303)

@app.get("/ui/drivers", response_class=HTMLResponse)
def ui_drivers(request: Request, db: Session = Depends(get_db)):
    drivers = db.query(models.Driver).all()
    return templates.TemplateResponse(
        request=request, name="drivers.html", context={"request": request, "drivers": drivers}
    )

@app.post("/ui/drivers")
def ui_create_driver(
    name: str = Form(...), cpf: str = Form(...), cnh: str = Form(...), 
    category: str = Form(...), phone: str = Form(...), hire_date: str = Form(...),
    db: Session = Depends(get_db)
):
    db_driver = models.Driver(
        name=name, cpf=cpf, cnh=cnh, category=category, 
        phone=phone, hire_date=date.fromisoformat(hire_date)
    )
    db.add(db_driver)
    db.commit()
    return RedirectResponse(url="/ui/drivers", status_code=303)

@app.get("/ui/shipments", response_class=HTMLResponse)
def ui_shipments(request: Request, db: Session = Depends(get_db)):
    shipments = db.query(models.Shipment).all()
    vehicles = db.query(models.Vehicle).all()
    drivers = db.query(models.Driver).all()
    return templates.TemplateResponse(
        request=request, name="shipments.html", context={
            "request": request, "shipments": shipments, 
            "vehicles": vehicles, "drivers": drivers
        }
    )

@app.post("/ui/shipments")
def ui_create_shipment(
    request: Request,
    tracking_code: str = Form(...), description: str = Form(None), weight: float = Form(...),
    origin: str = Form(...), destination: str = Form(...), shipping_value: float = Form(...),
    status: str = Form(...), shipment_date: str = Form(...),
    vehicle_id: int = Form(None), driver_id: int = Form(None),
    db: Session = Depends(get_db)
):
    try:
        db_shipment = models.Shipment(
            tracking_code=tracking_code, description=description, weight=weight,
            origin=origin, destination=destination, shipping_value=shipping_value,
            status=status, shipment_date=date.fromisoformat(shipment_date),
            vehicle_id=vehicle_id, driver_id=driver_id
        )
        db.add(db_shipment)
        db.commit()
        # Add initial history entry
        db.refresh(db_shipment)
        history = models.ShipmentHistory(
            shipment_id=db_shipment.id,
            status=status,
            notes="Registro inicial da entrega"
        )
        db.add(history)
        db.commit()
    except IntegrityError:
        db.rollback()
        shipments = db.query(models.Shipment).all()
        vehicles = db.query(models.Vehicle).all()
        drivers = db.query(models.Driver).all()
        return templates.TemplateResponse(
            request=request, name="shipments.html", context={
                "request": request, "shipments": shipments,
                "vehicles": vehicles, "drivers": drivers,
                "error": f"Código de rastreio '{tracking_code}' já existe."
            }
        )
    return RedirectResponse(url="/ui/shipments", status_code=303)

# --- API Endpoints ---
@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# Vehicles
@app.get("/vehicles/{vehicle_id}", response_model=schemas.Vehicle)
def read_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    db_vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if db_vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return db_vehicle

@app.put("/vehicles/{vehicle_id}", response_model=schemas.Vehicle)
def update_vehicle(vehicle_id: int, vehicle: schemas.VehicleCreate, db: Session = Depends(get_db)):
    db_vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if db_vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    for var, value in vehicle.model_dump().items():
        setattr(db_vehicle, var, value) if value is not None else None
        
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle

@app.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    db_vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if db_vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    db.delete(db_vehicle)
    db.commit()
    return {"detail": "Vehicle deleted"}

# Drivers
@app.get("/drivers/{driver_id}", response_model=schemas.Driver)
def read_driver(driver_id: int, db: Session = Depends(get_db)):
    db_driver = db.query(models.Driver).filter(models.Driver.id == driver_id).first()
    if db_driver is None:
        raise HTTPException(status_code=404, detail="Driver not found")
    return db_driver

@app.put("/drivers/{driver_id}", response_model=schemas.Driver)
def update_driver(driver_id: int, driver: schemas.DriverCreate, db: Session = Depends(get_db)):
    db_driver = db.query(models.Driver).filter(models.Driver.id == driver_id).first()
    if db_driver is None:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    for var, value in driver.model_dump().items():
        setattr(db_driver, var, value) if value is not None else None
        
    db.commit()
    db.refresh(db_driver)
    return db_driver

@app.delete("/drivers/{driver_id}")
def delete_driver(driver_id: int, db: Session = Depends(get_db)):
    db_driver = db.query(models.Driver).filter(models.Driver.id == driver_id).first()
    if db_driver is None:
        raise HTTPException(status_code=404, detail="Driver not found")
    db.delete(db_driver)
    db.commit()
    return {"detail": "Driver deleted"}

# Shipments
@app.get("/shipments/{shipment_id}", response_model=schemas.Shipment)
def read_shipment(shipment_id: int, db: Session = Depends(get_db)):
    db_shipment = db.query(models.Shipment).filter(models.Shipment.id == shipment_id).first()
    if db_shipment is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return db_shipment

@app.put("/shipments/{shipment_id}", response_model=schemas.Shipment)
def update_shipment(shipment_id: int, shipment: schemas.ShipmentCreate, db: Session = Depends(get_db)):
    db_shipment = db.query(models.Shipment).filter(models.Shipment.id == shipment_id).first()
    if db_shipment is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    
    for var, value in shipment.model_dump().items():
        setattr(db_shipment, var, value) if value is not None else None
        
    db.commit()
    db.refresh(db_shipment)
    return db_shipment

@app.delete("/shipments/{shipment_id}")
def delete_shipment(shipment_id: int, db: Session = Depends(get_db)):
    db_shipment = db.query(models.Shipment).filter(models.Shipment.id == shipment_id).first()
    if db_shipment is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    db.delete(db_shipment)
    db.commit()
    return {"detail": "Shipment deleted"}

# --- UI CRUD Operations ---

@app.post("/ui/vehicles/{vehicle_id}/update")
def ui_update_vehicle(
    vehicle_id: int,
    plate: str = Form(...), model: str = Form(...), brand: str = Form(...), 
    year: int = Form(...), capacity: float = Form(...), type: str = Form(...),
    status: str = Form(...), db: Session = Depends(get_db)
):
    db_vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if db_vehicle:
        db_vehicle.plate = plate
        db_vehicle.model = model
        db_vehicle.brand = brand
        db_vehicle.year = year
        db_vehicle.capacity = capacity
        db_vehicle.type = type
        db_vehicle.status = status
        db.commit()
    return RedirectResponse(url="/ui/vehicles", status_code=303)

@app.get("/ui/vehicles/{vehicle_id}/delete")
def ui_delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    db_vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if db_vehicle:
        db.delete(db_vehicle)
        db.commit()
    return RedirectResponse(url="/ui/vehicles", status_code=303)

@app.post("/ui/drivers/{driver_id}/update")
def ui_update_driver(
    driver_id: int,
    name: str = Form(...), cpf: str = Form(...), cnh: str = Form(...), 
    category: str = Form(...), phone: str = Form(...), hire_date: str = Form(...),
    db: Session = Depends(get_db)
):
    db_driver = db.query(models.Driver).filter(models.Driver.id == driver_id).first()
    if db_driver:
        db_driver.name = name
        db_driver.cpf = cpf
        db_driver.cnh = cnh
        db_driver.category = category
        db_driver.phone = phone
        db_driver.hire_date = date.fromisoformat(hire_date)
        db.commit()
    return RedirectResponse(url="/ui/drivers", status_code=303)

@app.get("/ui/drivers/{driver_id}/delete")
def ui_delete_driver(driver_id: int, db: Session = Depends(get_db)):
    db_driver = db.query(models.Driver).filter(models.Driver.id == driver_id).first()
    if db_driver:
        db.delete(db_driver)
        db.commit()
    return RedirectResponse(url="/ui/drivers", status_code=303)

@app.post("/ui/shipments/{shipment_id}/update")
def ui_update_shipment(
    request: Request,
    shipment_id: int,
    tracking_code: str = Form(...), description: str = Form(None), weight: float = Form(...),
    origin: str = Form(...), destination: str = Form(...), shipping_value: float = Form(...),
    status: str = Form(...), shipment_date: str = Form(...),
    vehicle_id: int = Form(None), driver_id: int = Form(None),
    db: Session = Depends(get_db)
):
    db_shipment = db.query(models.Shipment).filter(models.Shipment.id == shipment_id).first()
    if db_shipment:
        old_status = db_shipment.status
        db_shipment.tracking_code = tracking_code
        db_shipment.description = description
        db_shipment.weight = weight
        db_shipment.origin = origin
        db_shipment.destination = destination
        db_shipment.shipping_value = shipping_value
        db_shipment.status = status
        db_shipment.shipment_date = date.fromisoformat(shipment_date)
        db_shipment.vehicle_id = vehicle_id
        db_shipment.driver_id = driver_id
        
        # If status changed, record it in history
        if old_status != status:
            history = models.ShipmentHistory(
                shipment_id=shipment_id,
                status=status,
                notes=f"Status alterado de {old_status} para {status}"
            )
            db.add(history)
            
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            shipments = db.query(models.Shipment).all()
            vehicles = db.query(models.Vehicle).all()
            drivers = db.query(models.Driver).all()
            return templates.TemplateResponse(
                request=request, name="shipments.html", context={
                    "request": request, "shipments": shipments,
                    "vehicles": vehicles, "drivers": drivers,
                    "error": f"Não foi possível atualizar. O código de rastreio '{tracking_code}' já existe."
                }
            )
    return RedirectResponse(url="/ui/shipments", status_code=303)

@app.get("/ui/shipments/{shipment_id}/delete")
def ui_delete_shipment(shipment_id: int, db: Session = Depends(get_db)):
    db_shipment = db.query(models.Shipment).filter(models.Shipment.id == shipment_id).first()
    if db_shipment:
        db.delete(db_shipment)
        db.commit()
    return RedirectResponse(url="/ui/shipments", status_code=303)
