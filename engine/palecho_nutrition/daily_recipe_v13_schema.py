"""Offline validation for the recommended FreshFood 1.3 contract."""
import json
from pathlib import Path
from .freshfood_schema import validate_model

SCHEMA = json.loads(Path(__file__).with_name('freshfood_api_v13.schema.json').read_text())


def validate_daily_model(name, value):
    return validate_model(name, value, schema=SCHEMA)
