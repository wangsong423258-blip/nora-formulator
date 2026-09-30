"""FreshFood 1.0 public identifiers, structured diagnostics and profile adapter.

Display text never participates in routing. The legacy engine is an internal
adapter; its field names are not exposed as the new public request contract.
"""
from copy import deepcopy
from datetime import date
import math,re
from .profile import lifecycle
from .practical import normalize_pet
from .practical_disease import ACUTE_FLAGS

API_VERSION='1.0'
ENGINE_VERSION='freshfood-1.0.0'
RECIPE_STATUSES=('RECOMMENDED','RECOMMENDED_WITH_SUPPLEMENTS','LIMITED_DATA','PROFESSIONAL_REVIEW','BLOCKED')
GOALS={'FULL_DAILY_DIET':'COMPLETE_DIET','PARTIAL_DIET':'SUPPLEMENTAL','OCCASIONAL_MEAL':'TOPPER'}
SYMPTOMS={'PERSISTENT_VOMITING':'PERSISTENT_SEVERE_VOMITING','UNABLE_TO_EAT':'UNABLE_TO_EAT','URINARY_OBSTRUCTION_RISK':'UNABLE_TO_URINATE','SEVERE_DIARRHEA_DEHYDRATION':'DEHYDRATION','ACUTE_SEVERE_CONDITION':'ACUTE_SEVERE_ILLNESS'}
BLOCK_CODES={v:k for k,v in SYMPTOMS.items()}
PROFILE_FIELDS={'profile_id','species','breed_id','breed_name','birth_date','as_of_date','age_years','age_months','life_stage','sex','neutered','weight_kg','body_condition','muscle_condition','weight_trend','activity_level','diseases','recent_symptoms','current_diet_type','extra_foods','food_restrictions','disliked_foods','feeding_goal','expected_adult_weight_kg','growth_complete','weaned','available_ingredient_ids','daily_label_servings','medications'}

def error(code,field=None,message=None,action='CORRECT_INPUT',recoverable=True):
 return {'code':code,'message':message or '请核对输入或按返回原因补充信息。','field':field,'severity':'ERROR','recoverable':recoverable,'suggested_action':action}
def warning(code,message,field=None):return {'code':code,'message':message,'severity':'WARNING','related_field':field}
class ContractError(ValueError):
 def __init__(self,code,field=None,message=None,action='CORRECT_INPUT'):
  self.detail=error(code,field,message,action);super().__init__(code)
def require(ok,code,field=None,message=None):
 if not ok:raise ContractError(code,field,message)
def numeric(v):return type(v) in (int,float) and math.isfinite(v)
def business_id(v):return isinstance(v,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,79}',v) is not None

class PetNutritionProfileValidator:
 def __init__(self,store):self.store=store
 def validate(self,raw):
  warnings=[]
  try:
   require(isinstance(raw,dict),'PROFILE_OBJECT_REQUIRED')
   require(set(raw)<=PROFILE_FIELDS,'UNKNOWN_PROFILE_FIELD',next(iter(set(raw)-PROFILE_FIELDS),None))
   p=deepcopy(raw);require(business_id(p.get('profile_id')),'PROFILE_ID_INVALID','profile_id')
   sp=p.get('species');require(sp in {'DOG','CAT'},'SPECIES_REQUIRED','species')
   require(numeric(p.get('weight_kg')) and p['weight_kg']>0,'WEIGHT_INVALID','weight_kg')
   defaults={'breed_id':'UNKNOWN','breed_name':None,'birth_date':None,'age_years':None,'age_months':None,'life_stage':None,'sex':'UNKNOWN','neutered':None,'body_condition':None,'muscle_condition':'NORMAL','weight_trend':'STABLE','activity_level':'LOW','diseases':[],'recent_symptoms':[],'current_diet_type':'UNKNOWN','extra_foods':[],'food_restrictions':[],'disliked_foods':[],'feeding_goal':'FULL_DAILY_DIET'}
   for k,v in defaults.items():
    if k not in p:p[k]=deepcopy(v)
   require(p['breed_id'] is None or business_id(p['breed_id']),'BREED_ID_INVALID','breed_id')
   if not p['breed_id'] or p['breed_id']=='UNKNOWN':p['breed_id']='UNKNOWN';warnings.append(warning('BREED_UNKNOWN_ALLOWED','品种未知，可继续。','breed_id'))
   require(p['breed_name'] is None or isinstance(p['breed_name'],str),'BREED_NAME_INVALID','breed_name')
   require(p['sex'] in {'MALE','FEMALE','UNKNOWN'},'SEX_INVALID','sex')
   require(p['neutered'] is None or type(p['neutered']) is bool,'NEUTERED_INVALID','neutered')
   require(p['body_condition'] is None or type(p['body_condition']) is int and 1<=p['body_condition']<=9,'BODY_CONDITION_INVALID','body_condition')
   require(p['feeding_goal'] in GOALS,'FEEDING_GOAL_INVALID','feeding_goal')
   require(p['current_diet_type'] in {'COMPLETE_COMMERCIAL','HOMEMADE','MIXED','UNKNOWN'},'DIET_TYPE_INVALID','current_diet_type')
   allowed_activity={'LOW','MODERATE_LOW_IMPACT','MODERATE_HIGH_IMPACT','HIGH'} if sp=='DOG' else {'LOW','ACTIVE'}
   require(p['activity_level'] in allowed_activity,'ACTIVITY_SPECIES_CONFLICT','activity_level')
   require(p['weight_trend'] in {'STABLE','GAINING','LOSING','UNKNOWN'},'WEIGHT_TREND_INVALID','weight_trend')
   require(p['muscle_condition'] in {'NORMAL','MILD_LOSS','MODERATE_LOSS','SEVERE_LOSS','UNKNOWN'},'MUSCLE_CONDITION_INVALID','muscle_condition')
   from .life_stage_resolver import LifeStageResolver
   try:age=LifeStageResolver.profile_age(p)
   except ValueError as exc:raise ContractError(str(exc),'birth_date' if p.get('birth_date') else 'age_years') from exc
   if p.get('birth_date'):
    require(all(p[k] is None or p[k]==age[k] for k in ('age_years','age_months')),'AGE_DATE_CONFLICT','age_years')
   days=age['age_days'];p.update(age_years=age['age_years'],age_months=age['age_months'])
   stages={'GROWTH','ADULT','MATURE','SENIOR','EARLY_GROWTH','LATE_GROWTH_SMALL_MEDIUM','LATE_GROWTH_LARGE','UNWEANED'}
   require(p['life_stage'] is None or p['life_stage'] in stages,'LIFE_STAGE_INVALID','life_stage')
   if sp=='CAT':require(p['life_stage'] not in {'EARLY_GROWTH','LATE_GROWTH_SMALL_MEDIUM','LATE_GROWTH_LARGE'} and 'expected_adult_weight_kg' not in p and 'growth_complete' not in p,'SPECIES_SPECIFIC_FIELD_CONFLICT','life_stage')
   if 'expected_adult_weight_kg' in p:require(numeric(p['expected_adult_weight_kg']) and p['expected_adult_weight_kg']>=p['weight_kg'],'ADULT_WEIGHT_INVALID','expected_adult_weight_kg')
   for k in ['growth_complete','weaned']:
    if k in p:require(type(p[k]) is bool,'BOOLEAN_REQUIRED',k)
   if sp=='DOG' and days>=365 and p['life_stage'] in {'ADULT','MATURE','SENIOR'}:p.setdefault('growth_complete',True)
   if sp=='DOG' and days<365:require(not p.get('growth_complete',False),'LIFE_STAGE_AGE_CONFLICT','growth_complete')
   catalog=self.store.keyed('diseases','disease_id');diseases=[]
   require(isinstance(p['diseases'],list),'DISEASES_ARRAY_REQUIRED','diseases')
   for d in p['diseases']:
    require(isinstance(d,dict) and set(d)<={'disease_id','confirmed','stage','subtype','clinical_status'},'DISEASE_OBJECT_INVALID','diseases')
    did=d.get('disease_id');require(did in catalog,'UNKNOWN_DISEASE_ID','diseases')
    require(catalog[did]['species'] in {sp,'BOTH'},'DISEASE_SPECIES_CONFLICT','diseases')
    require(d.get('confirmed',True) is True,'DIAGNOSIS_CONFIRMATION_REQUIRED','diseases')
    require(d.get('clinical_status','STABLE') in {'STABLE','ACUTE','SEVERE','UNSTABLE'},'CLINICAL_STATUS_INVALID','diseases')
    diseases.append({'id':did,**{k:v for k,v in d.items() if k!='disease_id'}})
   require(len({d['id'] for d in diseases})==len(diseases),'DUPLICATE_DISEASE','diseases')
   ingredients=self.store.keyed('ingredients','ingredient_id');allergens=set();excluded=set()
   for k in ['food_restrictions','disliked_foods','recent_symptoms','extra_foods']:
    require(isinstance(p[k],list),'ARRAY_REQUIRED',k)
   for r in p['food_restrictions']:
    require(isinstance(r,dict) and set(r)=={'ingredient_id','reason'},'RESTRICTION_OBJECT_INVALID','food_restrictions')
    i=r['ingredient_id'];require(i in ingredients,'UNKNOWN_INGREDIENT_ID','food_restrictions');require(r['reason'] in {'ALLERGY','INTOLERANCE','VET_RESTRICTED'},'RESTRICTION_REASON_INVALID','food_restrictions')
    excluded.add(i)
    if r['reason'] in {'ALLERGY','INTOLERANCE'}:allergens.update(t for t in (ingredients[i]['allergen_tags'] or '').split(';') if t)
   if allergens:
    excluded.update(i for i,f in ingredients.items() if set((f['allergen_tags'] or '').split(';'))&allergens)
   codes=set(ingredients)|{f['food_category'] for f in ingredients.values()}|{t for f in ingredients.values() for t in (f['allergen_tags'] or '').split(';') if t}
   require(all(isinstance(x,str) and x in codes for x in p['disliked_foods']),'UNKNOWN_DISLIKED_FOOD','disliked_foods')
   signs=set(SYMPTOMS)|set(ACUTE_FLAGS)|set(self.store.config['red_flags'])|set(self.store.config['recognized_nonurgent_signs'])
   require(all(isinstance(x,str) and x in signs for x in p['recent_symptoms']),'UNKNOWN_SYMPTOM','recent_symptoms')
   for x in p['extra_foods']:
    require(isinstance(x,dict) and set(x)=={'ingredient_id','amount_g'} and x.get('ingredient_id') in ingredients and numeric(x.get('amount_g')) and x['amount_g']>0,'EXTRA_FOOD_INVALID','extra_foods')
   if 'available_ingredient_ids' in p:require(isinstance(p['available_ingredient_ids'],list) and all(i in ingredients for i in p['available_ingredient_ids']),'UNKNOWN_INGREDIENT_ID','available_ingredient_ids')
   if 'daily_label_servings' in p:require(numeric(p['daily_label_servings']) and p['daily_label_servings']>0,'LABEL_SERVINGS_INVALID','daily_label_servings')
   if 'medications' in p:require(isinstance(p['medications'],list) and all(isinstance(x,str) for x in p['medications']),'MEDICATIONS_INVALID','medications')
   if p['neutered'] is None:warnings.append(warning('NEUTER_STATUS_UNKNOWN','绝育状态未知，按当前活动模型估算并复核。','neutered'))
   if p['body_condition'] is None:warnings.append(warning('BODY_CONDITION_REQUIRED_FOR_RECIPE','可保留档案；生成完整配比前需补充1–9分体况。','body_condition'))
   pet={'species':sp,'breed':p['breed_id'],'age_days':days,'sex':p['sex'],'neutered':p['neutered'] if p['neutered'] is not None else False,'weight_kg':p['weight_kg'],'bcs':p['body_condition'] or 5,'muscle_condition':p['muscle_condition'],'weight_trend':p['weight_trend'],'activity':p['activity_level'],'diseases':diseases,'recent_abnormalities':[SYMPTOMS.get(x,x) for x in p['recent_symptoms']],'current_diet':p['current_diet_type'],'allergies':sorted(allergens),'dislikes':p['disliked_foods'],'purpose':GOALS[p['feeding_goal']]}
   for k in ['expected_adult_weight_kg','growth_complete','weaned','daily_label_servings','medications']:
    if k in p:pet[k]=p[k]
   if p['life_stage'] in {'MATURE','SENIOR'} and sp=='DOG':pet['life_stage_hint']=p['life_stage']
   if 'available_ingredient_ids' in p:pet['available_ingredients']=p['available_ingredient_ids']
   pet['_calendar_age']=age
   pet=normalize_pet(pet,self.store)
   stage=None
   try:stage,_=lifecycle(pet,self.store)
   except ValueError:warnings.append(warning('GROWTH_CONTEXT_REQUIRED','补充生长完成情况或预计成年体重后再计算。','expected_adult_weight_kg'))
   if p['life_stage']:
    stated=p['life_stage'];actual=(stage or '').removeprefix(sp+'_').replace('LATE_GROWTH_SMALL','LATE_GROWTH_SMALL_MEDIUM')
    require(stage is None or stated==actual or stated=='GROWTH' and 'GROWTH' in actual,'LIFE_STAGE_AGE_CONFLICT','life_stage')
   elif stage:p['life_stage']=stage.removeprefix(sp+'_').replace('LATE_GROWTH_SMALL','LATE_GROWTH_SMALL_MEDIUM')
   return {'status':'WARNING' if warnings else 'VALID','normalized':p,'engine_pet':pet,'excluded_ingredients':sorted(excluded),'errors':[],'warnings':warnings}
  except ContractError as e:return {'status':'INVALID','normalized':None,'engine_pet':None,'excluded_ingredients':[],'errors':[e.detail],'warnings':warnings}
  except (ValueError,TypeError,KeyError,OverflowError) as e:
   return {'status':'INVALID','normalized':None,'engine_pet':None,'excluded_ingredients':[],'errors':[error('PROFILE_INVALID',message='字段值或类型无法用于当前物种的档案。')],'warnings':warnings}
