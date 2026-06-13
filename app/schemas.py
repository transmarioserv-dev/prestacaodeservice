from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

# Shipment History Schemas
class ShipmentHistoryBase(BaseModel):
    status: str
    timestamp: datetime
    notes: Optional[str] = None

class ShipmentHistory(ShipmentHistoryBase):
    id: int
    shipment_id: int

    class Config:
        from_attributes = True

# Vehicle Schemas
class VehicleBase(BaseModel):
    plate: str
    model: str
    brand: str
    year: int
    capacity: float
    type: str
    status: str = "Disponível"

class VehicleCreate(VehicleBase):
    pass

class Vehicle(VehicleBase):
    id: int

    class Config:
        from_attributes = True

# Driver Schemas
class DriverBase(BaseModel):
    name: str
    cnh: str
    category: str
    phone: str
    hire_date: date
    assigned_plate: Optional[str] = None

class DriverCreate(DriverBase):
    pass

class Driver(DriverBase):
    id: int

    class Config:
        from_attributes = True

# Shipment Schemas
class ShipmentBase(BaseModel):
    tracking_code: str
    description: Optional[str] = None
    weight: float
    origin: str
    destination: str
    shipping_value: float
    status: str = "Pendente"
    shipment_date: date
    vehicle_id: Optional[int] = None
    driver_id: Optional[int] = None

class ShipmentCreate(ShipmentBase):
    pass

class Shipment(ShipmentBase):
    id: int
    history: List[ShipmentHistory] = []

    class Config:
        from_attributes = True

# Telemetry Schemas
class VehicleTelemetryBase(BaseModel):
    date: date
    route_length: Optional[float] = 0.0
    top_speed: Optional[float] = 0.0
    avg_speed: Optional[float] = 0.0
    fuel_consumption: Optional[float] = 0.0
    engine_hours: Optional[str] = "0s"
    odometer: Optional[float] = 0.0
    refueling_count: Optional[int] = 0
    refueling_volume: Optional[float] = 0.0
    theft_count: Optional[int] = 0
    theft_volume: Optional[float] = 0.0
    fuel_efficiency: Optional[float] = 0.0
    net_loss: Optional[float] = 0.0

class VehicleTelemetryCreate(VehicleTelemetryBase):
    vehicle_id: int

class VehicleTelemetry(VehicleTelemetryBase):
    id: int
    vehicle_id: int

    class Config:
        from_attributes = True
