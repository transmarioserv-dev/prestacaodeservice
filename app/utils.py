import re
import os
from datetime import date
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from . import models
import json
from pypdf import PdfReader
import pandas as pd

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

def update_vehicle_telemetry(db: Session, plate: str, file_date: date, **kwargs):
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
        for key, value in kwargs.items():
            if value is not None:
                if isinstance(value, (float, int)):
                    if key in ['theft_count', 'theft_volume', 'refueling_count', 'refueling_volume']:
                        setattr(existing, key, max(getattr(existing, key) or 0, value))
                    elif key == 'avg_speed':
                        existing.avg_speed = (existing.avg_speed + value) / 2 if existing.avg_speed else value
                    elif key == 'route_length':
                        existing.route_length = max(existing.route_length or 0, value)
                    elif key == 'fuel_consumption':
                        existing.fuel_consumption = max(existing.fuel_consumption or 0, value)
                    elif key == 'top_speed':
                        existing.top_speed = max(existing.top_speed or 0, value)
                    else:
                        setattr(existing, key, value)
                else:
                    if key == 'engine_hours' and value != "0s":
                        existing.engine_hours = value
                    else:
                        setattr(existing, key, value)
    else:
        new_telemetry = models.VehicleTelemetry(vehicle_id=vehicle.id, date=file_date, **kwargs)
        db.add(new_telemetry)
    db.commit()

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

        telemetry_data = {
            "route_length": 0.0,
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

        update_vehicle_telemetry(db, device_name, file_date, **telemetry_data)

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
        update_vehicle_telemetry(db, plate, file_date, route_length=float(km))

def ingest_consolidated_report(content, file_date, db: Session):
    sections = re.split(r'\d+\.\s+([A-Z0-9-]+)\s+\(', content)
    
    for i in range(1, len(sections), 2):
        plate = sections[i]
        data_block = sections[i+1]
        
        telemetry_data = {
            "route_length": 0.0,
            "fuel_consumption": 0.0,
            "refueling_count": 0,
            "refueling_volume": 0.0,
            "theft_count": 0,
            "theft_volume": 0.0,
            "fuel_efficiency": 0.0,
            "net_loss": 0.0
        }
        
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

        update_vehicle_telemetry(db, plate, file_date, **telemetry_data)

def ingest_pdf_report(file_path, file_date, db: Session):
    try:
        reader = PdfReader(file_path)
        content = ""
        for page in reader.pages:
            content += page.extract_text() + "\n"
        
        if "Report type: Fuel thefts" in content:
            return ingest_fuel_thefts_pdf(content, file_date, db)
        elif "Report type: Fuel fillings" in content:
            return ingest_fuel_fillings_pdf(content, file_date, db)
        elif "Report type: Travel sheet custom" in content:
            return ingest_travel_sheet_pdf(content, file_date, db)
    except Exception as e:
        print(f"Error parsing PDF {file_path}: {e}")
    return False

def ingest_fuel_fillings_pdf(content, file_date, db: Session):
    device_sections = re.split(r'Device:\s+', content)
    for section in device_sections[1:]:
        lines = section.split('\n')
        device_name = lines[0].strip()
        
        refill_count = 0
        total_refill_vol = 0.0
        
        # Match data lines like: 2026-06-11 08:22:40 17.86 L 173.81 L 191.67 L FUEL MAPUTO
        # Using a flexible regex for potential newlines from PDF extraction
        matches = re.finditer(r'(\d{4}-\d{2}-\d{2}[\s\n]+\d{2}:\d{2}:\d{2})[\s\n]+([\d.]+)[\s\n]+L[\s\n]+([\d.]+)[\s\n]+L', section)
        for m in matches:
            refill_count += 1
            total_refill_vol += float(m.group(3))
        
        if device_name:
            update_vehicle_telemetry(db, device_name, file_date, refueling_count=refill_count, refueling_volume=total_refill_vol)
    return True

def ingest_fuel_thefts_pdf(content, file_date, db: Session):
    # Split content by device
    device_sections = re.split(r'Device:\s+', content)
    for section in device_sections[1:]:
        lines = section.split('\n')
        device_name = lines[0].strip()
        
        theft_count = 0
        total_theft_vol = 0.0
        
        for line in lines[1:]:
            # Match data lines like: 2026-06-09 12:52:46 456.1 L 15.56 L 440.54 L FUEL QUELIMANE
            match = re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+[\d.]+\s+L\s+([\d.]+)\s+L', line)
            if match:
                theft_count += 1
                total_theft_vol += float(match.group(1))
        
        if device_name:
            update_vehicle_telemetry(db, device_name, file_date, theft_count=theft_count, theft_volume=total_theft_vol)
    return True

def ingest_travel_sheet_pdf(content, file_date, db: Session):
    device_sections = re.split(r'Device:\s+', content)
    for section in device_sections[1:]:
        lines = section.split('\n')
        device_name = lines[0].strip()
        
        # Summary lines usually at the end of section
        rl_match = re.search(r'Route length:\s+([\d.]+)\s+Km', section)
        fc_match = re.search(r'Fuel consumption \(FUEL \(DIESEL\)\):\s+([\d.]+)\s+L', section)
        
        telemetry_data = {}
        if rl_match:
            telemetry_data["route_length"] = float(rl_match.group(1))
        if fc_match:
            telemetry_data["fuel_consumption"] = float(fc_match.group(1))
            
        if device_name and telemetry_data:
            update_vehicle_telemetry(db, device_name, file_date, **telemetry_data)
    return True

def ingest_drivers_xlsx(file_path, db: Session):
    try:
        xl = pd.ExcelFile(file_path)
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet_name, header=1)
            # Expected columns: 'Nome Completo', 'Contacto', 'Matricula da viatura'
            if 'Nome Completo' not in df.columns:
                continue
                
            for _, row in df.iterrows():
                name = row.get('Nome Completo')
                if pd.isna(name) or not isinstance(name, str):
                    continue
                
                phone = str(int(row.get('Contacto'))) if not pd.isna(row.get('Contacto')) else None
                cnh = str(row.get('Número da carta de condução')) if 'Número da carta de condução' in df.columns and not pd.isna(row.get('Número da carta de condução')) else None
                plate = row.get('Matricula da viatura')
                
                # Find or create driver
                driver = db.query(models.Driver).filter(models.Driver.name == name).first()
                if not driver:
                    driver = models.Driver(
                        name=name,
                        phone=phone,
                        cnh=cnh,
                        assigned_plate=plate if not pd.isna(plate) else None
                    )
                    db.add(driver)
                    db.commit()
                    db.refresh(driver)
                else:
                    # Update info if changed
                    if phone: driver.phone = phone
                    if cnh: driver.cnh = cnh
                    if plate and not pd.isna(plate): driver.assigned_plate = plate
                    db.commit()
                
                # If there's a plate, ensure the vehicle exists
                if plate and not pd.isna(plate):
                    vehicle = db.query(models.Vehicle).filter(models.Vehicle.plate == plate).first()
                    if not vehicle:
                        vehicle = models.Vehicle(plate=plate, status="Disponível")
                        db.add(vehicle)
                        db.commit()
        return True
    except Exception as e:
        print(f"Error parsing XLSX {file_path}: {e}")
    return False

def process_report_file(file_path, db: Session):
    filename = os.path.basename(file_path)
    date_match = re.search(r'(\d{4})_(\d{2})_(\d{2})', filename)
    if date_match:
        file_date = date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
    else:
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
                elif "fuel_level_report" in filename:
                    # Even if we don't extract much, let's mark it as handled if it has panels
                    if soup.find('div', class_='panel panel-default'):
                        return True
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
    elif filename.endswith(".pdf"):
        return ingest_pdf_report(file_path, file_date, db)
    elif filename.endswith(".xlsx"):
        return ingest_drivers_xlsx(file_path, db)
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
