"""API 1.8: an independently audited occasional meal, not a complete diet.

Reuse sourced food/energy/disease rules without entering the advanced recipe
presenter, supplement completion solver, clinical release or product gates.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, replace
from .daily_recipe_v17 import DailyRecipeEngine as ScientificEngine
from .daily_recipe_v15 import support_result
from .daily_disease_v13 import daily_disease_advice, daily_disease_design, body_strategy
from .scientific_profile_v17 import normalize_profile, normalize_selection, CATEGORY_MAP
from .scientific_profile import energy_start, policy as scientific_policy
from .scientific_ingredients import category
from .practical_sources import source_candidates
from .practical_math import solve_reference, audit_reference
from .practical_preparation import _cooking, KINDS, SOURCES
from .profile import lifecycle
from .runtime import active_bounds
from .freshfood_contract import require
from .practical import digest
from .quick_meal_support import nutrition_support, SCOPE_NOTE

ENGINE_VERSION = 'freshfood-quick-meal-1.8.0'
READY = {'QUICK_MEAL_RECOMMENDED','QUICK_MEAL_DISEASE_ADAPTED','QUICK_MEAL_WITH_NUTRITION_NOTES'}
CHECKS = ['ENERGY_REASONABLE','SPECIES_APPROPRIATE','LIFE_STAGE_APPROPRIATE',
          'BODY_CONDITION_APPROPRIATE','DISEASE_APPROPRIATE','INGREDIENT_SAFE',
          'USER_SELECTION_RESPECTED','RECIPE_NOT_OVERCOMPLEX','PRACTICAL_PORTION','COOKING_CONSISTENT']
ADVANCED = {'layer':'ADVANCED_COMPLETE_DIET_LAYER','api_version':'1.7',
            'status':'UNCHANGED_INDEPENDENT','scientific_acceptance':'PARTIAL',
            'blocks_quick_meal':False,'complete_balanced_claim':False,
            'capabilities':['COMPLETE_NUTRIENT_MATRIX','ADVANCED_SUPPLEMENT_TARGET','PRODUCT_SPEC','COA','EXPERT_REVIEW','SCIENTIFIC_FULL_DIET_VALIDATION']}


def normalize_input(profile, selection, store):
    require(isinstance(profile, dict), 'PROFILE_OBJECT_REQUIRED')
    p = deepcopy(profile)
    scope = p.pop('meal_scope','DAY')
    require(scope in {'DAY','MEAL'}, 'MEAL_SCOPE_INVALID','meal_scope')
    for alias, canonical in [('diagnosed_diseases','diseases'),('weight','weight_kg')]:
        if alias in p:
            require(canonical not in p or p[canonical]==p[alias], 'PROFILE_ALIAS_CONFLICT',alias)
            p[canonical] = p.pop(alias)
    if 'breed' in p:
        require('breed_id' not in p and 'breed_name' not in p, 'PROFILE_ALIAS_CONFLICT','breed')
        breed = p.pop('breed')
        require(isinstance(breed,str), 'BREED_INVALID')
        p.update(breed_id='UNKNOWN',breed_name=breed)
    if selection is not None:
        require('ingredient_selection' not in p or normalize_selection(p['ingredient_selection'],store)==normalize_selection(selection,store), 'SELECTION_INPUT_CONFLICT')
        p['ingredient_selection'] = selection
    # Unknown expected adult weight must not be fabricated. The quick growth
    # fallback uses age/RER, with size-dependent complete-diet work kept separate.
    if p.get('species')=='DOG' and not p.get('expected_adult_weight_kg') and p.get('life_stage')=='LATE_GROWTH':
        p['life_stage']='GROWTH'
    normalized, check, warnings = normalize_profile(p,store)
    normalized['meal_scope'] = scope
    return normalized, check, warnings


def feeding_count(pet, stage, diseases):
    if 'GROWTH' in stage:
        return 4 if pet['species']=='CAT' or pet['age_months_completed']<4 else 3
    if pet['species']=='CAT':
        return 4
    return 3 if diseases & {'EPI','CIE_DOG','PLE','PANCREATITIS_DOG'} and 'DIABETES_DOG' not in diseases else 2


def food_facts(sources, grams):
    selected = [s for s in sources if grams.get(s['id'],0)>0]
    nutrients = ['protein','fat','calcium','phosphorus','sodium','potassium','copper','vitamin_a','epa','dha','epa_dha','taurine','arachidonic','arginine','dietary_fiber']
    facts = {}
    for n in nutrients:
        unknown = [s['id'] for s in selected if s['values'].get(n) is None]
        subtotal = sum(grams[s['id']]*s['values'][n]/100 for s in selected if s['values'].get(n) is not None)
        facts[n] = {'amount':None if unknown else subtotal,'known_subtotal':subtotal,
                    'unquantified_food_ids':unknown,'basis':'SELECTED_PORTION_FOOD_REFERENCE',
                    'unit':'IU' if n=='vitamin_a' else 'mg' if n=='copper' else 'g'}
    ca, p = facts['calcium']['amount'],facts['phosphorus']['amount']
    facts['ca_p_ratio'] = ca/p if ca is not None and p is not None and p>0 else None
    return facts


def cooking_plan(components, total, meals, scope, policy, nutrition, health, disease):
    if not components:
        return None
    # Integer gram allocation with residual conservation; no sub-gram food work.
    each = round(total/meals)
    portions = [float(each)]*(meals-1)+[round(total-each*(meals-1),1)]
    prep, steps = [], []
    for c in components:
        how = _cooking(c)
        prep.append({'ingredient_id':c['ingredient_id'],'instruction':how['cutting']})
        instruction = how['instruction']
        if how['minimum_internal_temperature_c'] is not None:
            instruction += f" 中心至少{how['minimum_internal_temperature_c']:g}°C。"
        if how['rest_minutes']:
            instruction += f" 静置{how['rest_minutes']}分钟后再切碎。"
        steps.append({'ingredient_ids':[c['ingredient_id']], 'food_state':c['food_state'],
                      'instruction':instruction,'minimum_internal_temperature_c':how['minimum_internal_temperature_c'],
                      'rest_minutes':how['rest_minutes']})
    hydration = []
    if policy.get('retain_cooking_water'):
        hydration.append('按原方法做好并称重后，可另加清水调成湿润状态；不加盐、浓肉汤或浮油。已有饮水限制时按原安排。')
    if policy.get('hydration_policy','').startswith('PRESERVE_EXISTING'):
        hydration.append('已有心脏病饮水或用药安排时照原计划执行，不自行额外灌水。')
    return {
        'status':'READY','meal_scope':scope,
        'shopping_list':[{'ingredient_id':c['ingredient_id'],'display_name':c['display_name'],'amount_g':c['amount_g'],
                          'weight_basis':c['weight_basis'],'food_state':c['food_state'],'raw_purchase_amount_g':None} for c in components],
        'weighing_note':'肉、蛋、米饭和蔬菜按所列熟制可食重量称；油按出售状态称。不将熟重当作生重，也不猜生熟换算。',
        'preparation':prep,'cooking_steps':steps,
        'mixing':{'ingredient_ids':[c['ingredient_id'] for c in components], 'instruction':'食物充分熟制后切成适口小块并混匀，放至适口温度再喂。不加葱蒜、盐或酱汁。'},
        'feeding':{'total_g':total,'meal_count':meals,'portions_g':portions,
                   'instruction':('这是这一餐的总量。' if scope=='MEAL' else '这是当天总量，按所列餐次分装。')+'用来替代相应主粮份额，不额外叠加原有日量；已有胰岛素或胰酶餐时安排时沿用原计划。'},
        'hydration_notes':hydration,
        'storage':['及时分装冷藏（≤4°C）；本功能建议当天制作当天使用。','室温放置不超过2小时，炎热环境超过32°C时不超过1小时；吃剩或保存不当的食物丢弃。','冷藏熟食再加热至中心74°C，冷却至适口温度；避免反复加热同一份。'],
        'nutrition_reminders':[r['user_message'] for r in nutrition],
        'health_support_notes':[r['user_message'] for r in health],
        'disease_support_notes':[r['title']+'：'+r['user_message'] for r in disease],
        'sources':{k:v for k,v in SOURCES.items() if k in {'PRACTICAL_FOOD_TEMP','PRACTICAL_FDA_STORAGE','PRACTICAL_COLD_STORAGE'}},
        'product_doses_included':False,
    }


def cooking_consistent(result):
    c=result['cooking_plan'];rows=result['recipe_components']
    if not rows or c is None:return False
    ids=Counter(r['ingredient_id'] for r in rows)
    if Counter(x['ingredient_id'] for x in c['shopping_list'])!=ids or Counter(x['ingredient_id'] for x in c['preparation'])!=ids:return False
    if Counter(i for x in c['cooking_steps'] for i in x['ingredient_ids'])!=ids or Counter(c['mixing']['ingredient_ids'])!=ids:return False
    byid={r['ingredient_id']:r for r in rows}
    if any(any(x[k]!=byid[x['ingredient_id']][k] for k in ['amount_g','weight_basis','food_state']) for x in c['shopping_list']):return False
    if any(x['food_state']!=byid[i]['food_state'] for x in c['cooking_steps'] for i in x['ingredient_ids']):return False
    total=sum(r['amount_g'] for r in rows)
    return abs(total-result['daily_or_meal_total_g'])<1e-6 and abs(total-c['feeding']['total_g'])<1e-6 and abs(total-sum(c['feeding']['portions_g']))<1e-6 and len(c['feeding']['portions_g'])==result['meal_count']==c['feeding']['meal_count'] and not c['product_doses_included']


class QuickMealEngine(ScientificEngine):
    def simplify(self,foods,bounds,target,design,solution,species):
        """Remove small extras by a fresh solve; never just subtract grams."""
        trials=[]
        if solution['status']!='REFERENCE_PASS':return foods,solution,trials
        ids=[iid for iid,g in solution['grams'].items() if 0<g<=10 and next(f['category'] for f in foods if f['id']==iid) not in {'OIL','ORGAN'}]
        for iid in ids:
            if not solution['grams'].get(iid):continue
            trial_foods=[f for f in foods if f['id']!=iid]
            trial_policy=deepcopy(design)
            trial_policy['recipe_composition_policy']['target_component_count'][0]=1
            trial=solve_reference(trial_foods,bounds,target,species=species,design_policy=trial_policy)
            reasons=[]
            if trial['status']!='REFERENCE_PASS':reasons.append('NO_SAFE_REPLACEMENT')
            elif sum(g>0 for g in trial['grams'].values())>=sum(g>0 for g in solution['grams'].values()):reasons.append('NO_COMPLEXITY_REDUCTION')
            else:
                before=food_facts(foods,solution['grams']);after=food_facts(trial_foods,trial['grams'])
                for nutrient in design.get('minimize_nutrients',[]):
                    if nutrient not in after or after[nutrient]['amount'] is None or before[nutrient]['amount'] is None or after[nutrient]['amount']>before[nutrient]['amount']*1.05+1e-8:
                        reasons.append('WORSE_DISEASE_DIRECTION:'+nutrient)
                for nutrient in before:
                    if nutrient!='ca_p_ratio' and before[nutrient]['amount'] is not None and after[nutrient]['amount'] is None:
                        reasons.append('NEW_UNKNOWN:'+nutrient)
            trials.append({'removed_candidate':iid,'whole_recipe_resolved':True,'accepted':not reasons,'reason_codes':reasons or ['FEWER_INGREDIENTS_CORE_BOUNDS_PRESERVED']})
            if not reasons:foods,solution=trial_foods,trial
        return foods,solution,trials

    def candidates(self, pet, stage, target, policy, excluded, scope):
        foods, rejected = source_candidates(pet,stage,self.store,target,excluded,include_supplements=False,quick_meal=True)
        pool=pet['_ingredient_selection_v16']['categories'];config=scientific_policy(self.store)
        retained=[]
        for food in foods:
            reasons=[];definition=food['definition'];group=category(definition)
            if food['id'] not in KINDS:reasons.append('NO_MATCHED_HOUSEHOLD_PREPARATION')
            if group in pool and food['id'] not in pool[group]:reasons.append('OUTSIDE_USER_CATEGORY_POOL')
            if food['category'] in policy.get('excluded_categories',[]) or food['id'] in policy.get('exclude_ids',[]):reasons.append('DISEASE_EXCLUSION')
            label='WEANED_GROWTH' if 'GROWTH' in stage else stage.removeprefix(pet['species']+'_')
            if label not in definition['life_stage_allowed'].split(';'):reasons.append('LIFE_STAGE_EXCLUSION')
            if policy.get('exclude_high_fat_animal_sources') and food['category'] in {'MEAT','POULTRY','FISH','EGG','ORGAN'} and food['values']['fat']>10:reasons.append('DISEASE_HIGH_FAT_EXCLUSION')
            if food['category']=='FISH':
                identity=config['fish_identities'].get(food['id'])
                if not identity or identity in config['fish_contaminant_policy']['excluded_identities']:reasons.append('FISH_IDENTITY_OR_CONTAMINANT_HAZARD')
            if policy.get('prefer_low_known_plant_fiber') and food['category'] in {'STARCH','VEGETABLE'} and food['values'].get('dietary_fiber') is None:reasons.append('EPI_UNKNOWN_PLANT_FIBER')
            if reasons:rejected.append({'id':food['id'],'reasons':reasons});continue
            food['quantum']=1. if food['category']=='OIL' else 5.
            food['minimum_portion_g']=2. if food['category']=='OIL' else 5. if scope=='MEAL' else 10.
            retained.append(food)
        return retained,rejected

    def design(self, profile, ingredient_selection=None):
        normalized,check,warnings=normalize_input(profile,ingredient_selection,self.store)
        pet=deepcopy(check['engine_pet']);scope=normalized['meal_scope']
        advice=daily_disease_advice(pet,self.store);diseases=set(advice['diseases'])
        raw={'pet':pet,'recipe_status':'NO_SAFE_RECIPE','daily_foods':[],'supplements':[],
             'disease_advice':advice,'reasons':[],'solver_request':{},'data_hash':self.store.meta['data_content_sha256']}
        state={'profile':normalized,'raw':raw,'specs':[],'warnings':warnings,'target':None,'eligible_foods':[],'facts':{}}
        result={'status':'NO_SAFE_INGREDIENT_COMBINATION','product':'FreshFood Quick Meal','product_layer':'QUICK_MEAL_V1',
                'meal_scope':scope,'pet_summary':normalized,'estimated_energy_target':None,'estimated_daily_energy_target':None,
                'recipe_energy':0,'recipe_components':[],'daily_or_meal_total_g':0,'meal_count':0,'suggested_daily_meal_count':0,
                'ingredient_options':[],'nutrition_notes':[],'health_support_recommendations':[],'disease_support_recommendations':[],
                'disease_notes':[],'cooking_plan':None,'warnings':deepcopy(warnings),'support_result':None,
                'key_nutrients':{},'scientific_checks':{k:'NOT_APPLICABLE' for k in CHECKS},
                'quick_meal_scientific_acceptance':'NOT_APPLICABLE','complete_balanced_claim':False,
                'scope_note':SCOPE_NOTE,'advanced_complete_diet_layer':deepcopy(ADVANCED),
                'reason_codes':[],'calculation_metadata':{'engine_version':ENGINE_VERSION,'whole_recipe_recalculated':True,
                    'input_hash':digest(normalized),'ingredient_selection':deepcopy(normalized['ingredient_selection']),
                    'selection_mode':'CANDIDATE_POOL','equal_split_used':False,'all_selected_required':False}}
        for d in advice['disease_adaptations']:
            result['disease_notes'].append({'disease_id':d['disease_id'],'display_name':d['name_zh'],'food_direction':d['food_direction'],
                'source_id':d['source_id'],'feeding_notes':deepcopy(d['feeding_notes']),
                'hydration_notes':deepcopy(d['hydration_notes']),'numerical_treatment_prescription':False})
        if diseases & {'FOOD_ALLERGY','ADVERSE_FOOD_REACTION','FOOD_RESPONSIVE_ENTEROPATHY'} and not pet['allergies']:
            result['warnings'].append({'code':'ALLERGEN_IDENTITY_NOT_PROVIDED',
                'message':'尚未提供具体致敏来源，这份饭不能被视为低敏配方或排除试验。请保留已知耐受食物，并补充需排除的食材后重算。','field':'food_restrictions'})
        if advice['acute_red_flags']:
            raw['recipe_status']='BLOCKED_ACUTE_CONDITION'
            result.update(status='ACUTE_SUPPORT_RESULT',support_result=support_result(raw),reason_codes=advice['reasons'])
            state['result']=result;return state
        require(normalized.get('body_condition') is not None,'BODY_CONDITION_REQUIRED','body_condition')
        try:stage,reference=lifecycle(pet,self.store)
        except ValueError:stage,reference=None,None
        missing_adult=pet['species']=='DOG' and not pet.get('expected_adult_weight_kg') and (stage is None or 'GROWTH' in stage)
        if missing_adult:
            require(pet['age_months_completed']>=2,'WEANED_GROWTH_REQUIRED','age_months')
            known_large=normalized.get('life_stage')=='LATE_GROWTH_LARGE'
            stage='DOG_LATE_GROWTH_LARGE' if known_large else 'DOG_GROWTH'
            reference=('DOG_GROWTH_LATE_LARGE_'+('U6' if pet['age_months_completed']<6 else 'O6') if known_large
                       else 'DOG_GROWTH_EARLY' if pet['age_months_completed']<4 else 'DOG_GROWTH_LATE_SMALL')
            base=70*pet['weight_kg']**.75*(3 if pet['age_months_completed']<4 else 2)
            energy={'DER_start_kcal':base,'rule_id':'QUICK_PUPPY_AGE_RER_START','source_id':'MERCK_NUTRITION',
                    'source_url':'https://www.merckvetmanual.com/management-and-nutrition/nutrition-small-animals/nutritional-requirements-of-small-animals',
                    'scientific_energy':{'expected_adult_weight_unknown':True,'model':'AGE_RER_STARTING_ESTIMATE','neuter_multiplier_applied':False,'activity_multiplier_applied':False}}
            result['warnings'].append({'code':'GROWTH_SIZE_UNKNOWN','message':'未提供预计成年体重，采用年龄与当前体重的幼犬起始能量估计；提供体型信息后可进一步重算。','field':'expected_adult_weight_kg'})
        else:
            require(stage is not None and reference is not None,'UNSUPPORTED_LIFE_STAGE','life_stage')
            energy=energy_start(pet,reference,self.store);base=energy['DER_start_kcal'] or energy['interval_kcal'][0]
        require('UNWEANED' not in stage,'WEANED_GROWTH_REQUIRED','life_stage')
        reference_bounds=active_bounds({'profile_id':reference,'pet':pet,'disease_constraints':[]},self.store)
        bounds,_,design,_=daily_disease_design(pet,advice,reference_bounds,base,stage)
        body=design['body_condition_strategy'];body['energy_factor']/=body['neuter_weight_management_factor'];body['neuter_weight_management_factor']=1.
        daily_target=base*body['energy_factor'];body['daily_energy_kcal']=daily_target
        count=feeding_count(pet,stage,diseases);target=daily_target/count if scope=='MEAL' else daily_target
        # Complete-diet micronutrient minima never become a Quick Meal gate.
        # Existing known upper screens and the sourced canine low-fat limit stay.
        meal_bounds=[replace(b,minimum=None,dependency={}) if b.nutrient not in {'protein','fat'} else b for b in bounds]
        design.update(scope='OCCASIONAL_QUICK_MEAL',version='QUICK_MEAL_V1',
            objective_priority='SAFETY_NUTRITION_DISEASE_AVAILABILITY_COMPLEXITY_COST_PREFERENCE',
            soft_component_count_only=True,soft_structure_categories=[],diversity_after_cost=True,
            hydration_via_preparation=True,retry_infeasible_without_presolve=True,disease_objective_relative_slack=.05,
            check_active_nutrient_completion_capacity=False,
            recipe_composition_policy={'target_component_count':[2,5] if pet['species']=='DOG' else [1,4]},
            food_energy_share_limits={'FISH':.8},
            fish_share_scope='OCCASIONAL_IDENTIFIED_FISH_HOUSEHOLD_CAP_NOT_TOXICOLOGICAL_UL')
        if 'EPI' in diseases and pet['species']=='DOG':design['prefer_low_known_plant_fiber']=True
        if 'PANCREATITIS_CAT' in diseases:design['minimize_nutrients']=list(dict.fromkeys(design['minimize_nutrients']+['fat']))
        if pet['bcs']<4 and 'DIABETES_DOG' in diseases and not diseases & {'PANCREATITIS_DOG','HYPERLIPIDEMIA','PLE'}:
            design['minimize_nutrients']=[n for n in design['minimize_nutrients'] if n!='fat']
        result['estimated_daily_energy_target']={'kcal':round(daily_target),'basis':'ESTIMATE_NOT_MEASURED_ME'}
        result['estimated_energy_target']={'kcal':round(target),'range_kcal':[round(target*.95,1),round(target*1.05,1)],'unit':'kcal/'+scope.lower(),'basis':'HOUSEHOLD_STARTING_ESTIMATE','tolerance_fraction':.05}
        result['suggested_daily_meal_count']=count
        state['target']={'daily_energy_kcal':target,'fresh_food_energy_kcal':target,'life_stage':stage,'design_policy':design,'disease_constraints':advice['recipe_constraint_requirements'],'nutrient_constraints':[asdict(b) for b in meal_bounds]}
        raw.update(life_stage=stage,profile_id=reference,energy=energy)
        foods,rejected=self.candidates(pet,stage,target,design,set(check['excluded_ingredients']),scope)
        attempts=[];solution=None
        for include_oil in [False,True]:
            chosen_pool=[f for f in foods if include_oil or f['category']!='OIL']
            solution=solve_reference(chosen_pool,meal_bounds,target,species=pet['species'],design_policy=design)
            attempts.append({'oil_available':include_oil,'status':solution['status'],'reason_codes':solution.get('blockers',[])})
            if solution['status']!='INFEASIBLE':break
        chosen_pool,solution,simplification=self.simplify(chosen_pool,meal_bounds,target,design,solution,pet['species'])
        state['eligible_foods']=chosen_pool;raw['source_exclusions']=rejected
        result['calculation_metadata'].update(energy_inputs={'species':pet['species'],'life_stage':stage,'weight_kg':pet['weight_kg'],'body_condition':body,'activity':pet['_activity_level_v16'],'neutered':pet['neutered'],'base_model':energy},
            solver_attempts=attempts,objective_trace=solution.get('objectives',[]),source_exclusions=rejected,simplification_trials=simplification,
            design_policy=design,selected_portion_target_unrounded=target)
        unrestricted=deepcopy(pet);unrestricted['_ingredient_selection_v16']={'mode':'CANDIDATE_POOL','categories':{}}
        alternatives,_=self.candidates(unrestricted,stage,target,design,set(check['excluded_ingredients']),scope)
        result['ingredient_options']=[{'ingredient_id':f['id'],'display_name':f['definition']['name_zh'],'category':category(f['definition']),
            'requires_whole_recipe_recalculation':True,'within_current_pool':f['id'] in {x['id'] for x in foods}} for f in alternatives if category(f['definition']) in {'ANIMAL_PROTEIN','ENERGY_SOURCE','FIBER_SOURCE'}]
        if solution['status']!='REFERENCE_PASS':
            result['reason_codes']=solution.get('blockers') or ['SOLVER_NOT_COMPLETED' if solution['status']=='SOLVER_UNRESOLVED' else 'NO_FEASIBLE_SELECTED_FOOD_COMBINATION']
            result['support_result']={'reason':'当前食材选择与安全限制无法组成可执行配方。','suggestion':'可从所列较低脂或更适合当前情况的候选中调整选择后重算；不会自动加入你未接受的肉类。','no_ordinary_recipe':True}
            state['result']=result;return state
        grams=solution['grams'];raw['solver']=solution;raw['nutrition_audit']=solution['audit']
        raw['food_reference_audit']=audit_reference(chosen_pool,bounds,grams,target)
        self._materialize(state,chosen_pool,grams)
        sources={f['id']:f for f in chosen_pool}
        components=[]
        for f in raw['daily_foods']:
            source=sources[f['ingredient_id']];d=source['definition']
            components.append({'ingredient_id':f['ingredient_id'],'display_name':d['name_zh'],'amount_g':f['grams_cooked'],
                'category':CATEGORY_MAP.get(category(d),category(d)),'food_state':d['food_state'],'weight_basis':d['weight_basis'],
                'portion_basis':'EDIBLE_WEIGHT','source_id':d['source_id'],'energy_kcal':f['energy_reference_kcal']})
        state['facts']=food_facts(chosen_pool,grams)
        nutrition,health,disease,notes=nutrition_support(state,self.store)
        total=round(sum(c['amount_g'] for c in components),1);meals=1 if scope=='MEAL' else count
        result.update(status='QUICK_MEAL_DISEASE_ADAPTED' if diseases else 'QUICK_MEAL_WITH_NUTRITION_NOTES' if nutrition or notes else 'QUICK_MEAL_RECOMMENDED',
            recipe_components=components,recipe_energy=round(sum(c['energy_kcal'] for c in components),4),
            daily_or_meal_total_g=total,meal_count=meals,key_nutrients=state['facts'],nutrition_notes=nutrition,
            health_support_recommendations=health,disease_support_recommendations=disease)
        result['warnings'] += [{'code':'SUPPORT_EVIDENCE_UNAVAILABLE','message':n,'field':None} for n in notes]
        result['cooking_plan']=cooking_plan(components,total,meals,scope,design,nutrition,health,disease)
        result['scientific_checks']=self.audit(state,result)
        failures=[k for k,v in result['scientific_checks'].items() if v=='FAIL']
        result['quick_meal_scientific_acceptance']='FAIL' if failures else 'PARTIAL' if notes or 'PARTIAL' in result['scientific_checks'].values() else 'PASS'
        if failures:
            result.update(status='NO_SAFE_INGREDIENT_COMBINATION',recipe_components=[],cooking_plan=None,daily_or_meal_total_g=0,recipe_energy=0,meal_count=0,
                          nutrition_notes=[],health_support_recommendations=[],disease_support_recommendations=[],reason_codes=failures,
                          support_result={'reason':'当次安全或制作一致性检查未通过，未发布普通食物方案。','suggestion':'调整食材或资料后重新求解。','no_ordinary_recipe':True})
        state['result']=result;return state

    def audit(self,state,r):
        pet=state['raw']['pet'];stage=state['raw']['life_stage'];design=state['target']['design_policy'];rows=r['recipe_components']
        defs=self.store.keyed('ingredients','ingredient_id');target=state['target']['daily_energy_kcal']
        animal=sum(s['values']['protein']*c['amount_g']/100 for c in rows for s in state['eligible_foods'] if s['id']==c['ingredient_id'] and s['category'] in {'MEAT','POULTRY','FISH','EGG','ORGAN'})
        total_protein=r['key_nutrients']['protein']['amount'];pools=state['profile']['ingredient_selection']['categories']
        label='WEANED_GROWTH' if 'GROWTH' in stage else stage.removeprefix(pet['species']+'_')
        check={
            'ENERGY_REASONABLE':abs(r['recipe_energy']/target-1)<=.050001,
            'SPECIES_APPROPRIATE':all(defs[c['ingredient_id']][pet['species'].lower()+'_allowed'] for c in rows) and animal>=total_protein*(.8 if pet['species']=='CAT' else .6)-1e-6,
            'LIFE_STAGE_APPROPRIATE':all(label in defs[c['ingredient_id']]['life_stage_allowed'].split(';') for c in rows) and ('GROWTH' not in stage or design['body_condition_strategy']['energy_factor']>=1),
            'BODY_CONDITION_APPROPRIATE':design['body_condition_strategy']['bcs']==pet['bcs'] and design['body_condition_strategy']['weight_trend']==pet['weight_trend'],
            'DISEASE_APPROPRIATE':state['raw']['nutrition_audit']['pass'] and all(defs[c['ingredient_id']]['food_category'] not in design['excluded_categories'] and c['ingredient_id'] not in design['exclude_ids'] for c in rows),
            'INGREDIENT_SAFE':all(not defs[c['ingredient_id']]['toxicity_flag'] and not set(defs[c['ingredient_id']]['allergen_tags'].split(';'))&set(pet['allergies']) and c['food_state']!='RAW' for c in rows),
            'USER_SELECTION_RESPECTED':all(c['category'] not in pools or c['ingredient_id'] in pools[c['category']] for c in rows),
            'PRACTICAL_PORTION':all(c['amount_g']>=2 and c['amount_g']%1==0 if c['category']=='OIL' else c['amount_g']>=(5 if r['meal_scope']=='MEAL' else 10) and c['amount_g']%5==0 for c in rows),
            'COOKING_CONSISTENT':cooking_consistent(r),
        }
        result={k:'PASS' if v else 'FAIL' for k,v in check.items()}
        main=sum(c['category'] not in {'OIL','ORGAN'} for c in rows)
        result['RECIPE_NOT_OVERCOMPLEX']='PASS' if main<=(5 if pet['species']=='DOG' else 4) else 'PARTIAL'
        return {k:result[k] for k in CHECKS}
