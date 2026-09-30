"""Offline 1.1 contract validation; no schema resolver or network access."""
import json
from pathlib import Path
from .freshfood_schema import validate_model
SCHEMA=json.loads(Path(__file__).with_name('freshfood_api_v11.schema.json').read_text())
def validate_design_model(name,value):return validate_model(name,value,schema=SCHEMA)
