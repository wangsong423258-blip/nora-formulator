"""Consumer household-food V1 API; advanced clinical validation is separate."""
import copy, hashlib, json, math
from datetime import date
from .profile import validate_pet, lifecycle, energy_start
from .runtime import active_bounds
from .requirements import profile_coverage_issues
from .practical_disease import disease_advice
from .practical_sources import source_candidates, ENERGY_METHOD
from .practical_math import solve_reference
from .user_supplements import selection_guides, quality_guides, validate_specs, user_sources
from dataclasses import replace

RECOMMENDED={'RECOMMENDED','RECOMMENDED_WITH_SUPPLEMENTS'}

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def normalize_pet(pet,store):
    if not isinstance(pet,dict):raise ValueError('Pet input must be an object')
    p=copy.deepcopy(pet)
    if p.get('purpose') not in ('COMPLETE_DIET','TOPPER','SUPPLEMENTAL'):raise ValueError('purpose must be COMPLETE_DIET, TOPPER or SUPPLEMENTAL')
    if 'age_months' in p and 'age_days' not in p and 'birth_date' not in p:
        if type(p['age_months']) not in (int,float) or not math.isfinite(p['age_months']) or p['age_months']<0:raise ValueError('Invalid age_months')
        p['age_days']=round(p['age_months']*365.2425/12)
    age_for_defaults=p.get('age_days',0)
    if 'birth_date' in p:
        # The normalized payload retains exact calendar age and is replayed for
        # preparation. Accept a redundant computed age only when it agrees.
        age_for_defaults=(date.fromisoformat(p['as_of_date'])-date.fromisoformat(p['birth_date'])).days
        if 'age_days' in p and (type(p['age_days']) is not int or p['age_days']!=age_for_defaults):raise ValueError('Conflicting birth_date and age_days')
        p.pop('age_days',None)
    for k,v in {'sex':'UNKNOWN','muscle_condition':'NORMAL','weight_trend':'STABLE','current_diet':'UNKNOWN','allergies':[],'dislikes':[],'diseases':[],'recent_abnormalities':[]}.items():p.setdefault(k,v)
    p.setdefault('weaned',age_for_defaults>=56)
    from .life_stage_resolver import LifeStageResolver
    resolved=p.get('_calendar_age') or (LifeStageResolver.age(birth_date=p['birth_date'],as_of_date=p['as_of_date']) if 'birth_date' in p else LifeStageResolver.age(days=age_for_defaults))
    if p.get('species')=='DOG' and resolved['age_months_completed']>=24:p.setdefault('growth_complete',True)
    # Clinical triage reads original diagnosis/symptom codes independently; the
    # established input validator is used only for ordinary biological fields.
    clinical=copy.deepcopy(p);p['diseases']=[];p['recent_abnormalities']=[]
    out=validate_pet(p,store)
    out['diseases']=clinical['diseases'];out['recent_abnormalities']=clinical['recent_abnormalities']
    for k in ['symptoms','current_abnormalities','abnormal_states','red_flags','current_status']:
        if k in clinical:out[k]=clinical[k]
    if 'budget_level' in out and out['budget_level'] not in ['LOW','MEDIUM','HIGH']:raise ValueError('Invalid budget_level')
    if "user_owned_supplements" in out:raise ValueError("LEGACY_SKU_SELECTION_REMOVED_USE_USER_SUPPLEMENTS")
    checks=validate_specs(out,store)
    if any(r["status"]=="INVALID" for r in checks):raise ValueError(";".join(e for r in checks for e in r["errors"]))
    return out


def _priorities(p,profile,energy,foods=(),supplements=(),audit=None):
    by_n={r['nutrient_id']:r for r in (audit or {}).get('rows',[])}
    priorities=[('energy','能量','维持体况，按每周体重和实际食欲调整；调整后重算全餐。'),
                ('protein','蛋白质与必需氨基酸','由熟肉、蛋或合适鱼类提供；健康老年不自动降低蛋白质。'),
                ('fat','脂肪与必需脂肪酸','核对必需脂肪酸；烹调油与补充油计入同一餐。'),
                ('linoleic','亚油酸及适用阶段的其他必需脂肪酸','结合肉、蛋和食用油计算；不把未区分的脂肪酸自动算成n-6或n-3。'),
                ('epa_dha','EPA与DHA','先核对食物贡献；是否补鱼油取决于生命阶段和缺口，不给所有宠物固定剂量。'),
                ('calcium','钙、磷与比例','普通无骨肉通常不能独立补足钙；补剂量随食物贡献重新计算。'),
                ('dietary_fiber','纤维与耐受','熟蔬菜、淀粉按便便和耐受选择，不用大量南瓜治疗疾病。'),
                ('vitamin_a','维生素与微量元素','食品提供一部分，必要时使用指定产品和明确剂量。')]
    if p['species']=='CAT':priorities.extend([('taurine','猫：牛磺酸','熟食牛磺酸未知时不借用生肉数据；标准化补充来源承担已核算部分。'),('arachidonic','猫：花生四烯酸、精氨酸与烟酸','按猫独立营养要求检查，不能沿用犬的向量。')])
    if 'GROWTH' in profile:priorities.append(('phosphorus','生长：钙磷、能量与长链脂肪酸','保持生长阶段约束；大型幼犬不得任意额外补钙。'))
    result=[]
    for n,title,why in priorities:
        if p['purpose'] in ('TOPPER','SUPPLEMENTAL') and n not in ('energy','protein','dietary_fiber'):continue
        row=by_n.get(n);contrib=(row or {}).get('contributions',[])
        if n in ('energy','dietary_fiber'):
            key='energy_reference_kcal' if n=='energy' else 'dietary_fiber_g'
            contrib=[{'id':f['ingredient_id'],'name_zh':f['name_zh'],'source_type':'FOOD','grams_cooked':f['grams_cooked'],
                      'contribution':f.get(key),'unit':'kcal' if n=='energy' else 'g','source_id':f['source_id']} for f in foods if f.get(key) is not None]
        result.append({'nutrient_id':n,'title':title,'reason':why,'food_sources':[x for x in contrib if x['source_type']=='FOOD' and x['contribution'] is not None and x['contribution']>0],
          'supplement_sources':[x for x in contrib if x['source_type']!='FOOD' and x['contribution'] is not None and x['contribution']>0],
          'check_status':row['status'] if row else 'REFERENCE_GUIDANCE','daily_energy_target_kcal':energy if n=='energy' else None})
    return result


# These actions require a disease-specific numerical or established treatment
# plan. Their advice is available, but healthy bounds cannot certify that plan.
NUMERICAL_DISEASE_ACTIONS={'CONTROL_PHOSPHORUS','INDIVIDUALIZE_PROTEIN_AND_PHOSPHORUS','STONE_SPECIFIC_MINERAL_CHECK',
 'STONE_SPECIFIC_AMINO_ACID_CHECK','EXCLUDE_HIGH_FAT','PREFER_LOWER_CARBOHYDRATE_CAT','AVOID_HIGH_OXALATE',
 'AVOID_HIGH_PURINE_ORGANS','INDIVIDUALIZE_FAT_AND_PROTEIN','INDIVIDUALIZE_PROTEIN','REVIEW_PREMIX_COPPER','WEIGHT_MANAGEMENT'}


def recommend(pet,store,*,excluded=(),required=()):
    result={'api_version':'PRACTICAL_RECIPE_V1_USER_SPECS','layer':'CONSUMER_V1','recipe_status':'LIMITED_DATA',
       'data_version':store.meta['data_version'],'data_hash':store.meta['data_content_sha256'],
       'weight_basis':'COOKED_WEIGHT','portion_basis':'EDIBLE_WEIGHT','complete_balanced_claim':False,
       'advanced_validated':False,'requires_laboratory':False,'requires_batch_coa':False,'requires_recipe_signature':False,
       'confirmed':False,'daily_foods':[],'supplements':[],'reasons':[],
       'consumer_executable':False,
       'solver_request':{'excluded':list(excluded),'required':list(required)},
       'presentation_order':['nutrition_priorities','nutrition_source_mapping','daily_foods','supplements','replacement_options','daily_care','confirmation_then_preparation']}
    guides=selection_guides(store)
    result['supplement_requirements']=[{'supplement_type':g['supplement_type'],'selection_guide':g,'user_spec_status':'NOT_PROVIDED','calculated_dose':None,'dose_unit':None,'calculation_basis':None,'warnings':[]} for g in guides]
    applicability=store.config.get('practical_v1',{}).get('eu_legal_maximum_policy')
    if not applicability or applicability.get('trigger')!='SAME_NUTRIENT_DECLARED_ADDITION' or applicability.get('trigger_amount')!='POSITIVE_ACTUAL_SELECTED_SUPPLEMENT_DOSE':
        result.update(recipe_status='BLOCKED',reasons=['VERSIONED_PRACTICAL_APPLICABILITY_POLICY_REQUIRED']);return result
    result['rule_applicability_policy']=applicability
    try:p=normalize_pet(pet,store)
    except (ValueError,TypeError,KeyError) as e:
        result.update(recipe_status='BLOCKED',reasons=['INVALID_INPUT:'+str(e)]);return result
    result.update(pet=p,use_case=p['purpose'],complete_diet=p['purpose']=='COMPLETE_DIET')
    result['supplement_requirements']=[r for r in result['supplement_requirements'] if p['species'] in r['selection_guide']['species']]
    for row in result['supplement_requirements']:row['need_status']='DETERMINED_BY_WHOLE_DIET_NOT_ALL_TYPES_REQUIRED'
    disease=disease_advice(p,store);result['disease_advice']=disease;result['daily_care']=disease['daily_care']
    if disease['status']!='PRACTICAL_CLEAR':
        result.update(recipe_status=disease['status'],reasons=disease['reasons']);return result
    try:stage,profile=lifecycle(p,store)
    except ValueError as e:
        result.update(recipe_status='PROFESSIONAL_REVIEW',reasons=['LIFE_STAGE_INPUT:'+str(e)]);return result
    result.update(life_stage=stage,profile_id=profile)
    if profile is None:
        result.update(recipe_status='PROFESSIONAL_REVIEW',reasons=['UNWEANED_OR_REPRODUCTIVE_STAGE_NEEDS_INDIVIDUAL_PLAN']);return result
    try:energy=energy_start(p,profile,store)
    except ValueError as e:
        result.update(recipe_status='PROFESSIONAL_REVIEW',reasons=['ENERGY_INPUT:'+str(e)]);return result
    if energy['DER_start_kcal'] is None and energy.get('interval_kcal') and 'energy_target_kcal' not in p:
        energy['DER_start_kcal']=energy['interval_kcal'][0];energy['selection_policy']='Documented lower endpoint as household starting estimate; monitor growth/BCS, never below published interval.'
    target=energy['DER_start_kcal'];result.update(energy=energy,energy_method=ENERGY_METHOD,
      nutrition_priorities=_priorities(p,profile,target),meals_per_day=3 if 'GROWTH' in stage else 2)
    if target is None:
        result.update(recipe_status='PROFESSIONAL_REVIEW',reasons=['ENERGY_TARGET_OUTSIDE_PUBLISHED_MODEL']);return result
    if p['bcs'] not in [4,5] or p['muscle_condition']!='NORMAL' or p['weight_trend']=='LOSING':
        result.update(recipe_status='PROFESSIONAL_REVIEW',reasons=['INDIVIDUAL_WEIGHT_OR_MUSCLE_MANAGEMENT_REQUIRED'],daily_care=disease['daily_care']);return result
    unimplemented=sorted(set(disease['recipe_constraint_requirements'])&NUMERICAL_DISEASE_ACTIONS)
    if unimplemented:
        result.update(recipe_status='PROFESSIONAL_REVIEW',reasons=['DISEASE_SPECIFIC_PLAN_REQUIRED:'+a for a in unimplemented],unimplemented_disease_constraints=unimplemented);return result
    if p.get('diet_trial_active') and not p.get('available_ingredients'):
        result.update(recipe_status='PROFESSIONAL_REVIEW',reasons=['PRESERVE_EXISTING_DIET_TRIAL_INGREDIENT_SET']);return result
    sources,rejected=source_candidates(p,stage,store,target,excluded,include_supplements=False);result['source_exclusions']=rejected
    if p['purpose'] in ('TOPPER','SUPPLEMENTAL'):
        if p['current_diet']!='COMPLETE_COMMERCIAL' and not p.get('main_diet_complete',False):
            result.update(reasons=['BALANCED_MAIN_DIET_REQUIRED_FOR_AUXILIARY_FOOD']);return result
        allowed=[s for s in sources if s['type']=='FOOD' and s['category'] in ('POULTRY','MEAT','VEGETABLE')]
        if required:allowed=[s for s in allowed if s['id'] in required]
        allowed.sort(key=lambda s:(s['cost'],s['id']))
        selected=None
        for s in allowed:
            grams=math.floor(target*.10/s['energy_high']/s['quantum'])*s['quantum']
            if grams>=s['quantum']:selected=(s,grams);break
        if selected is None:
            result.update(reasons=['NO_SAFE_AUXILIARY_PORTION']);return result
        s,g=selected;f=s['definition'];k=g*s['energy_high']
        result.update(recipe_status='RECOMMENDED',daily_foods=[{'ingredient_id':s['id'],'name_zh':f['name_zh'],'grams_cooked':g,'display_grams':g,'food_state':f['food_state'],'source_id':f['source_id'],
           'energy_reference_kcal':k,'dietary_fiber_g':None if s['values'].get('dietary_fiber') is None else s['values']['dietary_fiber']*g/100}],
          complete_diet=False,auxiliary_energy_kcal=k,remaining_complete_food_energy_kcal=target-k,
          audit={'auxiliary_fraction':k/target,'maximum_fraction':.10,'source_id':'V1_AAHA_NUTRITION2021','full_diet_claim':False},
          feeding_notes=['该鲜食仅占每日热量不超过10%；其余由适合生命阶段的完整主食提供，并扣除对应热量。','不为少量辅助鲜食叠加全日维矿粉。'])
        result['nutrition_priorities']=_priorities(p,profile,target,result['daily_foods'])
        result['nutrition_source_mapping']=result['nutrition_priorities']
        result.update(consumer_executable=True,nutrition_validation_level='AUXILIARY_FOOD_ONLY')
        result['recipe_hash']=digest({'pet':p,'foods':result['daily_foods'],'supplements':[],'data_hash':result['data_hash']});return result
    coverage=profile_coverage_issues(store.rows('requirements'),profile)
    if coverage:result.update(reasons=coverage);return result
    assessment={'profile_id':profile,'pet':p,'disease_constraints':[]}
    bounds=active_bounds(assessment,store)
    try: supplement_sources,input_results,input_errors=user_sources(p,stage,store,target,bounds)
    except ValueError as e: supplement_sources,input_results,input_errors=[],[],[str(e)]
    result['supplement_input_validation']=input_results
    if input_errors:
        result.update(reasons=input_errors,user_spec_status='INVALID');return result
    sources+=supplement_sources
    guided=any(s['definition']['supplement_mode']=='LABEL_GUIDED' for s in supplement_sources)
    original_bounds=bounds
    if guided:
        # Manufacturer guidance is an explicitly different assurance level.
        # Keep food macro/AA/EFA minima and all quantifiable declared maxima;
        # never claim absent premix micronutrient amounts are numeric zeros.
        from .user_supplements import PREMIX
        covered={'calcium','phosphorus','ca_p','potassium','sodium','chloride','magnesium','iron','zinc','copper','manganese','iodine','selenium','vitamin_a','vitamin_d','vitamin_e','b1','b2','b6','b12','niacin','b3','b5','folate','b9','biotin','choline','taurine','vitamin_k'}
        bounds=[replace(b,minimum=None,dependency={}) if b.nutrient in covered else b for b in bounds if b.basis!='RATIO']
    result['nutrition_validation_level']='MANUFACTURER_GUIDED' if guided else 'FORMULA_CALCULATED'
    solution=solve_reference(sources,bounds,target,required,p.get('price_cny_per_kg'),p.get('budget_cny_per_day'),p['species'],p.get('continuity_reference'))
    if solution['status']!='REFERENCE_PASS' and supplement_sources:
        # Distinguish impossible concentration/dispensing from nutrition failure.
        relaxed=[{**s,'quantum':min(s['quantum'],.00001)} if s['type']!='FOOD' else s for s in sources]
        diagnostic=solve_reference(relaxed,bounds,target,required,p.get('price_cny_per_kg'),p.get('budget_cny_per_day'),p['species'],p.get('continuity_reference'))
        result['dose_failure']='PRODUCT_CONCENTRATION_NOT_PRACTICAL' if diagnostic['status']=='REFERENCE_PASS' else 'NO_SAFE_SUPPLEMENT_DOSE'
        result['dose_failure_note']='选择更易计量或较低浓度规格；不输出诊断中的不可执行剂量。' if diagnostic['status']=='REFERENCE_PASS' else '当前食品和输入产品没有满足全部适用约束的剂量。'
    if guided and solution.get('audit'):
        solution['audit']['nutrition_validation_level']='MANUFACTURER_GUIDED'
        solution['audit']['all_micronutrients_verified']=False
        solution['audit']['all_required_nutrients_verified']=False
        solution['audit']['scope']='FOOD_CORE_CHECK_PLUS_MANUFACTURER_GUIDANCE_NOT_FULL_MICRONUTRIENT_VERIFICATION'
        for row in solution['audit']['rows']:
            if row['nutrient_id'] in covered:
                row.update(status='MANUFACTURER_GUIDED_UNQUANTIFIED',minimum_check='NOT_NUMERICALLY_VERIFIED',upper_check='NOT_NUMERICALLY_VERIFIED',upper_applies=None)
        solution['audit']['manufacturer_guided_constraints']=[{'constraint_id':b.id,'nutrient_id':b.nutrient,'minimum':b.minimum,'maximum':b.maximum,'status':'MANUFACTURER_GUIDED_UNQUANTIFIED'} for b in original_bounds if b.nutrient in covered or b.basis=='RATIO']

    result['solver']=solution
    if solution['status']!='REFERENCE_PASS':
        result.update(reasons=solution.get('blockers',['REFERENCE_AUDIT_FAILED']),complete_diet=False,
                      applicability='No complete household meal is released; LIMITED_DATA is information only, not permission to feed an incomplete diet.')
        return result
    by={s['id']:s for s in sources};foods=[];supps=[]
    for i,g in solution['grams'].items():
        s=by[i];d=s['definition']
        if s['type']=='FOOD':foods.append({'ingredient_id':i,'name_zh':d['name_zh'],'grams_cooked':g,'display_grams':g,'food_state':d['food_state'],'source_id':d['source_id'],'data_precision':'REFERENCE_ESTIMATE',
             'energy_reference_kcal':s['energy_low']*g,'dietary_fiber_g':None if s['values'].get('dietary_fiber') is None else s['values']['dietary_fiber']*g/100})
        else:
            supps.append({'supplement_id':i,'user_spec_id':d['id'],'supplement_type':d['supplement_type'],'product_name':d['product_name'],
                'daily_amount':g,'calculated_dose':g,'unit':s['unit'],'dose_unit':s['unit'],'source_id':'USER_LABEL:'+d['id'],
                'spec_hash':d['spec_hash'],'label_source':d['label_source'],'practical_usable':True,
                'supplement_mode':d['supplement_mode'],'nutrition_validation_level':d['nutrition_validation_level'],
                'evidence_type':'USER_CONFIRMED_LABEL_DECLARED','actual_concentration':None,'search_domain_upper_amount':s['cap'],'label_max_daily_amount':d['max_daily_amount'],'search_domain_is_safety_limit':False,
                'required_scale_resolution_g':s['quantum'] if s['unit']=='g' else None,
                'required_measurement_increment':s['quantum'],'division_allowed':d['division_allowed'],
                'calculation_basis':{'pet_profile':profile,'food_contribution_recomputed':True,'dose_relation':d['dose_relation'],'spec_hash':d['spec_hash'],'whole_diet_audit':True},
                'addition_instruction':'按用户产品说明，默认临喂前加入冷却食物；不得另换规格。','addition_source_id':'PRACTICAL_PROCESS_POLICY'})
    result.update(recipe_status='RECOMMENDED_WITH_SUPPLEMENTS' if supps else 'RECOMMENDED',daily_foods=foods,supplements=supps,nutrition_audit=solution['audit'],
       nutrition_priorities=_priorities(p,profile,target,foods,supps,solution['audit']),
       disease_constraints_applied=disease['recipe_constraint_requirements'],
       feeding_notes=['食材重量是指定方法熟制后的可食重量；补剂按指定产品称量，不按相似商品替代。','记录每周体重、体况、食欲和便便；明显变化时重新计算。',
                      '此为代表食品值与用户确认标签的家庭营养筛查，通过不代表实测代谢能或高级完整日粮认证。'],
       practical_limitations=['食品批次差异及未量化微量背景保留在审计中。','标签规格由用户确认；完整成分核算与厂家指导模式分别展示。'])
    result['nutrition_source_mapping']=result['nutrition_priorities']
    result.update(consumer_executable=True,user_spec_status='VALIDATED_USER_INPUT')
    for row in result['supplement_requirements']:
        used=[s for s in supps if s['supplement_type']==row['supplement_type']]
        row.update(user_spec_status='USED' if used else 'NOT_NEEDED_OR_NOT_SELECTED',doses=used,calculated_dose=used[0]['daily_amount'] if len(used)==1 else None,dose_unit=used[0]['unit'] if len(used)==1 else None,calculation_basis=used[0]['calculation_basis'] if len(used)==1 else None,warnings=[w for v in input_results if v.get('normalized',{}).get('supplement_type')==row['supplement_type'] for w in v['warnings']])
    result['replacement_options']=[{'ingredient_id':f['ingredient_id'],'requires_full_reoptimization':True,'group':by[f['ingredient_id']]['definition'].get('substitution_group')} for f in foods]
    result['solver']['amounts']={i:{'amount':a,'unit':by[i]['unit']} for i,a in solution['grams'].items()}
    result['solver'].pop('grams',None)
    result['recipe_hash']=digest({'pet':p,'foods':foods,'supplements':supps,'data_hash':result['data_hash']})
    return result


def replace_practical(pet,old,new,store,baseline=None):
    baseline=baseline or recommend(pet,store,required=(old,))
    if baseline.get('recipe_status') not in RECOMMENDED or old not in {r['ingredient_id'] for r in baseline.get('daily_foods',[])}:
        return {'substitution_status':'NOT_RECOMMENDED','message':'不建议这样替换','reason':'BASELINE_NOT_RECOMMENDED_OR_OLD_FOOD_ABSENT','executed':False,'baseline':baseline}
    if baseline.get('data_hash')!=store.meta['data_content_sha256']:
        return {'substitution_status':'NOT_RECOMMENDED','message':'不建议这样替换','reason':'STALE_BASELINE','executed':False}
    expected=digest({'pet':baseline.get('pet'),'foods':baseline.get('daily_foods'),'supplements':baseline.get('supplements'),'data_hash':baseline.get('data_hash')})
    if baseline.get('recipe_hash')!=expected:
        return {'substitution_status':'NOT_RECOMMENDED','message':'不建议这样替换','reason':'CHANGED_BASELINE','executed':False}
    if normalize_pet(pet,store)!=baseline.get('pet'):
        return {'substitution_status':'NOT_RECOMMENDED','message':'不建议这样替换','reason':'BASELINE_PET_MISMATCH','executed':False}
    if old==new:return {'substitution_status':'NOT_RECOMMENDED','message':'不建议这样替换','reason':'IDENTICAL_FOOD','executed':False}
    result=recommend(pet,store,excluded=(old,),required=(new,))
    good=result['recipe_status'] in RECOMMENDED
    before={s['supplement_id']:s['daily_amount'] for s in baseline.get('supplements',[])}
    after={s['supplement_id']:s['daily_amount'] for s in result.get('supplements',[])} if good else None
    return {'substitution_status':'RECOMMENDED' if good else 'NOT_RECOMMENDED','message':'已重新计算整餐和补剂' if good else '不建议这样替换',
      'executed':True,'equal_weight_swap':False,'food_and_supplements_recomputed':True,'baseline_hash':baseline['recipe_hash'],
      'supplement_before':before,'supplement_after':after,'supplement_dose_changed':before!=after if good else None,'recommendation':result}


def practical_status(store):
    return {'layer':'CONSUMER_V1','advanced_layer':'ADVANCED_VALIDATION_LAYER','data_version':store.meta['data_version'],
        'runtime_network_allowed':False,'requires_batch_coa':False,'requires_laboratory':False,'requires_recipe_signature':False,
        'reference_energy_method':ENERGY_METHOD,'advanced_production_ready':store.meta['production_ready'],
        'supplement_system':'SUPPLEMENT_USER_INPUT_ENGINE','supplement_selection_guides':selection_guides(store),
        'supplement_quality_guides':quality_guides(store),'available_modes':['LABEL_GUIDED','NUTRIENT_CALCULATED'],
        'brand_database_required':False,'domestic_channel_database_required':False}


def prepare_recommendation(recommendation,store,*,days=3,meals_per_day=None):
    """Reproduce the calculation before converting a confirmed plan to cooking.

    A caller cannot bypass a nutrition check by editing status or powder grams.
    The user confirms the concrete quantities, not a medical certification.
    """
    from .practical_preparation import prepare_practical
    if not isinstance(recommendation,dict) or not recommendation.get('pet'):
        return {'preparation_status':'NO_PREPARABLE_RECOMMENDATION','reasons':['ORIGINAL_PET_AND_CALCULATION_REQUIRED']}
    if recommendation.get('recipe_status') not in RECOMMENDED:
        return {'preparation_status':'NO_PREPARABLE_RECOMMENDATION','reasons':['RECOMMENDATION_NOT_ELIGIBLE']}
    if recommendation.get('confirmed') is not True:
        return {'preparation_status':'AWAITING_CONFIRMATION','reasons':['CONFIRM_RECOMMENDED_AMOUNTS_FIRST']}
    req=recommendation.get('solver_request',{})
    if not isinstance(req,dict):return {'preparation_status':'NO_PREPARABLE_RECOMMENDATION','reasons':['INVALID_SOLVER_REQUEST']}
    fresh=recommend(recommendation['pet'],store,excluded=req.get('excluded',()),required=req.get('required',()))
    if fresh.get('recipe_status') not in RECOMMENDED or any(fresh.get(k)!=recommendation.get(k) for k in ['recipe_hash','data_hash','daily_foods','supplements','use_case']):
        return {'preparation_status':'NEEDS_NUTRITION_RECHECK','reasons':['STALE_OR_CHANGED_RECOMMENDATION']}
    if fresh.get('consumer_executable') is not True:
        return {'preparation_status':'NEEDS_NUTRITION_RECHECK','reasons':['USER_PRODUCT_SPEC_RECHECK_REQUIRED']}
    fresh['confirmed']=True
    prepared=prepare_practical(fresh,store,days=days,meals_per_day=meals_per_day or fresh['meals_per_day'])
    prepared['nutrition_validation_level']=fresh.get('nutrition_validation_level')
    return prepared
