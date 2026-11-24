import asyncio
import csv
from datetime import datetime, timezone
from decimal import Decimal
import os
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to sys.path so app imports work
API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import async_session_factory, async_engine
from app.models.patient import Patient, PatientLab


SYNTHEA_CSV_DIR = Path(r"E:\Projects\synthea\output\csv")


async def run_ingestion():
    patients_file = SYNTHEA_CSV_DIR / "patients.csv"
    observations_file = SYNTHEA_CSV_DIR / "observations.csv"

    if not patients_file.exists() or not observations_file.exists():
        print(f"Error: Required CSV files not found in {SYNTHEA_CSV_DIR}")
        sys.exit(1)

    print("=" * 60)
    print("STARTING SYNTHEA PATIENT & RENAL LABS INGESTION")
    print("=" * 60)

    # 1. Parse Anthropometrics & Renal Labs from observations.csv
    print(f"\n[1/3] Parsing observations from {observations_file.name}...")
    weights = {}  # pid -> {'date': str, 'weight_kg': Decimal}
    heights = {}  # pid -> {'date': str, 'height_cm': Decimal}
    panels = defaultdict(dict)  # (pid, date_str) -> {'scr': Decimal, 'egfr': Decimal}

    scr_codes = {"38483-4", "2160-0"}
    egfr_codes = {"33914-3"}
    weight_code = "29463-7"
    height_code = "8302-2"

    with open(observations_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["PATIENT"]
            code = row["CODE"]
            date = row["DATE"]
            val = row["VALUE"]

            if code == weight_code:
                try:
                    w = round(Decimal(val), 2)
                    if pid not in weights or date > weights[pid]["date"]:
                        weights[pid] = {"date": date, "weight_kg": w}
                except Exception:
                    pass

            elif code == height_code:
                try:
                    h = round(Decimal(val), 2)
                    if pid not in heights or date > heights[pid]["date"]:
                        heights[pid] = {"date": date, "height_cm": h}
                except Exception:
                    pass

            elif code in scr_codes:
                try:
                    scr = round(Decimal(val), 2)
                    key = (pid, date)
                    panels[key]["scr"] = scr
                except Exception:
                    pass

            elif code in egfr_codes:
                try:
                    egfr = round(Decimal(val), 1)
                    key = (pid, date)
                    panels[key]["egfr"] = egfr
                except Exception:
                    pass

    print(f"  -> Extracted weights for {len(weights)} patients")
    print(f"  -> Extracted heights for {len(heights)} patients")
    print(f"  -> Extracted {len(panels)} distinct renal lab draws")

    # 2. Parse demographics from patients.csv
    print(f"\n[2/3] Parsing patients from {patients_file.name}...")
    patient_records = []
    synthea_pids = set()

    with open(patients_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            pid = row["Id"]
            synthea_pids.add(pid)
            bdate = datetime.strptime(row["BIRTHDATE"], "%Y-%m-%d")
            ddate = datetime.strptime(row["DEATHDATE"], "%Y-%m-%d") if row["DEATHDATE"] else datetime.now()
            age_years = max(0, (ddate - bdate).days // 365)

            name = f"{row['FIRST']} {row['LAST']}".strip()
            sex = "Male" if row["GENDER"] == "M" else "Female"

            wt = weights.get(pid, {}).get("weight_kg", Decimal("70.00"))
            ht = heights.get(pid, {}).get("height_cm", Decimal("170.00"))

            patient_records.append({
                "patient_id": pid,
                "generic_patient_id": f"PAT-{idx + 1:03d}",
                "name": name,
                "age_years": age_years,
                "biological_sex": sex,
                "actual_weight_kg": wt,
                "height_cm": ht,
            })

    print(f"  -> Prepared {len(patient_records)} patient records")

    # 3. Insert into Database
    print(f"\n[3/3] Inserting into PostgreSQL Database via Async Session...")
    async with async_session_factory() as session:
        # Upsert Patients
        for p in patient_records:
            stmt = (
                pg_insert(Patient)
                .values(**p)
                .on_conflict_do_update(
                    index_elements=["patient_id"],
                    set_={
                        "generic_patient_id": p["generic_patient_id"],
                        "name": p["name"],
                        "age_years": p["age_years"],
                        "biological_sex": p["biological_sex"],
                        "actual_weight_kg": p["actual_weight_kg"],
                        "height_cm": p["height_cm"],
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
            )
            await session.execute(stmt)

        await session.commit()
        print(f"  -> Successfully upserted {len(patient_records)} patients.")

        # Clean existing labs for these Synthea patients to ensure idempotency
        await session.execute(
            delete(PatientLab).where(PatientLab.patient_id.in_(synthea_pids))
        )
        await session.commit()

        # Insert Patient Labs
        lab_objects = []
        for (pid, date_str), lab in panels.items():
            if pid not in synthea_pids:
                continue

            collected_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            lab_objects.append(
                PatientLab(
                    patient_id=pid,
                    serum_creatinine_mg_dl=lab.get("scr"),
                    egfr_ml_min_1_73m2=lab.get("egfr"),
                    collected_at=collected_at,
                )
            )

        session.add_all(lab_objects)
        await session.commit()
        print(f"  -> Successfully inserted {len(lab_objects)} renal lab panel records.")

    await async_engine.dispose()

    print("\n" + "=" * 60)
    print("SYNTHEA INGESTION COMPLETE!")
    print(f"Total Patients Loaded: {len(patient_records)}")
    print(f"Total Lab Panels Loaded: {len(lab_objects)}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_ingestion())
