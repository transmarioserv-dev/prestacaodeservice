from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Enum, DateTime
from sqlalchemy.orm import relationship
from .database import Base
import enum
from datetime import datetime

class VehicleType(enum.Enum):
    CAMINHAO = "Caminhão"
    VAN = "Van"
    MOTO = "Moto"

class VehicleStatus(enum.Enum):
    DISPONIVEL = "Disponível"
    MANUTENCAO = "Em Manutenção"
    EM_USO = "Em Uso"

class ShipmentStatus(enum.Enum):
    PENDENTE = "Pendente"
    TRANSITO = "Em Trânsito"
    ENTREGUE = "Entregue"
    CANCELADO = "Cancelado"

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    plate = Column(String, unique=True, index=True, nullable=False)
    model = Column(String)
    brand = Column(String)
    year = Column(Integer)
    capacity = Column(Float)
    type = Column(String) # Usando string para simplificar nos forms
    status = Column(String, default="Disponível")

    shipments = relationship("Shipment", back_populates="vehicle")
    telemetry = relationship("VehicleTelemetry", back_populates="vehicle", cascade="all, delete-orphan")

class Driver(Base):
    __tablename__ = "drivers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    cpf = Column(String, unique=True, index=True, nullable=False)
    cnh = Column(String, unique=True, index=True, nullable=False)
    category = Column(String)
    phone = Column(String)
    hire_date = Column(Date)

    shipments = relationship("Shipment", back_populates="driver")

class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    tracking_code = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)
    weight = Column(Float)
    origin = Column(String)
    destination = Column(String)
    shipping_value = Column(Float)
    status = Column(String, default="Pendente")
    shipment_date = Column(Date, default=datetime.utcnow)

    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    driver_id = Column(Integer, ForeignKey("drivers.id"))

    vehicle = relationship("Vehicle", back_populates="shipments")
    driver = relationship("Driver", back_populates="shipments")
    history = relationship("ShipmentHistory", back_populates="shipment", cascade="all, delete-orphan")

class ShipmentHistory(Base):
    __tablename__ = "shipment_history"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"))
    status = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    notes = Column(String)

    shipment = relationship("Shipment", back_populates="history")

class VehicleTelemetry(Base):
    __tablename__ = "vehicle_telemetry"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    date = Column(Date, nullable=False)
    
    route_length = Column(Float) # Km
    top_speed = Column(Float) # kph
    avg_speed = Column(Float) # kph
    fuel_consumption = Column(Float) # L
    engine_hours = Column(String) # Duration string
    odometer = Column(Float) # KM

    refueling_count = Column(Integer, default=0)
    refueling_volume = Column(Float, default=0.0)
    theft_count = Column(Integer, default=0)
    theft_volume = Column(Float, default=0.0)
    fuel_efficiency = Column(Float) # km/L
    net_loss = Column(Float, default=0.0)

    vehicle = relationship("Vehicle", back_populates="telemetry")
