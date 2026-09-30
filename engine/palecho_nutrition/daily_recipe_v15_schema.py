"""Offline schema validation of the API 1.5 boundary."""
import json
from pathlib import Path
from .freshfood_schema import validate_model
SCHEMA=json.loads(Path(__file__).with_name('freshfood_api_v15.schema.json').read_text())
def validate_daily_model(name,value):return validate_model(name,value,schema=SCHEMA)
