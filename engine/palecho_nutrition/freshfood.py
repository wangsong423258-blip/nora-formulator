"""Frozen FreshFood 1.0 local service. No HTTP, cloud or model calls.

Nutrition DB is immutable; user state is a separate append-only SQLite journal.
Confirmed plans carry materialized cooking rules, not mutable database pointers.
"""
from copy import deepcopy
from datetime import datetime,timezone
from functools import wraps
import json,sqlite3,threading,uuid
from pathlib import Path
from .freshfood_contract import *
from .practical import recommend,prepare_recommendation,digest,RECOMMENDED
from .practical_disease import disease_advice
from .practical_preparation import KINDS
from .user_supplements import validate_spec,selection_guides

def endpoint(method):
 @wraps(method)
 def wrapped(self,*args,**kwargs):
  try:
   result=method(self,*args,**kwargs)
   if 'api_version' not in result:result={**self.versions(),**result}
   return deepcopy(result)
  except ContractError as e:return {**self.versions(),'status':'ERROR','errors':[e.detail],'warnings':[],**({'dose_status':'INVALID_PRODUCT_SPEC'} if method.__name__=='setUserSupplementSpec' else {})}
  except sqlite3.Error:return {**self.versions(),'status':'ERROR','errors':[error('STATE_STORAGE_ERROR',action='CHECK_LOCAL_STATE_DATABASE')],'warnings':[]}
 return wrapped

class FreshFoodService:
 def __init__(self,store,state_path,*,clock=None):
  self.store=store;self.clock=clock or (lambda:datetime.now(timezone.utc).isoformat());self.lock=threading.RLock()
  self.calculation_control={'active':None}
  path=Path(state_path) if str(state_path)!=':memory:' else None
  if path:
   require(path.resolve()!=store.path,'STATE_DATABASE_MUST_BE_SEPARATE')
   path.parent.mkdir(parents=True,exist_ok=True)
  self.db=sqlite3.connect(str(state_path),isolation_level=None,check_same_thread=False,timeout=30)
  self.db.execute('PRAGMA foreign_keys=ON')
  self.db.executescript('''
   CREATE TABLE IF NOT EXISTS recipes(id TEXT PRIMARY KEY,version INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS profile_links(profile_id TEXT PRIMARY KEY,recipe_id TEXT NOT NULL UNIQUE REFERENCES recipes(id));
   CREATE TABLE IF NOT EXISTS recipe_versions(recipe_id TEXT NOT NULL,version INTEGER NOT NULL,body TEXT NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(recipe_id,version),FOREIGN KEY(recipe_id) REFERENCES recipes(id));
   CREATE TABLE IF NOT EXISTS confirmations(id TEXT PRIMARY KEY,recipe_id TEXT NOT NULL,version INTEGER NOT NULL,body TEXT NOT NULL,hash TEXT NOT NULL,UNIQUE(recipe_id,version),FOREIGN KEY(recipe_id,version) REFERENCES recipe_versions(recipe_id,version));
   CREATE TRIGGER IF NOT EXISTS version_no_update BEFORE UPDATE ON recipe_versions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_VERSION'); END;
   CREATE TRIGGER IF NOT EXISTS version_no_delete BEFORE DELETE ON recipe_versions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_VERSION'); END;
   CREATE TRIGGER IF NOT EXISTS snapshot_no_update BEFORE UPDATE ON confirmations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_SNAPSHOT'); END;
   CREATE TRIGGER IF NOT EXISTS snapshot_no_delete BEFORE DELETE ON confirmations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_SNAPSHOT'); END;
  ''')
 def close(self):self.db.close()
 def __enter__(self):return self
 def __exit__(self,*args):self.close()
 def versions(self):return {'api_version':API_VERSION,'nutrition_db_version':self.store.meta['data_version'],'nutrition_rules_version':self.store.meta['data_content_sha256'],'recipe_engine_version':ENGINE_VERSION}
 def designQuickFreshMeal(self,profile,ingredientSelection=None):
  """Recommended direct Quick Meal entry point: Ingredient-First API 1.9."""
  from .freshfood_v19 import ingredient_first_service
  return ingredient_first_service(self).designQuickFreshMeal(profile,ingredientSelection)
 def designFreshFoodRecipe(self,context):
  """Explicit 1.1 entry point; generatePracticalRecipe remains frozen 1.0."""
  from .freshfood_v11 import design_service
  return design_service(self).designFreshFoodRecipe(context)
 def designDailyFreshFoodRecipe(self,profile):
  """Recommended 1.2 entry point; earlier entry points retain their contracts."""
  from .freshfood_v12 import daily_service
  return daily_service(self).designDailyFreshFoodRecipe(profile)
 def _load(self,rid,expected=None):
  require(isinstance(rid,str),'RECIPE_ID_INVALID','recipe_id')
  row=self.db.execute('SELECT v.body,v.hash FROM recipes r JOIN recipe_versions v ON r.id=v.recipe_id AND r.version=v.version WHERE r.id=?',(rid,)).fetchone()
  require(row is not None,'RECIPE_NOT_FOUND','recipe_id')
  body=json.loads(row[0]);require(digest(body)==row[1],'STATE_INTEGRITY_FAILURE')
  require(body['result']['api_version']==self.versions()['api_version'],'RECIPE_API_VERSION_MISMATCH')
  if expected is not None:require(type(expected) is int and expected==body['version'],'VERSION_CONFLICT','expected_version')
  return body
 def _write(self,body):
  rid=body['recipe_id'];v=body['version'];self.db.execute('INSERT OR IGNORE INTO recipes VALUES (?,?)',(rid,0))
  self.db.execute('INSERT INTO recipe_versions VALUES (?,?,?,?)',(rid,v,json.dumps(body,ensure_ascii=False,allow_nan=False),digest(body)))
  self.db.execute('UPDATE recipes SET version=? WHERE id=?',(v,rid))
 def _transaction(self,operation):
  with self.lock:
   self.db.execute('BEGIN IMMEDIATE')
   try:result=operation();self.db.execute('COMMIT');return result
   except BaseException:self.db.execute('ROLLBACK');raise
 def _check_profile(self,p):
  from .freshfood_schema import validate_model
  validate_model('PetNutritionProfile',p)
  check=PetNutritionProfileValidator(self.store).validate(p)
  if check['status']=='INVALID':
   d=check['errors'][0];raise ContractError(d['code'],d['field'],d['message'])
  return check
 def _route(self,raw):
  d=raw.get('disease_advice',{});status=d.get('status')
  route='BLOCKED' if status=='BLOCKED' else 'PROFESSIONAL_REVIEW' if status=='PROFESSIONAL_REVIEW' else 'DISEASE_ADAPTED' if d.get('diseases') else 'HEALTHY'
  care=d.get('daily_care',{});adapt=[]
  for x in d.get('disease_details',[]):
   did=x['disease_id'];entries=lambda name:[e for e in care.get(name,[]) if e.get('disease_id')==did]
   adapt.append({'disease_id':did,'display_name':x['name_zh'],'classification':x['classification'],
     'nutrition_changes':[{'code':c,'message':x['food_direction'],'source_id':x['source_id']} for c in x['adjustments']],
     'food_preferences':entries('foods_or_patterns_preferred'),'food_limits':entries('foods_to_limit')+entries('foods_to_avoid'),
     'hydration_notes':entries('hydration_notes'),'monitoring_notes':entries('weight_monitoring')+entries('appetite_monitoring')+entries('stool_vomiting_monitoring')})
  return {'status':route,'disease_adaptations':adapt,'reason_codes':d.get('reasons',[]),'safe_general_guidance':care,'automatic_recipe_allowed':raw['recipe_status'] in RECOMMENDED,'numerical_disease_prescription':False}
 def _adapt(self,body,raw,check):
  food_defs=self.store.keyed('ingredients','ingredient_id');route=self._route(raw);foods=[];warnings=list(check['warnings'])
  warnings.append(warning('LIMITED_FOOD_DATA','采用代表食品值与用户标签；未量化背景仍保留，非高级完整日粮认证。'))
  if raw.get('nutrition_validation_level')=='MANUFACTURER_GUIDED':warnings.append(warning('PRODUCT_LABEL_GUIDED','按完整自制日粮产品说明用量；未逐项验证全部微量营养与Ca:P。','supplements'))
  if route['disease_adaptations']:warnings.append(warning('DISEASE_GENERALIZED_RULE','疾病方向不等于个体治疗处方。','diseases'))
  for f in raw.get('daily_foods',[]):
   d=food_defs[f['ingredient_id']];g=f['grams_cooked'];span=raw.get('solver',{}).get('food_amount_ranges',{}).get(f['ingredient_id'],{'amount_min_g':g,'amount_max_g':g})
   foods.append({'ingredient_id':f['ingredient_id'],'display_name':f['name_zh'],'amount_g':g,'amount_min_g':span['amount_min_g'],'amount_max_g':span['amount_max_g'],
     'weight_basis':'COOKED_WEIGHT' if d['raw_or_cooked']=='COOKED' else 'AS_SOLD_WEIGHT','food_state':d['food_state'],'portion_basis':'EDIBLE_WEIGHT',
     'purpose':[d['food_category']],'replaceable':True,'replacement_group':d['substitution_group'],'china_availability':d['china_availability'],'cost_level':d['cost_level'],
     'preparation_hint':{'method_id':d['cooking_method_id'],'message':'按指定熟制方法称最终可食重量；变更方法需重算。'},'range_policy':'SIMULTANEOUS_REFERENCE_BOX_FIXED_SUPPLEMENTS'})
  guides={g['supplement_type']:g for g in selection_guides(self.store)};supps=[]
  used={s['user_spec_id']:s for s in raw.get('supplements',[])}
  for spec in body['specs']:
   normalized=validate_spec(spec,self.store,body['profile']['species']);s=used.get(spec['id']);dose=s['daily_amount'] if s else 0 if raw['recipe_status'] in RECOMMENDED else None
   bad=normalized['status']=='INVALID';failed=raw.get('dose_failure')=='PRODUCT_CONCENTRATION_NOT_PRACTICAL'
   supps.append({'supplement_type':spec['supplement_type'],'user_spec_id':spec['id'],'purpose':guides[spec['supplement_type']]['purpose'],'selection_guide':guides[spec['supplement_type']],
    'user_spec_required':False,'need_status':'SATISFIED' if dose is not None and dose>0 else 'NOT_NEEDED' if dose==0 else 'NEEDS_EVALUATION','user_spec_status':normalized['status'],'calculated_dose':dose,'dose_unit':s['unit'] if s else (normalized['normalized'] or {}).get('dose_unit'),
    'practical_dose':dose,'practical_unit':s['unit'] if s else (normalized['normalized'] or {}).get('dose_unit'),
    'dose_status':'INVALID_PRODUCT_SPEC' if bad else 'CONCENTRATION_NOT_PRACTICAL' if failed else 'USABLE' if dose is not None else None,
    'dose_pending_reason':None if dose is not None else raw.get('dose_failure','WHOLE_DIET_NOT_SOLVED'),'supplement_mode':spec.get('supplement_mode','NUTRIENT_CALCULATED'),
    'spec_hash':(normalized['normalized'] or {}).get('spec_hash'),'calculation_basis':s.get('calculation_basis') if s else None,
    'warnings':[warning(code,'请核对当前标签适用性及计量条件。','supplements') for code in normalized['warnings']]})
  if raw['recipe_status']=='LIMITED_DATA':
   present={s['supplement_type'] for s in supps}
   for g in guides.values():
    if body['profile']['species'] not in g['species'] or g['supplement_type'] in present:continue
    gaps={x.split(':',1)[1] for x in raw.get('reasons',[]) if x.startswith('NO_RELIABLE_MINIMUM_CONTRIBUTION:')}
    required=bool(gaps & ({'taurine'} if g['supplement_type']=='TAURINE' else {'calcium'} if g['supplement_type']=='CALCIUM' else {'epa_dha'} if g['supplement_type']=='OMEGA3_FISH_OIL' else gaps-{'epa_dha','taurine'}))
    supps.append({'supplement_type':g['supplement_type'],'user_spec_id':None,'purpose':g['purpose'],'selection_guide':g,'user_spec_required':required,'need_status':'REQUIRED_TO_CALCULATE' if required else 'NEEDS_EVALUATION','user_spec_status':'NOT_PROVIDED','calculated_dose':None,'dose_unit':None,'practical_dose':None,'practical_unit':None,'dose_status':None,'dose_pending_reason':'PRODUCT_SPEC_REQUIRED_TO_EVALUATE_NEED','supplement_mode':None,'spec_hash':None,'calculation_basis':None,'warnings':[]})
  focus=[]
  for n in raw.get('nutrition_priorities',[]):
   supplied=bool(n['supplement_sources']);checked=n['check_status']=='PASS_REFERENCE_SCREEN' or n['nutrient_id']=='energy' and raw['recipe_status'] in RECOMMENDED;controlled=any(n['nutrient_id']=='phosphorus' and d['disease_id']=='CKD' for d in route['disease_adaptations'])
   status='CONTROL' if controlled else 'ADEQUATE' if checked else 'NEEDS_SUPPLEMENT' if supplied else 'MONITOR'
   focus.append({'nutrient_id':n['nutrient_id'],'display_name':n['title'],'status':status,'importance':'SPECIES_SPECIFIC' if n['nutrient_id'] in {'taurine','arachidonic'} else 'CORE',
    'strategy':'FOOD_AND_USER_SUPPLEMENT' if supplied else 'FOOD_FIRST_REASSESS','primary_sources':n['food_sources']+n['supplement_sources'],'supplement_required':True if supplied else None if raw['recipe_status'] not in RECOMMENDED else False,'explanation':n['reason']})
  for reason in raw.get('reasons',[]):
   if reason.startswith('NO_RELIABLE_MINIMUM_CONTRIBUTION:'):
    nutrient=reason.split(':',1)[1]
    if not any(f['nutrient_id']==nutrient for f in focus):focus.append({'nutrient_id':nutrient,'display_name':nutrient,'status':'NEEDS_SUPPLEMENT','importance':'CORE','strategy':'PROVIDE_QUANTIFIED_SOURCE','primary_sources':[],'supplement_required':None,'explanation':'当前没有足够的已知贡献；需要核对适用补剂或其他可靠来源，不能把未知当零。'})
  blocking=[BLOCK_CODES.get(c,'ACUTE_SEVERE_CONDITION') for c in raw.get('disease_advice',{}).get('acute_red_flags',[])]
  return {**self.versions(),'recipe_id':body['recipe_id'],'recipe_version':body['version'],'profile_version':body['profile_version'],'status':raw['recipe_status'],
   'pet_summary':deepcopy(body['profile']),'nutrition_focus':focus,'foods':foods,'supplements':supps,'disease_adaptations':route['disease_adaptations'],'disease_routing':route,
   'warnings':warnings,'errors':[],'blocking_reasons':sorted(set(blocking)),'reason_codes':raw.get('reasons',[]),'safe_general_guidance':route['safe_general_guidance'],
   'replacement_options':[{'source_ingredient_id':f['ingredient_id'],'replacement_group':f['replacement_group'],'requires_whole_recipe_recalculation':True} for f in foods],
   'calculation_summary':{'energy':raw.get('energy'),'nutrition_validation_level':raw.get('nutrition_validation_level'),'nutrition_audit':raw.get('nutrition_audit'),
    'whole_recipe_recalculated':True,'continuity_reference_hash':digest(body['continuity_reference']) if body.get('continuity_reference') else None,'dose_failure':raw.get('dose_failure'),'source_exclusions':raw.get('source_exclusions',[]),'rounding_reaudited':raw.get('solver',{}).get('rounding_reaudited',False),'complete_balanced_claim':False,'advanced_validated':False,
    'weight_basis':'COOKED_WEIGHT','portion_basis':'EDIBLE_WEIGHT','data_hash':self.store.meta['data_content_sha256'],'input_hash':digest({'profile':body['profile'],'specs':body['specs'],'excluded':body['excluded'],'required':body['required'],'continuity_reference':body.get('continuity_reference')})}}
 def _compute(self,body):
  check=self._check_profile(body['profile']);p=check['engine_pet'];p['user_supplements']=deepcopy(body['specs'])
  if body.get('continuity_reference'):p['continuity_reference']=body['continuity_reference']
  excluded=set(body['excluded'])|set(check['excluded_ingredients'])
  raw=recommend(p,self.store,excluded=sorted(excluded),required=body['required'])
  if body['profile']['extra_foods'] or body['profile']['body_condition'] is None:
   if raw['recipe_status']!='BLOCKED':raw.update(recipe_status='PROFESSIONAL_REVIEW',daily_foods=[],supplements=[],consumer_executable=False,nutrition_priorities=[],nutrition_audit=None,solver={},reasons=raw.get('reasons',[])+(['EXTRA_FOODS_REQUIRE_WHOLE_DIET_ACCOUNTING'] if body['profile']['extra_foods'] else ['BODY_CONDITION_REQUIRED']))
  body['raw']=raw;body['result']=self._adapt(body,raw,check);return body
 @endpoint
 def validateProfile(self,profile):
  r=PetNutritionProfileValidator(self.store).validate(profile);return {k:v for k,v in r.items() if k not in {'engine_pet','excluded_ingredients'}}
 @endpoint
 def generatePracticalRecipe(self,profile):
  check=self._check_profile(profile)
  def op():
   row=self.db.execute('SELECT recipe_id FROM profile_links WHERE profile_id=?',(check['normalized']['profile_id'],)).fetchone()
   if row:
    old=self._load(row[0]);require(old['profile']['species']==check['normalized']['species'],'PROFILE_SPECIES_IMMUTABLE','species')
    if old['profile']==check['normalized'] and old['result']['nutrition_rules_version']==self.versions()['nutrition_rules_version'] and old['result']['recipe_engine_version']==ENGINE_VERSION:return old['result']
    body=self._updated_profile_body(old,check);self._write(body);return body['result']
   body={'recipe_id':'recipe_'+uuid.uuid4().hex,'version':1,'profile_version':1,'profile':check['normalized'],'specs':[],'excluded':[],'required':[]}
   self._compute(body);self._write(body);self.db.execute('INSERT INTO profile_links VALUES (?,?)',(body['profile']['profile_id'],body['recipe_id']));return body['result']
  return self._transaction(op)

 @endpoint
 def getRecipe(self,recipe_id,recipe_version=None):
  if recipe_version is None:return self._load(recipe_id)['result']
  row=self.db.execute('SELECT body,hash FROM recipe_versions WHERE recipe_id=? AND version=?',(recipe_id,recipe_version)).fetchone();require(row is not None,'RECIPE_VERSION_NOT_FOUND')
  data=json.loads(row[0]);require(digest(data)==row[1],'STATE_INTEGRITY_FAILURE');require(data['result']['api_version']==self.versions()['api_version'],'RECIPE_API_VERSION_MISMATCH');return data['result']
 def _changes(self,old,new):
  a={r['nutrient_id']:r for r in (old['result']['calculation_summary'].get('nutrition_audit') or {}).get('rows',[])}
  b={r['nutrient_id']:r for r in (new['result']['calculation_summary'].get('nutrition_audit') or {}).get('rows',[])}
  return [{'nutrient_id':n,'previous':a.get(n),'current':b.get(n)} for n in sorted(set(a)|set(b)) if a.get(n)!=b.get(n)]
 def _recalc_result(self,old,new):
  r=new['result'];return {**self.versions(),'recipe_id':new['recipe_id'],'previous_version':old['version'],'new_version':new['version'],'foods':r['foods'],'supplements':r['supplements'],'nutrition_changes':self._changes(old,new),'warnings':r['warnings'],'errors':[],'status':r['status'],'recipe':r,'whole_recipe_recalculated':True}
 def _next(self,old):
  new=deepcopy(old);new['version']+=1;new.pop('raw',None);new.pop('result',None);new.pop('continuity_reference',None);return new
 @endpoint
 def recalculateRecipe(self,recipe_id,expected_version=None):
  def op():
   old=self._load(recipe_id,expected_version);new=self._compute(self._next(old));self._write(new);return self._recalc_result(old,new)
  return self._transaction(op)
 @endpoint
 def setUserSupplementSpec(self,recipe_id,userSupplementSpec,expected_version=None):
  def op():
   old=self._load(recipe_id,expected_version);p=old['profile']
   from .freshfood_schema import validate_model
   validate_model('UserSupplementSpec',userSupplementSpec)
   v=validate_spec(userSupplementSpec,self.store,p['species'],old['raw'].get('life_stage'))
   if v['status']=='INVALID':
    reason=v['errors'][0];code='SUPPLEMENT_EPA_DHA_INVALID' if 'EPA_DHA' in reason or 'OIL_EXCEEDS' in reason else 'INVALID_PRODUCT_SPEC'
    msg='EPA和DHA总量或单位与每份产品标签不一致，请重新核对标签。' if code=='SUPPLEMENT_EPA_DHA_INVALID' else '补剂规格不满足计算要求：'+reason
    return {**self.versions(),'status':'ERROR','recipe_id':recipe_id,'previous_version':old['version'],'new_version':old['version'],'dose_status':'INVALID_PRODUCT_SPEC','errors':[error(code,'userSupplementSpec',msg)],'warnings':[]}
   new=self._next(old);spec=deepcopy(userSupplementSpec);spec.setdefault('created_at',self.clock());spec['updated_at']=self.clock()
   new['specs']=[s for s in new['specs'] if s['id']!=spec['id']]+[spec];new['specs'].sort(key=lambda s:s['id']);self._compute(new);self._write(new);return self._recalc_result(old,new)
  return self._transaction(op)
 def _updated_profile_body(self,old,c):
  new=self._next(old);new['profile']=c['normalized'];new['profile_version']+=1
  # Scaling provides an optimization preference only, never a released dose.
  # New energy and every nutrient constraint are solved again before release.
  from .profile import lifecycle,energy_start
  if old['result']['status'] in RECOMMENDED:
   try:
    pet=c['engine_pet'];_,stage=lifecycle(pet,self.store);energy=energy_start(pet,stage,self.store);target=energy['DER_start_kcal'] or energy['interval_kcal'][0]
    old_target=old['raw']['energy']['DER_start_kcal'];ratio=target/old_target
    amounts={f['ingredient_id']:f['grams_cooked'] for f in old['raw']['daily_foods']};amounts.update({s['supplement_id']:s['daily_amount'] for s in old['raw']['supplements']})
    new['continuity_reference']={k:v*ratio for k,v in amounts.items()}
   except (ValueError,KeyError,TypeError):pass
  return self._compute(new)
 @endpoint
 def updatePetNutritionProfile(self,recipe_id,profile,expected_version=None):
  def op():
   old=self._load(recipe_id,expected_version);c=self._check_profile(profile);require(c['normalized']['profile_id']==old['profile']['profile_id'],'PROFILE_ID_CONFLICT','profile_id')
   require(c['normalized']['species']==old['profile']['species'],'PROFILE_SPECIES_IMMUTABLE','species')
   new=self._updated_profile_body(old,c);self._write(new);return self._recalc_result(old,new)
  return self._transaction(op)
 @endpoint
 def replaceIngredient(self,request):
  require(isinstance(request,dict) and set(request)<={'recipe_id','source_ingredient_id','target_ingredient_id','user_requested_amount','expected_version'},'REPLACEMENT_REQUEST_INVALID')
  require(all(isinstance(request.get(k),str) for k in ['recipe_id','source_ingredient_id','target_ingredient_id']),'REPLACEMENT_REQUEST_INVALID')
  def op():
   old=self._load(request['recipe_id'],request.get('expected_version'));src=request['source_ingredient_id'];dst=request['target_ingredient_id'];defs=self.store.keyed('ingredients','ingredient_id');reasons=[]
   if old['result']['status'] not in RECOMMENDED:reasons.append('BASELINE_NOT_RECOMMENDED')
   if src not in {f['ingredient_id'] for f in old['result']['foods']}:reasons.append('SOURCE_INGREDIENT_NOT_IN_RECIPE')
   if dst not in defs:reasons.append('UNKNOWN_INGREDIENT_ID')
   elif dst in self._check_profile(old['profile'])['excluded_ingredients']:reasons.append('ALLERGY_CONFLICT' if any(r['reason']=='ALLERGY' for r in old['profile']['food_restrictions']) else 'FOOD_RESTRICTION_CONFLICT')
   elif defs[dst]['toxicity_flag']:reasons.append('UNSAFE_INGREDIENT')
   if src==dst:reasons.append('IDENTICAL_INGREDIENT')
   if request.get('user_requested_amount') is not None:reasons.append('USER_FIXED_AMOUNT_REQUIRES_SEPARATE_CONSTRAINT_SUPPORT')
   if reasons:return {'status':'REPLACEMENT_REJECTED','recipe_id':old['recipe_id'],'previous_version':old['version'],'new_version':old['version'],'reason_codes':reasons,'warnings':[],'errors':[],'recipe':old['result']}
   new=self._next(old);new['excluded']=sorted((set(new['excluded'])|{src})-{dst});new['required']=sorted((set(new['required'])-{src})|{dst})
   if 'available_ingredient_ids' in new['profile']:
    new['profile']['available_ingredient_ids']=sorted((set(new['profile']['available_ingredient_ids'])-{src})|{dst});new['profile_version']+=1
   self._compute(new)
   if new['result']['status'] not in RECOMMENDED:
    reasons=['DISEASE_CONFLICT' if new['result']['status']=='PROFESSIONAL_REVIEW' else 'NO_SAFE_SUPPLEMENT_DOSE' if new['raw'].get('dose_failure')=='NO_SAFE_SUPPLEMENT_DOSE' else 'NUTRITION_IMBALANCE']
    return {'status':'REPLACEMENT_REJECTED','recipe_id':old['recipe_id'],'previous_version':old['version'],'new_version':old['version'],'reason_codes':reasons,'diagnostic_reason_codes':new['raw'].get('reasons',[]),'warnings':new['result']['warnings'],'errors':[],'recipe':old['result'],'attempted_status':new['result']['status']}
   self._write(new);r=self._recalc_result(old,new);r.update(status='REPLACEMENT_ACCEPTED',reason_codes=[],equal_weight_swap=False);return r
  return self._transaction(op)
 def _cooking(self,body,snapshot_id,batch_days,*,prepared=None):
  raw=body['raw'];p=prepared if prepared is not None else prepare_recommendation({**raw,'confirmed':True},self.store,days=batch_days)
  require(p['preparation_status'] in {'READY','READY_AUXILIARY'},'COOKING_PLAN_RECHECK_FAILED')
  foods=self.store.keyed('ingredients','ingredient_id');shopping=[];preparation=[];steps=[]
  for idx,r in enumerate(p['shopping_list'],1):
   i=r['ingredient_id'];d=foods[i];method=r['cooking'];basis='COOKED_WEIGHT' if d['raw_or_cooked']=='COOKED' else 'AS_SOLD_WEIGHT'
   shopping.append({'ingredient_id':i,'display_name':d['name_zh'],'daily_amount':r['daily_consumed_g'],'batch_amount':r['batch_consumed_g'],'unit':'g','amount_basis':basis,'purchase_note':r['purchase_note'],'raw_purchase_amount_g':r['gross_purchase_g'],'first_cook_batch_g':r.get('first_cook_batch_g'),'repeat_cook_every_days':r.get('repeat_cook_every_days')})
   kind=KINDS[i];preparation.append({'ingredient_id':i,'trim_instruction':'按来源食品身份保留可食部分，去掉不可食部分。','bone_instruction':'去骨、鱼刺及蛋壳，不计入可食重量。' if kind in {'POULTRY','MEAT','FISH','EGG'} else '不适用；去掉不可食部分。','skin_instruction':'按来源食品身份处理皮，不自行改变去皮/带皮状态。','cut_instruction':method.get('cutting','按最终可食状态处理。'),'weight_basis':basis,'source_food_identity':d['name_en']})
   steps.append({'step':idx,'ingredients':[i],'method':method['cooking_method'],'instruction':method['instruction'],'important_notes':[method['time_note']]+([method['ground_meat_caution']] if method.get('ground_meat_caution') else []),'minimum_internal_temperature_c':method['minimum_internal_temperature_c'],'rest_minutes':method['rest_minutes'],'source_id':method['temperature_source_id']})
  types={s['supplement_id']:s['supplement_type'] for s in raw['supplements']};supp=[]
  for r in p['supplements']:
   supp.append({'supplement_type':types[r['supplement_id']],'user_spec_id':r['supplement_id'].removeprefix('USER:'),'dose':r['daily_amount'],'unit':r['unit'],'when_to_add':'AT_FEEDING_AFTER_BASE_FOOD_COOLED','mixing_instruction':r['addition_instruction'],'source_id':r['addition_source_id'],'thermal_stability':r['thermal_stability'],'per_meal_schedule':r['per_meal_schedule'],'batch_total_to_have':r['batch_total_to_have']})
  care=body['result']['safe_general_guidance'];mapping={'eat_less':'foods_to_limit','prefer':'foods_or_patterns_preferred','avoid':'foods_to_avoid','hydration':'hydration_notes','weight_monitoring':'weight_monitoring','appetite_monitoring':'appetite_monitoring','stool_monitoring':'stool_vomiting_monitoring','other_monitoring':'stop_self_adjustment'}
  notes=[{'disease_id':d['disease_id'],**{k:[x for x in care.get(v,[]) if x.get('disease_id')==d['disease_id']] for k,v in mapping.items()}} for d in body['result']['disease_adaptations']]
  storage=p['storage'];goal=body['profile']['feeding_goal'];scope={'FULL_DAILY_DIET':'full_daily_diet','PARTIAL_DIET':'partial_diet','OCCASIONAL_MEAL':'occasional_meal'}[goal]
  return {**self.versions(),'confirmed_recipe_id':snapshot_id,'recipe_id':body['recipe_id'],'recipe_version':body['version'],'status':'READY','batch_days':batch_days,'shopping_list':shopping,'ingredient_preparation':preparation,'cooking_steps':steps,'supplement_steps':supp,
   'daily_feeding_plan':{'diet_scope':scope,'daily_total_g':p['daily_total_with_supplements_g'],'daily_food_g':p['daily_food_total_g'],'meals_per_day':p['meals_per_day'],'amount_per_meal_g':p['per_meal_food_g'],'amount_per_meal_basis':'FOOD_ONLY_SUPPLEMENTS_SEPARATE','fresh_food_energy_fraction_max':1 if scope=='full_daily_diet' else .1,'remaining_complete_food_energy_kcal':raw.get('remaining_complete_food_energy_kcal'),'mass_note':p['mass_note']},
   'storage_plan':{'recommended_batch_days':3,'requested_batch_days':batch_days,'refrigeration_guidance':{'max_temperature_c':storage['refrigerator_max_c'],'planning_days':storage['refrigerator_planning_days'],'message':storage['planning_basis']},'freezing_guidance':{'max_temperature_c':storage['freezer_max_c'],'message':p['portions']['freeze_instruction'],'egg_instruction':p['portions']['egg_instruction']},'thawing_guidance':storage['thawing'],'food_safety_notes':[storage['discard'],storage['reheating']],'source_ids':storage['source_ids'],'portions':p['portions']},
   'transition_plan':p['transition'],'disease_lifestyle_notes':notes,'safety_notes':p['feeding_notes']+p['mixing_order'],'warnings':body['result']['warnings'],'errors':[],'nutrition_validation_level':raw.get('nutrition_validation_level'),'advanced_validated':False}
 def _snapshot_details(self,body):return {}
 def _snapshot_profile(self,body):return deepcopy(body['profile'])
 @endpoint
 def confirmRecipe(self,recipe_id,expected_version=None):
  def op():
   body=self._load(recipe_id,expected_version);require(body['result']['status'] in RECOMMENDED,'RECIPE_NOT_CONFIRMABLE','recipe_id')
   require(body['result']['nutrition_rules_version']==self.versions()['nutrition_rules_version'] and body['result']['recipe_engine_version']==self.versions()['recipe_engine_version'],'STALE_RECIPE_RECALCULATION_REQUIRED')
   row=self.db.execute('SELECT body,hash FROM confirmations WHERE recipe_id=? AND version=?',(recipe_id,body['version'])).fetchone()
   if row:
    snapshot=json.loads(row[0]);require(digest(snapshot)==row[1],'STATE_INTEGRITY_FAILURE')
   else:
    sid='confirmed_'+uuid.uuid4().hex
    snapshot={**self.versions(),'confirmed_recipe_id':sid,'recipe_id':recipe_id,'recipe_version':body['version'],'profile_version':body['profile_version'],'ingredient_data_version':self.store.meta['data_content_sha256'],'nutrition_rule_version':self.versions()['nutrition_rules_version'],'supplement_specs':deepcopy(body['specs']),'timestamp':self.clock(),'profile':self._snapshot_profile(body),'recipe':deepcopy(body['result']),**self._snapshot_details(body),'cooking_plans':{str(d):self._cooking(body,sid,d) for d in (1,3,7)}}
    self.db.execute('INSERT INTO confirmations VALUES (?,?,?,?,?)',(sid,recipe_id,body['version'],json.dumps(snapshot,ensure_ascii=False,allow_nan=False),digest(snapshot)))
   return {**{k:snapshot[k] for k in self.versions()},'status':'CONFIRMED','confirmed_recipe_id':snapshot['confirmed_recipe_id'],'confirmed_recipe_snapshot':{k:v for k,v in snapshot.items() if k!='cooking_plans'},'snapshot_hash':digest(snapshot)}
  return self._transaction(op)
 @endpoint
 def generateCookingPlan(self,confirmed_recipe_id,batch_days=3):
  require(isinstance(confirmed_recipe_id,str),'CONFIRMED_RECIPE_ID_INVALID','confirmed_recipe_id')
  require(type(batch_days) is int and batch_days in (1,3,7),'BATCH_DAYS_UNSUPPORTED','batch_days')
  row=self.db.execute('SELECT body,hash FROM confirmations WHERE id=?',(confirmed_recipe_id,)).fetchone();require(row is not None,'CONFIRMED_RECIPE_NOT_FOUND','confirmed_recipe_id')
  snapshot=json.loads(row[0]);require(digest(snapshot)==row[1],'STATE_INTEGRITY_FAILURE');require(snapshot['api_version']==self.versions()['api_version'],'RECIPE_API_VERSION_MISMATCH');return snapshot['cooking_plans'][str(batch_days)]
