import httpx
import json

payload = {
    "patient_name": "Test Name",
    "age": 21,
    "sex": "male",
    "village": "Test Village",
    "district": "Test District",
    "chief_complaint": "Chest pain",
    "vulnerability_flags": {
        "pregnant": False,
        "postpartum": False,
        "immunocompromised": False,
        "chronic_lung_disease": False,
        "cardiovascular_disease": False,
        "diabetic": False,
        "malnutrition": False
    },
    "vitals": {
        "systolic_bp": 340,
        "diastolic_bp": 90,
        "heart_rate": 140,
        "respiratory_rate": 20,
        "spo2": 97,
        "temperature": 39.0,
        "blood_glucose_mgdl": 100,
        "weight_kg": 70,
        "gcs_score": 15
    },
    "medications": [],
    "symptoms": []
}

# The route requires PHW token, but we can generate one using app.core.security
from app.core.security import create_access_token
token = create_access_token("test_num", "phw", {"user_id": "00000000-0000-0000-0000-000000000000"})

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        resp = await client.post('http://localhost:8000/api/v1/analyze/risk', json=payload, headers=headers)
        print("Status", resp.status_code)
        import pprint
        pprint.pprint(resp.json())

asyncio.run(main())
