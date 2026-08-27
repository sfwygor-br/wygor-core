#!/usr/bin/env python3

import sys
import requests
import json
from datetime import datetime, timedelta

def fetch_telemetry_data(unit=None, minutes=30):
    try:
        url = "http://localhost:8000/telemetry"
        params = {"minutes": minutes}
        if unit:
            params["unit"] = unit
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching telemetry data: {e}", file=sys.stderr)
        return {}

def classify_errors(telemetry_data):
    try:
        url = "http://localhost:8000/classify"
        response = requests.post(url, json=telemetry_data)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error classifying errors: {e}", file=sys.stderr)
        return {}

def apply_auto_healing(classified_errors):
    # Placeholder for auto-healing logic
    for error in classified_errors.get("errors", []):
        if error["severity"] == "critical":
            print(f"Applying auto-healing to critical error: {error["signature"]}")
            # Implement actual healing actions here

def main():
    unit = sys.argv[1] if len(sys.argv) > 1 else None
    minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    
    telemetry_data = fetch_telemetry_data(unit, minutes)
    classified_errors = classify_errors(telemetry_data)
    apply_auto_healing(classified_errors)
    print(json.dumps(classified_errors, indent=4))

if __name__ == "__main__":
    main()
