from pydantic import BaseModel
from typing import Optional, List
from datetime import date

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
    cpf: str
    cnh: str
    category: str
    phone: str
    hire_date: date

class DriverCreate(DriverBase):
    pass

class Driver(DriverBase):
    id: int

    class Config:
        from_attributes = True

# Shipment Schemas
class ShipmentBase(BaseModel):
    tracking_code: str
    description: str
    weight: float
    origin: str
    destination: str
    shipping_value: float
    status: str = "Pendente"
    vehicle_id: Optional[int] = None
    driver_id: Optional[int] = None

class ShipmentCreate(ShipmentBase):
    pass

class Shipment(ShipmentBase):
    id: int

    class Config:
        from_attributes = True
