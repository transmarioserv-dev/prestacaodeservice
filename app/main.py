from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from . import models, schemas, database
from .database import engine, get_db
from datetime import date

# Create tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Mario Transport Service API")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    vehicles_count = db.query(models.Vehicle).count()
    drivers_count = db.query(models.Driver).count()
    shipments_count = db.query(models.Shipment).filter(models.Shipment.status != "Entregue").count()
    latest_shipments = db.query(models.Shipment).order_by(models.Shipment.id.desc()).limit(5).all()
    
    context = {
        "request": request,
        "vehicles_count": vehicles_count,
        "drivers_count": drivers_count,
        "shipments_count": shipments_count,
        "latest_shipments": latest_shipments
    }
    return templates.TemplateResponse(request=request, name="index.html", context=context)

# --- UI ROUTES ---

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
    vehicles = db.query(models.Vehicle).filter(models.Vehicle.status == "Disponível").all()
    drivers = db.query(models.Driver).all()
    return templates.TemplateResponse(
        request=request, name="shipments.html", context={
            "request": request, "shipments": shipments, 
            "vehicles": vehicles, "drivers": drivers
        }
    )

@app.post("/ui/shipments")
def ui_create_shipment(
    tracking_code: str = Form(...), description: str = Form(...), weight: float = Form(...),
    origin: str = Form(...), destination: str = Form(...), shipping_value: float = Form(...),
    status: str = Form(...), vehicle_id: int = Form(None), driver_id: int = Form(None),
    db: Session = Depends(get_db)
):
    db_shipment = models.Shipment(
        tracking_code=tracking_code, description=description, weight=weight,
        origin=origin, destination=destination, shipping_value=shipping_value,
        status=status, vehicle_id=vehicle_id, driver_id=driver_id
    )
    db.add(db_shipment)
    db.commit()
    return RedirectResponse(url="/ui/shipments", status_code=303)

# --- API Endpoints ---
@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# Vehicles
@app.post("/vehicles/", response_model=schemas.Vehicle)
def create_vehicle(vehicle: schemas.VehicleCreate, db: Session = Depends(get_db)):
    db_vehicle = models.Vehicle(**vehicle.model_dump())
    db.add(db_vehicle)
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle

@app.get("/vehicles/", response_model=list[schemas.Vehicle])
def read_vehicles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    vehicles = db.query(models.Vehicle).offset(skip).limit(limit).all()
    return vehicles

# Drivers
@app.post("/drivers/", response_model=schemas.Driver)
def create_driver(driver: schemas.DriverCreate, db: Session = Depends(get_db)):
    db_driver = models.Driver(**driver.model_dump())
    db.add(db_driver)
    db.commit()
    db.refresh(db_driver)
    return db_driver

@app.get("/drivers/", response_model=list[schemas.Driver])
def read_drivers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    drivers = db.query(models.Driver).offset(skip).limit(limit).all()
    return drivers

# Shipments
@app.post("/shipments/", response_model=schemas.Shipment)
def create_shipment(shipment: schemas.ShipmentCreate, db: Session = Depends(get_db)):
    db_shipment = models.Shipment(**shipment.model_dump())
    db.add(db_shipment)
    db.commit()
    db.refresh(db_shipment)
    return db_shipment

@app.get("/shipments/", response_model=list[schemas.Shipment])
def read_shipments(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    shipments = db.query(models.Shipment).offset(skip).limit(limit).all()
    return shipments
