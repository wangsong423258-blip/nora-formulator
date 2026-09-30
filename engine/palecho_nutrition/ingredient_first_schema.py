"""Versioned structural and semantic output contract."""
import json
import math
from pathlib import Path
from .freshfood_schema import validate_model
from .freshfood_contract import require

SCHEMA=json.loads(Path(__file__).with_name('freshfood_api_v19.schema.json').read_text())

def validate_result(result):
    from .ingredient_first import READY
    validate_model('IngredientFirstQuickMealResult',result,schema=SCHEMA)
    if result['status'] in READY:
        selected=result['selected_ingredient_set']['ingredient_ids']
        actual=[c['ingredient_id'] for c in result['recipe_components']]
        # Revalidate persisted results against the current catalog. A historical
        # snapshot must not reactivate a food removed from production.
        from .ingredient_first_repository import IngredientRepository
        repository=IngredientRepository();active=repository.records
        require(all(i in active for i in actual+selected),'UNKNOWN_INGREDIENT_ID')
        require(result['calculation_metadata'].get('ingredient_data_hash')==repository.data_hash,
                'STALE_RECIPE_RECALCULATION_REQUIRED')
        require(sorted(actual)==sorted(selected),'USER_SELECTED_INGREDIENT_MISSING')
        require('FAIL' not in result['scientific_checks'].values() and result['scientific_audit']['status']!='FAIL','SCIENTIFIC_AUDIT_FAILED')
        require(result['cooking_plan'] is not None,'COOKING_PLAN_REQUIRED')
        # The lightweight offline schema validator does not implement if/then.
        # Enforce the success-only energy contract here as well as in JSON Schema.
        for key in ['dog_me','cat_me','recipe_pet_me_kcal']:
            v=result.get(key)
            require(type(v) in (int,float) and math.isfinite(v) and v>0,'ME_RESULT_INVALID',key)
        for key in ['dog_me','cat_me']:
            require(abs(result[key]-math.fsum(c[key] for c in result['recipe_components']))<1e-6,'ME_SUM_MISMATCH',key)
        species=result['calculation_metadata']['model']['species']
        require(abs(result['recipe_pet_me_kcal']-result[species.lower()+'_me'])<1e-6 and
                abs(result['recipe_energy']-result['recipe_pet_me_kcal'])<1e-6,'ME_SPECIES_MISMATCH')
        require(isinstance(result.get('energy_validation'),dict) and result['energy_validation'].get('status')=='PASS','ME_ENERGY_RANGE_INVALID')
    else:
        require(result['recipe_components']==[] and result['cooking_plan'] is None,'FAILED_AUDIT_RECIPE_RELEASE')
    return True
