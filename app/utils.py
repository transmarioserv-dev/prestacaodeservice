import re
import os
from datetime import date
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from . import models
import json

def parse_duration(duration_str):
    if not duration_str or duration_str == "0s":
        return "0s"
    return duration_str

def parse_float(val_str):
    if not val_str:
        return 0.0
    val = re.sub(r'[^\d.]', '', val_str.replace(',', '.'))
    try:
        return float(val) if val else 0.0
    except ValueError:
        return 0.0

def ingest_general_info(soup, file_date, db: Session):
    panels = soup.find_all('div', class_='panel panel-default')
    for panel in panels:
        heading = panel.find('div', class_='panel-heading')
        if not heading or "General information" not in heading.text:
            continue
        
        device_table = panel.find('table', class_='table')
        if not device_table:
            continue
        
        device_name = ""
        tds = device_table.find_all('td')
        for td in tds:
            if td.text.strip():
                device_name = td.text.strip()
                break
        
        if not device_name:
            continue

        vehicle = db.query(models.Vehicle).filter(models.Vehicle.plate == device_name).first()
        if not vehicle:
            vehicle = models.Vehicle(plate=device_name, status="Disponível")
            db.add(vehicle)
            db.commit()
            db.refresh(vehicle)

        telemetry_data = {
            "vehicle_id": vehicle.id,
            "date": file_date,
            "route_length": 0.0,
            "move_duration": "0s",
            "stop_duration": "0s",
            "top_speed": 0.0,
            "avg_speed": 0.0,
            "fuel_consumption": 0.0,
            "engine_hours": "0s"
        }

        tables = panel.find_all('table', class_='table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    label = th.text.strip()
                    value = td.text.strip()
                    if "Route length" in label:
                        telemetry_data["route_length"] = parse_float(value)
                    elif "Top speed" in label:
                        telemetry_data["top_speed"] = parse_float(value)
                    elif "Average speed" in label:
                        telemetry_data["avg_speed"] = parse_float(value)
                    elif "Fuel consumption" in label:
                        telemetry_data["fuel_consumption"] += parse_float(value)
                    elif "Engine hours" in label:
                        telemetry_data["engine_hours"] = parse_duration(value)

        existing = db.query(models.VehicleTelemetry).filter(
            models.VehicleTelemetry.vehicle_id == vehicle.id,
            models.VehicleTelemetry.date == file_date
        ).first()

        if existing:
            existing.route_length = max(existing.route_length or 0, telemetry_data["route_length"])
            existing.top_speed = max(existing.top_speed or 0, telemetry_data["top_speed"])
            existing.avg_speed = (existing.avg_speed or 0 + telemetry_data["avg_speed"]) / 2 if existing.avg_speed else telemetry_data["avg_speed"]
            existing.fuel_consumption = max(existing.fuel_consumption or 0, telemetry_data["fuel_consumption"])
            existing.engine_hours = telemetry_data["engine_hours"] if telemetry_data["engine_hours"] != "0s" else existing.engine_hours
        else:
            new_telemetry = models.VehicleTelemetry(
                vehicle_id=vehicle.id,
                date=file_date,
                route_length=telemetry_data["route_length"],
                top_speed=telemetry_data["top_speed"],
                avg_speed=telemetry_data["avg_speed"],
                fuel_consumption=telemetry_data["fuel_consumption"],
                engine_hours=telemetry_data["engine_hours"]
            )
            db.add(new_telemetry)
        db.commit()

def ingest_odometer_report(soup, file_date, db: Session):
    script = soup.find('script', string=re.compile('const vehicles ='))
    if not script:
        return
    
    match = re.search(r'const vehicles = (\[.*?\]);', script.string, re.DOTALL)
    if not match:
        return
    
    vehicles_raw = match.group(1)
    items = re.findall(r"\{name:'([^']+)',\s*km:([\d.]+)\}", vehicles_raw)
    
    for plate, km in items:
        vehicle = db.query(models.Vehicle).filter(models.Vehicle.plate == plate).first()
        if not vehicle:
            vehicle = models.Vehicle(plate=plate, status="Disponível")
            db.add(vehicle)
            db.commit()
            db.refresh(vehicle)
        
        existing = db.query(models.VehicleTelemetry).filter(
            models.VehicleTelemetry.vehicle_id == vehicle.id,
            models.VehicleTelemetry.date == file_date
        ).first()

        if existing:
            existing.route_length = max(existing.route_length or 0, float(km))
        else:
            new_telemetry = models.VehicleTelemetry(
                vehicle_id=vehicle.id,
                date=file_date,
                route_length=float(km)
            )
            db.add(new_telemetry)
        db.commit()

def ingest_consolidated_report(content, file_date, db: Session):
    # Regex to find each vehicle section
    sections = re.split(r'\d+\.\s+([A-Z0-9-]+)\s+\(', content)
    
    # The first element is before any vehicle section
    for i in range(1, len(sections), 2):
        plate = sections[i]
        data_block = sections[i+1]
        
        vehicle = db.query(models.Vehicle).filter(models.Vehicle.plate == plate).first()
        if not vehicle:
            vehicle = models.Vehicle(plate=plate, status="Disponível")
            db.add(vehicle)
            db.commit()
            db.refresh(vehicle)
        
        telemetry_data = {
            "vehicle_id": vehicle.id,
            "date": file_date,
            "route_length": 0.0,
            "fuel_consumption": 0.0,
            "refueling_count": 0,
            "refueling_volume": 0.0,
            "theft_count": 0,
            "theft_volume": 0.0,
            "fuel_efficiency": 0.0,
            "net_loss": 0.0
        }
        
        # Extract values using regex
        dist_match = re.search(r'Distância percorrida\s+([\d,.]+)\s+km', data_block)
        if dist_match:
            telemetry_data["route_length"] = parse_float(dist_match.group(1))
            
        cons_match = re.search(r'Consumo declarado\s+([\d,.]+)\s+L', data_block)
        if cons_match:
            telemetry_data["fuel_consumption"] = parse_float(cons_match.group(1))
            
        abast_match = re.search(r'Abastecimentos\s+(\d+)\s+\(([\d,.]+)\s+L\)', data_block)
        if abast_match:
            telemetry_data["refueling_count"] = int(abast_match.group(1))
            telemetry_data["refueling_volume"] = parse_float(abast_match.group(2))
        elif re.search(r'Abastecimentos\s+0', data_block):
            telemetry_data["refueling_count"] = 0
            telemetry_data["refueling_volume"] = 0.0
            
        furtos_match = re.search(r'Furtos\s+(\d+)\s+eventos\s+\(total\s+([-]?[\d,.]+)\s+L\)', data_block)
        if furtos_match:
            telemetry_data["theft_count"] = int(furtos_match.group(1))
            telemetry_data["theft_volume"] = abs(parse_float(furtos_match.group(2)))
        else:
            # Try another format: Furtos 1 (-15,65 L)
            furtos_match_alt = re.search(r'Furtos\s+(\d+)\s+\(([-]?[\d,.]+)\s+L\)', data_block)
            if furtos_match_alt:
                telemetry_data["theft_count"] = int(furtos_match_alt.group(1))
                telemetry_data["theft_volume"] = abs(parse_float(furtos_match_alt.group(2)))
        
        eff_match = re.search(r'Eficiência operacional\s+([\d,.]+)\s+km/L', data_block)
        if eff_match:
            telemetry_data["fuel_efficiency"] = parse_float(eff_match.group(1))
            
        loss_match = re.search(r'Perda líquida\s+([-]?[\d,.]+)\s+L', data_block)
        if loss_match:
            telemetry_data["net_loss"] = parse_float(loss_match.group(1))

        # Update or create telemetry record
        existing = db.query(models.VehicleTelemetry).filter(
            models.VehicleTelemetry.vehicle_id == vehicle.id,
            models.VehicleTelemetry.date == file_date
        ).first()

        if existing:
            existing.route_length = max(existing.route_length or 0, telemetry_data["route_length"])
            existing.fuel_consumption = max(existing.fuel_consumption or 0, telemetry_data["fuel_consumption"])
            existing.refueling_count = telemetry_data["refueling_count"]
            existing.refueling_volume = telemetry_data["refueling_volume"]
            existing.theft_count = telemetry_data["theft_count"]
            existing.theft_volume = telemetry_data["theft_volume"]
            existing.fuel_efficiency = telemetry_data["fuel_efficiency"]
            existing.net_loss = telemetry_data["net_loss"]
        else:
            new_telemetry = models.VehicleTelemetry(**telemetry_data)
            db.add(new_telemetry)
        db.commit()

def process_report_file(file_path, db: Session):
    filename = os.path.basename(file_path)
    date_match = re.search(r'(\d{4})_(\d{2})_(\d{2})', filename)
    if date_match:
        file_date = date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
    else:
        # Check if "dia 9" or "dia 7" is in path
        if "dia 9" in file_path:
            file_date = date(2026, 6, 9)
        elif "dia 7" in file_path:
            file_date = date(2026, 6, 7)
        else:
            file_date = date.today()

    if filename.endswith(".html"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'lxml')
                if "general_information_report" in filename:
                    ingest_general_info(soup, file_date, db)
                    return True
                elif "odometer_daily_report" in filename:
                    ingest_odometer_report(soup, file_date, db)
                    return True
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
    elif filename.endswith(".txt"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "RELATÓRIO CONSOLIDADO" in content or "DASHBOARD OPERACIONAL" in content:
                    ingest_consolidated_report(content, file_date, db)
                    return True
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
    return False
