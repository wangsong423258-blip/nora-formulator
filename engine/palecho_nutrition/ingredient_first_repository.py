"""Versioned, offline exact-identity food records; unknown is never zero."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from .freshfood_contract import require
from .practical import digest
from .energy_methods import calculate_me
from .recipe_me import predict,INPUTS as ME_INPUTS,METHOD

CATEGORIES = {
    'ANIMAL_MEAT':'肉类', 'FISH':'鱼类', 'OTHER_SEAFOOD':'其他水产',
    'EGG':'蛋类', 'ORGAN':'内脏', 'ENERGY_SOURCE':'主食/能量来源',
    'FIBER_VEGETABLE':'蔬菜/膳食纤维', 'PLANT_ASSIST':'豆类/植物辅助',
    'FAT_OIL':'油脂', 'OPTIONAL_OTHER':'其他辅助食材',
}
ANIMAL = {'ANIMAL_MEAT','FISH','OTHER_SEAFOOD','EGG','ORGAN'}
CORE_ANIMAL = {'ANIMAL_MEAT','FISH','OTHER_SEAFOOD'}
CRITICAL = {'energy','protein','fat','carbohydrate','water','calcium','phosphorus','sodium','potassium','magnesium'}

def record_hash(row):
    return hashlib.sha256(json.dumps({k:v for k,v in row.items() if k!='record_sha256'},
        sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

class IngredientRepository:
    def __init__(self):
        base=Path(__file__).parent
        manifest=json.loads((base/'ingredient_first_manifest.json').read_text())
        docs={}
        for name in ['ingredient_first_foods.json','ingredient_first_registry.json']:
            data=(base/name).read_bytes()
            require(hashlib.sha256(data).hexdigest()==manifest['files'][name],'INGREDIENT_FIRST_DATA_INTEGRITY',name)
            docs[name]=json.loads(data)
        self.document=docs['ingredient_first_foods.json']
        self.registry=docs['ingredient_first_registry.json']
        self.records={r['ingredient_id']:r for r in self.document['records']}
        require(len(self.records)==len(self.document['records']),'DUPLICATE_INGREDIENT_RECORD')
        self.data_hash=digest(docs)

    @property
    def policy(self):return self.registry['engineering_policy']

    def provenance_errors(self,food):
        errors=[]
        if record_hash(food)!=food.get('record_sha256'):errors.append('INGREDIENT_RECORD_HASH_MISMATCH')
        sid=food.get('authoritative_source_id');source=self.registry['sources'].get(sid)
        if not source or source['version']!=food.get('source_version') or source.get('sha256')!=food.get('archive_sha256'):
            errors.append('SOURCE_RECORD_MISMATCH')
        for n,v in food['nutrients_per_100g'].items():
            p=food['nutrient_provenance'].get(n)
            if v is None:continue
            if type(v) not in (float,int) or not math.isfinite(v) or v<0:errors.append('INVALID_NUTRIENT:'+n)
            if not p or any([p['source_id']!=sid,p['fdc_id']!=food['fdc_id'],p['food_state']!=food['food_state'],p['source_amount']!=v,
                             p['source_unit'].lower()!=food['nutrient_units'][n],not p['food_nutrient_id']]):
                errors.append('NUTRIENT_PROVENANCE_MISMATCH:'+n)
        actual=sorted(n for n,v in food['nutrients_per_100g'].items() if v is None)
        energy=food['nutrients_per_100g'].get('energy')
        if energy is not None and energy<=0:errors.append('NONPOSITIVE_ENERGY_REFERENCE')
        if actual!=food['missing_nutrients']:errors.append('MISSING_NUTRIENTS_MISMATCH')
        return errors

    def critical_missing(self,food):
        needed=CRITICAL | set(ME_INPUTS)
        if food['category']=='ORGAN':needed|={'retinol','copper'}
        return sorted(n for n in needed if food['nutrients_per_100g'].get(n) is None)

    def energy(self,food,species):
        calculation=predict(species,food['nutrients_per_100g'])
        me=calculation['value']
        return {'value_per_100g':me,
          'basis':METHOD if me is not None else 'PET_ME_UNAVAILABLE',
          'formula_source':'NRC2006_TDF_CALVEZ2019','formula_version':calculation['version'],
          'species':species,'applicable_food_type':calculation['applicability'],
          'prediction_scope':'SINGLE_FOOD_STARTING_COEFFICIENT_REPLACED_BY_FINAL_MIXTURE_CONTRIBUTION',
          'assumptions':calculation['assumptions'],
          'pet_me_prediction':calculation,'pet_me_kcal_per_100g':me,
          'formula_alternatives':['FEDIAF_2025_NRC_PREPARED','AAFCO_MODIFIED_ATWATER'],
          'energy_source':deepcopy(food['energy_source'])}

    def public(self,food):
        return deepcopy(food)
