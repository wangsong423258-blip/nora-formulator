"""Offline food-first RecipeDesignEngine for FreshFood 1.1.

Uses the frozen representative-food matrix and rounded MILP, never modifies the
1.0 clinical or intake semantics. Clinical direction is distinct from treatment.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from math import floor
from .freshfood_contract import require, warning
from .profile import lifecycle, energy_start
from .runtime import active_bounds
from .requirements import profile_coverage_issues
from .solver import NutrientBound
from .practical import digest, NUMERICAL_DISEASE_ACTIONS
from .practical_disease import disease_advice
from .practical_sources import source_candidates
from .practical_math import solve_reference, audit_reference
from .user_supplements import user_sources
from .recipe_design_context import normalize_context, estimate_current_intake

ENGINE_VERSION='freshfood-design-1.1.0'
COMPONENTS={'MEAT':'ANIMAL_PROTEIN','POULTRY':'ANIMAL_PROTEIN','FISH':'ANIMAL_PROTEIN','STARCH':'ENERGY_SOURCE','OIL':'ENERGY_SOURCE','VEGETABLE':'FIBER_VEGETABLE','EGG':'OPTIONAL_EGG','ORGAN':'OPTIONAL_ORGAN'}
PURPOSES={'ANIMAL_PROTEIN':'主要蛋白质来源','ENERGY_SOURCE':'提供所需能量和适用脂肪酸','FIBER_VEGETABLE':'纤维与消化耐受','OPTIONAL_EGG':'补充蛋白及食物营养','OPTIONAL_ORGAN':'经上限校验的少量内脏'}
SUPPLEMENT_PURPOSES={'CALCIUM':'无骨食材的钙贡献不足时，补足钙并校验整体钙磷比例；不用骨头补钙。',
 'TAURINE':'按猫的独立需求核算牛磺酸；熟肉未量化的贡献不用于保证最低摄入。',
 'OMEGA3_FISH_OIL':'根据食物及已有补剂的EPA+DHA贡献决定用量，同时计入油脂与能量。',
 'DOG_VITAMIN_MINERAL':'补足犬当前食材组合无法稳定满足的维生素和矿物质，按指定标签计算。',
 'CAT_VITAMIN_MINERAL':'按猫独立营养要求补足食材无法稳定满足的维生素和矿物质，核对标签含有的牛磺酸。'}
KINDS={'COMPLETE_DIET':'complete_fresh_food_recipe','PARTIAL_WITH_MAIN_DIET':'supplemental_fresh_food','OCCASIONAL_MEAL':'safe_occasional_recipe'}
HANDLED={'CONTROL_PHOSPHORUS','INDIVIDUALIZE_PROTEIN_AND_PHOSPHORUS','EXCLUDE_HIGH_FAT','WEIGHT_MANAGEMENT','AVOID_HIGH_PURINE_ORGANS','AVOID_HIGH_OXALATE','PREFER_LOWER_CARBOHYDRATE_CAT'}


def supplement_type(source,species):
    d=source['definition']
    if d.get('supplement_type'):return d['supplement_type']
    if source['type']=='MULTI_NUTRIENT_PREMIX':return species+'_VITAMIN_MINERAL'
    if (source['values'].get('calcium') or 0)>0:return 'CALCIUM'
    if (source['values'].get('taurine') or 0)>0:return 'TAURINE'
    return 'OMEGA3_FISH_OIL'


def disease_design(pet,advice,bounds,energy,stage):
    ids=set(advice['diseases']);policy={'version':'CN_HOUSEHOLD_DESIGN_1.1','minimize_nutrients':[]}
    excluded_categories=set();reasons=[];daily=energy
    if 'CKD' in ids:
        policy['minimize_nutrients']=['phosphorus','protein'];excluded_categories.add('ORGAN')
        policy['ckd_scope']='LOWER_PHOSPHORUS_SELECTION_WITH_HEALTHY_MINIMA_PRESERVED_NOT_RENAL_TREATMENT_TARGET'
    if ids & {'PANCREATITIS_DOG','HYPERLIPIDEMIA'}:
        bounds=bounds+[NutrientBound('DESIGN_DOG_LOW_FAT','fat','g','PER_1000_KCAL_ME',maximum=19.9,source_id='MERCK_PANCREATITIS',source_locator='Dog chronic pancreatitis: less than 20 g fat/1000 kcal')]
        policy['minimize_nutrients'].append('fat')
    if 'OBESITY' in ids or pet['bcs']>=6:
        # Product starting policy, not a clinical ideal-weight prescription.
        # Retain the original absolute nutrient floor at the lower energy target.
        daily=energy*.9;policy['energy_adjustment']='INITIAL_10_PERCENT_REDUCTION_REASSESS_WEEKLY'
        policy['minimize_nutrients'].append('fat')
    if ids & {'URATE','LIVER_CHRONIC','BILIARY'}:excluded_categories.add('ORGAN')
    if 'DIABETES_CAT' in ids:excluded_categories.add('STARCH')
    if 'CALCIUM_OXALATE' in ids:policy['exclude_ids']=['FDC_169967'] # cooked spinach
    if 'GROWTH' in stage and ids & {'CKD','OBESITY','PANCREATITIS_DOG','HYPERLIPIDEMIA'}:reasons.append('GROWTH_DISEASE_TARGET_CONFLICT')
    if pet['muscle_condition'] not in {'NORMAL','UNKNOWN'} or pet['weight_trend']=='LOSING' or pet['bcs']<4:reasons.append('WEIGHT_OR_MUSCLE_LOSS_NEEDS_INDIVIDUAL_PLAN')
    unsupported=set(advice['recipe_constraint_requirements']) & NUMERICAL_DISEASE_ACTIONS-HANDLED
    reasons.extend('DISEASE_SPECIFIC_PLAN_REQUIRED:'+x for x in sorted(unsupported))
    policy['excluded_categories']=sorted(excluded_categories)
    return bounds,daily,policy,reasons


def designFreshFoodRecipe(context,store,*,excluded=(),required=()):
    """Pure design operation; persistence and Recipe Version live in service 1.1."""
    return RecipeDesignEngine(store).design(context,excluded=excluded,required=required)['result']


class RecipeDesignEngine:
    def __init__(self,store):self.store=store

    def design(self,context,*,excluded=(),required=()):
        c,check,specs,warnings=normalize_context(context,self.store)
        p=check['engine_pet'];p['user_supplements']=specs
        goal=c['feeding_goal'];diet=c['current_diet_context'];full=goal=='COMPLETE_DIET'
        advice=disease_advice(p,self.store)
        raw={'pet':p,'recipe_status':'LIMITED_DATA','daily_foods':[],'supplements':[],'disease_advice':advice,'daily_care':advice['daily_care'],
             'reasons':[],'use_case':p['purpose'],'complete_diet':full,'consumer_executable':False,'meals_per_day':2,
             'data_hash':self.store.meta['data_content_sha256'],'solver_request':{'excluded':list(excluded),'required':list(required)},'feeding_notes':[]}
        internal={'context':c,'profile':check['normalized'],'specs':specs,'raw':raw,'target':None,'current_contributions':[],
                  'estimate':None,'eligible_foods':[],'warnings':warnings}
        def finish(status,reasons=()):
            raw['recipe_status']=status;raw['reasons']+=list(reasons)
            internal['result']=self._present(internal);return internal
        # 1. Automatic safety triage precedes goals, target, candidates and doses.
        if advice['status']!='PRACTICAL_CLEAR':return finish(advice['status'],advice['reasons'])
        try:stage,profile=lifecycle(p,self.store)
        except ValueError:return finish('PROFESSIONAL_REVIEW',['LIFE_STAGE_CONTEXT_REQUIRED'])
        if profile is None:return finish('PROFESSIONAL_REVIEW',['UNSUPPORTED_LIFE_STAGE'])
        if full:
            coverage=profile_coverage_issues(self.store.rows('requirements'),profile)
            if coverage:return finish('LIMITED_DATA',coverage)
        energy=energy_start(p,profile,self.store);maintenance=energy['DER_start_kcal'] or (energy.get('interval_kcal') or [None])[0]
        if maintenance is None:return finish('PROFESSIONAL_REVIEW',['ENERGY_MODEL_UNAVAILABLE'])
        bounds=active_bounds({'profile_id':profile,'pet':p,'disease_constraints':[]},self.store)
        bounds,daily,policy,reasons=disease_design(p,advice,bounds,maintenance,stage)
        raw.update(life_stage=stage,profile_id=profile,energy={**energy,'DER_start_kcal':daily},meals_per_day=3 if 'GROWTH' in stage else 2)
        if goal=='OCCASIONAL_MEAL':raw['meals_per_day']=1
        if reasons:return finish('PROFESSIONAL_REVIEW',reasons)
        if check['normalized']['body_condition'] is None:
            warnings.append(warning('BODY_CONDITION_ESTIMATED','体况未知，先按正常体况提供起始方案并复核。','body_condition'))
        estimate=estimate_current_intake(diet,daily,self.store);internal['estimate']=estimate
        if estimate['limited_context']:warnings.append(warning('LIMITED_CONTEXT','额外食物按喂食当天的保守热量额度预留；该额度不是实测摄入。','current_diet_context'))
        if full:warnings.append(warning('COMPLETE_DIET_REPLACES_MAIN_DIET','完整鲜食用于逐步替代原主粮；不要叠加原来一整天的主粮份量。','main_diet'))
        if not full and diet['main_diet'].get('is_complete') is not True:
            warnings.append(warning('MAIN_DIET_COMPLETENESS_UNKNOWN','可提供少量安全鲜食；其余饮食应为适合生命阶段的完整主粮，不能据此认定总日粮完整。','main_diet'))
        if not full and diet['current_supplements']:
            warnings.append(warning('CURRENT_SUPPLEMENTS_NOT_DUPLICATED','当前补剂单列，不因这份搭配餐新增维矿；未提供主粮营养标签时不声称验证了全天补剂总摄入。','current_supplements'))
        if full and estimate['extra_energy_allowance_kcal']>daily*.1+1e-8:
            return finish('LIMITED_DATA',['REDUCE_EXTRA_FOODS_BEFORE_COMPLETE_DIET'])
        if full and any(i.get('spec') and i.get('frequency','DAILY_SMALL') in {'OCCASIONAL','WEEKLY'} for i in diet['current_supplements']):
            return finish('LIMITED_DATA',['VARIABLE_SUPPLEMENT_SCHEDULE_REQUIRES_DAILY_PLAN'])
        # 5–7. Safety exclusions, structural categories and common Chinese foods.
        foods,rejected=source_candidates(p,stage,self.store,daily,set(excluded)|set(check['excluded_ingredients']),include_supplements=False)
        foods=[s for s in foods if s['category'] not in policy['excluded_categories'] and s['id'] not in policy.get('exclude_ids',[])]
        if 'PANCREATITIS_DOG' in advice['diseases'] or 'HYPERLIPIDEMIA' in advice['diseases']:
            foods=[s for s in foods if s['category'] not in {'MEAT','POULTRY','FISH','EGG','ORGAN'} or (s['values'].get('fat') or 0)<=10]
        preferred=set(c['food_preferences'].get('preferred_ingredient_ids',[]))
        for s in foods:
            if preferred:s['preference_penalty']+=0 if s['id'] in preferred else .1
            s['cost']+=0 if s['definition'].get('china_availability') in {'HIGH','COMMON','EASY'} else .1
        internal['eligible_foods']=foods
        raw['source_exclusions']=rejected
        # Existing labels and current amounts participate in the SAME solve.
        user,validation,errors=user_sources(p,stage,self.store,daily,bounds)
        if errors:return finish('LIMITED_DATA',errors)
        current_by_id={i['spec']['id']:i for i in diet['current_supplements'] if i.get('spec')}
        for s in user:
            d=s['definition'];s['supplement_type']=d['supplement_type'];item=current_by_id.get(d['id'])
            # Include total fish oil fat; EPA+DHA is only a subset of the oil.
            if d['supplement_type']=='OMEGA3_FISH_OIL':
                original=next(x for x in specs if x['id']==d['id'])
                oil=original.get('fish_oil_total_mg')
                if oil is not None:
                    per=original.get('serving_amount',1)
                    if original.get('serving_unit')=='mg':per*=.001
                    elif original.get('serving_unit')=='scoop':per*=original['grams_per_scoop']
                    fat=oil/1000/per*100
                    s['values']['fat']=max(s['values'].get('fat',0),fat);s['upper']['fat']=s['values']['fat']
            if item and item.get('daily_amount') is not None and not item.get('adjustment_allowed',False):
                amount=item['daily_amount'];require(amount<=s['cap']+1e-8,'CURRENT_SUPPLEMENT_EXCEEDS_LABEL_CAP')
                require(abs(amount/s['quantum']-round(amount/s['quantum']))<1e-7,'CURRENT_SUPPLEMENT_DOSE_NOT_MEASURABLE')
                s['fixed_dose']=amount
        known_current_energy=sum(s['energy_high']*(current_by_id[s['definition']['id']].get('daily_amount') or 0) for s in user if s['definition']['id'] in current_by_id)
        allowance=estimate['extra_energy_allowance_kcal']
        fresh_target=daily-allowance if full else max(0,daily*.1-allowance-known_current_energy)
        internal['target']={'daily_energy_kcal':daily,'fresh_food_energy_kcal':fresh_target,'life_stage':stage,'nutrient_constraints':[],
                            'disease_constraints':advice['recipe_constraint_requirements'],'design_policy':policy}
        raw['remaining_complete_food_energy_kcal']=None if full else max(0,daily-allowance-known_current_energy-fresh_target)
        if not full:
            return self._auxiliary(internal,foods,user,current_by_id,bounds,required,finish)
        if any(not i.get('spec') and i['supplement_type']!='OTHER' for i in diet['current_supplements']):return finish('LIMITED_DATA',['CURRENT_SUPPLEMENT_SPEC_REQUIRED_FOR_COMPLETE_DESIGN'])
        # Preserve absolute daily nutrient floors when reserving calories for extras
        # or reducing energy for overweight pets; extras receive no nutrient credit.
        bounds=[replace(b,minimum=b.minimum*maintenance/fresh_target) if b.minimum is not None and b.basis=='PER_1000_KCAL_ME' else b for b in bounds]
        internal['target']['nutrient_constraints']=[asdict(b) for b in bounds]
        guided=any(s['definition']['supplement_mode']=='LABEL_GUIDED' for s in user)
        if guided:
            # Keep established manufacturer-guided behavior, with an explicit
            # assurance level. CKD/low-fat cannot hide minerals behind a label.
            if advice['diseases']:return finish('LIMITED_DATA',['DISEASE_DESIGN_REQUIRES_QUANTIFIED_SUPPLEMENT_PANEL'])
            from .recipe_design_guidance import guided_bounds
            bounds=guided_bounds(bounds)
        # 8–10. First test food alone. Do not add organs beyond existing caps.
        solution=solve_reference(foods,bounds,fresh_target,required,species=p['species'],design_policy=policy)
        selected_sources=foods
        if solution['status']!='REFERENCE_PASS' or user:
            catalog,_=source_candidates({**p,'dislikes':[]},stage,self.store,daily,include_supplements=True)
            types={s['supplement_type'] for s in user}|{i['supplement_type'] for i in diet['current_supplements']}
            defaults=[]
            for s in catalog:
                if s['type']=='FOOD':continue
                s['supplement_type']=supplement_type(s,p['species'])
                if s['supplement_type'] in types or guided:continue
                if s['id']=='V1_FM_CANI_COOKING':s['required_food_categories']=['STARCH','VEGETABLE','OIL']
                # Renal direction never adds phosphorus-bearing mineral powder.
                if 'CKD' in advice['diseases'] and s['type']=='DEFINED_NUTRIENT_SOURCE' and (s['values'].get('phosphorus') or 0)>0:continue
                defaults.append(s)
            selected_sources=foods+user+defaults
            solution=solve_reference(selected_sources,bounds,fresh_target,required,species=p['species'],design_policy=policy)
        raw['solver']=solution
        if solution['status']!='REFERENCE_PASS':
            status='PROFESSIONAL_REVIEW' if advice['diseases'] or check['excluded_ingredients'] or required else 'LIMITED_DATA'
            return finish(status,solution.get('blockers') or ['DESIGN_UNRESOLVED'])
        raw['nutrition_audit']=solution['audit'];raw['nutrition_validation_level']='MANUFACTURER_GUIDED' if guided else 'FORMULA_CALCULATED'
        if guided:
            raw['nutrition_audit'].update(all_micronutrients_verified=False,scope='FOOD_CORE_PLUS_MANUFACTURER_GUIDANCE')
        self._materialize(internal,selected_sources,solution['grams'],current_by_id)
        raw['consumer_executable']=True
        return finish('RECOMMENDED_WITH_SUPPLEMENTS' if raw['supplements'] else 'RECOMMENDED')

    def _auxiliary(self,state,foods,user,current,bounds,required,finish):
        raw=state['raw'];p=raw['pet'];target=state['target']['fresh_food_energy_kcal'];goal=state['context']['feeding_goal']
        # Partial: a recurring protein + tolerated fiber portion. Occasional:
        # a single simple protein portion, never a miniature complete diet solve.
        allowed=[s for s in foods if s['category'] in {'MEAT','POULTRY','FISH','VEGETABLE'}]
        clinical=state['target']['design_policy'].get('minimize_nutrients',[])
        allowed.sort(key=lambda s:(s['preference_penalty'],tuple(s['values'][n]/s['energy_low'] for n in clinical),s['cost'],s['id']))
        selected=[s for s in allowed if s['id'] in required]
        if len(selected)!=len(set(required)):return finish('PROFESSIONAL_REVIEW',['REQUIRED_FOOD_UNAVAILABLE'])
        if not any(s['category']!='VEGETABLE' for s in selected):
            protein=next((s for s in allowed if s['category']!='VEGETABLE'),None)
            if protein:selected.append(protein)
        if goal=='PARTIAL_WITH_MAIN_DIET' and p['species']=='DOG' and not any(s['category']=='VEGETABLE' for s in selected):
            vegetable=next((s for s in allowed if s['category']=='VEGETABLE'),None)
            if vegetable:selected.append(vegetable)
        if not selected or not any(s['category']!='VEGETABLE' for s in selected):return finish('PROFESSIONAL_REVIEW',['NO_SAFE_PROTEIN_SOURCE'])
        grams={s['id']:s['quantum'] for s in selected}
        used=sum(grams[s['id']]*s['energy_high'] for s in selected)
        if used>target+1e-8:return finish('LIMITED_DATA',['EXTRA_ENERGY_BUDGET_EXHAUSTED'])
        protein=next(s for s in selected if s['category']!='VEGETABLE')
        grams[protein['id']]+=floor((target-used)/protein['energy_high']/protein['quantum'])*protein['quantum']
        energy=sum(s['energy_high']*grams[s['id']] for s in selected)
        # Only upper/disease screening applies to the fresh portion. Full-day
        # nutrient minimums are deliberately NOT enforced on a side dish.
        upper_bounds=[replace(b,minimum=None,dependency={}) for b in bounds if b.maximum is not None and b.basis!='RATIO']
        # Fixed existing supplements remain external to the cooked side dish.
        # Their calories have been reserved, and obvious known upper excesses
        # are checked against the whole-day allowance, never credited as zero.
        fixed=[s for s in user if s['definition']['id'] in current and current[s['definition']['id']].get('daily_amount')]
        fixed_grams={s['id']:current[s['definition']['id']]['daily_amount'] for s in fixed}
        for b in upper_bounds:
            if b.basis=='PER_1000_KCAL_ME' and b.maximum and fixed:
                subtotal=sum((s['upper'].get(b.nutrient) or 0)*fixed_grams[s['id']]/100 for s in fixed)
                subtotal+=sum((s['upper'].get(b.nutrient) or 0)*grams[s['id']]/100 for s in selected)
                if subtotal>b.maximum*state['target']['daily_energy_kcal']/1000+1e-8:
                    return finish('LIMITED_DATA',['CURRENT_SUPPLEMENT_KNOWN_UPPER_EXCESS:'+b.nutrient])
        audit=audit_reference(selected,upper_bounds,grams,energy)
        if not audit['pass']:return finish('PROFESSIONAL_REVIEW',['AUXILIARY_DISEASE_OR_UPPER_CONSTRAINT_FAILED'])
        raw.update(nutrition_audit=audit,nutrition_validation_level='AUXILIARY_FOOD_ONLY',auxiliary_energy_kcal=energy,
                   solver={'food_amount_ranges':{},'rounding_reaudited':True},consumer_executable=True)
        raw['remaining_complete_food_energy_kcal']+=target-energy
        self._materialize(state,selected,grams,{})
        for s in user:
            d=s['definition'];item=current.get(d['id'])
            if item:state['current_contributions'].append(self._contribution(s,item,item.get('daily_amount'),'KEEP_EXTERNAL_EXISTING_PLAN'))
        raw['feeding_notes']=['鲜食与其他零食共享每日不超过10%的热量额度；从原主粮中扣除对应热量。','此份鲜食不替代长期完整主粮，不额外叠加完整维矿体系。']
        if goal=='OCCASIONAL_MEAL':raw['feeding_notes'].append('这是一份偶尔改善伙食的小餐；当天其余营养仍由完整主粮承担，不替代全天口粮。')
        return finish('RECOMMENDED')

    def _contribution(self,s,item,dose,action=None):
        before=item.get('daily_amount');d=s['definition']
        return {'user_spec_id':d['id'],'supplement_type':s['supplement_type'],'previous_daily_amount':before,'designed_daily_amount':dose,
                'dose_unit':s['unit'],'action':action or ('KEEP' if before==dose else 'CANCEL' if dose==0 else 'SET_CALCULATED_DOSE' if before is None else 'REDUCE' if dose<before else 'ADJUST'),
                'known_nutrients':{} if dose is None else {n:v*dose/100 for n,v in s['values'].items() if v is not None},
                'energy_kcal_interval':None if dose is None else [s['energy_low']*dose,s['energy_high']*dose]}

    def _materialize(self,state,sources,grams,current):
        raw=state['raw']
        for s in sources:
            g=grams.get(s['id'],0);d=s['definition']
            if s['type']!='FOOD' and d.get('id') in current:state['current_contributions'].append(self._contribution(s,current[d['id']],g))
            if not g:continue
            if s['type']=='FOOD':
                raw['daily_foods'].append({'ingredient_id':s['id'],'name_zh':d['name_zh'],'grams_cooked':g,'display_grams':g,'food_state':d['food_state'],'source_id':d['source_id'],'energy_reference_kcal':s['energy_low']*g})
            else:
                is_user=s['id'].startswith('USER:')
                raw['supplements'].append({'supplement_id':s['id'],'user_spec_id':d.get('id'),'supplement_type':s['supplement_type'],
                    'product_name':d['product_name'],'daily_amount':g,'unit':s['unit'],'source_id':'USER_LABEL:'+d['id'] if is_user else d['source_id'],
                    'practical_usable':True,'division_allowed':d.get('division_allowed',False),'required_measurement_increment':s['quantum'],
                    'addition_instruction':d.get('addition_instruction','按指定标签，临喂前加入冷却的食物。'),'addition_source_id':d.get('addition_source_id','PRACTICAL_PROCESS_POLICY'),
                    'spec_hash':d.get('spec_hash',digest(d)),'specification':deepcopy(d),'origin':'CURRENT_SUPPLEMENT' if d.get('id') in current else 'USER_AVAILABLE' if is_user else 'VERIFIED_CATALOG_REFERENCE',
                    'energy_kcal_interval':[s['energy_low']*g,s['energy_high']*g]})
        raw['recipe_hash']=digest({'foods':raw['daily_foods'],'supplements':raw['supplements'],'context':state['context'],'data_hash':raw['data_hash']})

    def _present(self,state):
        raw=state['raw'];c=state['context'];goal=c['feeding_goal'];target=state['target'];status=raw['recipe_status']
        defs=self.store.keyed('ingredients','ingredient_id');components=[];alternatives=[]
        for row in raw['daily_foods']:
            iid=row['ingredient_id'];d=defs[iid];typ=COMPONENTS[d['food_category']]
            options=[{'ingredient_id':s['id'],'display_name':s['definition']['name_zh'],'requires_whole_recipe_recalculation':True} for s in sorted(state['eligible_foods'],key=lambda s:(s['preference_penalty'],s['cost'],s['id'])) if s['id']!=iid and COMPONENTS[s['category']]==typ][:5]
            amount=row['grams_cooked'];span=raw.get('solver',{}).get('food_amount_ranges',{}).get(iid,{'amount_min_g':amount,'amount_max_g':amount})
            components.append({'component_type':typ,'ingredient_id':iid,'display_name':d['name_zh'],'amount_g':amount,**{k:span[k] for k in ('amount_min_g','amount_max_g')},
                'purpose':[PURPOSES[typ]],'replaceable':bool(options),'replacement_options':options,'weight_basis':d['weight_basis'],'food_state':d['food_state'],'portion_basis':'EDIBLE_WEIGHT',
                'china_availability':d['china_availability'],'cost_level':d['cost_level'],'preparation_hint':d['cooking_method_id']})
            alternatives.append({'source_ingredient_id':iid,'options':options,'requires_whole_recipe_recalculation':True})
        adaptations=[{'disease_id':d['disease_id'],'display_name':d['name_zh'],'classification':'DISEASE_ADAPTED_RECIPE',
                      'design_changes':d['adjustments'],'explanation':d['food_direction'],'source_id':d['source_id'],'numerical_treatment_prescription':False} for d in raw['disease_advice'].get('disease_details',[])]
        total_energy=sum(f['energy_reference_kcal'] for f in raw['daily_foods'])+sum(s['energy_kcal_interval'][1] for s in raw['supplements'])
        supp=[{'supplement_type':s['supplement_type'],'user_spec_id':s['user_spec_id'],'product_reference_id':s['supplement_id'],'display_name':s['product_name'],
               'daily_amount':s['daily_amount'],'dose_unit':s['unit'],'purpose':[SUPPLEMENT_PURPOSES[s['supplement_type']]],'origin':s['origin'],'spec_hash':s['spec_hash'],
               'specification':s['specification'],'product_substitution_requires_recalculation':True,'addition_instruction':s['addition_instruction']} for s in raw['supplements']]
        warnings=list(state['warnings'])
        warnings.append(warning('REFERENCE_DATA_SCOPE','食材采用代表值、补剂采用明确标签；不是实测完整日粮或疾病治疗处方认证。'))
        if any(s['origin']=='VERIFIED_CATALOG_REFERENCE' for s in raw['supplements']):warnings.append(warning('EXACT_PRODUCT_SPEC_REQUIRED','补剂剂量仅适用于列明的可追溯产品规格；换用自购产品须输入标签后重算。','supplements'))
        if adaptations:warnings.append(warning('DISEASE_ADAPTED_NOT_TREATMENT','疾病名称用于通用配方适配，不代表精准治疗处方。','diseases'))
        full=goal=='COMPLETE_DIET'
        return {'recipe_summary':{'daily_total_g':sum(x['amount_g'] for x in components),'amount_basis':'FOOD_ONLY_SUPPLEMENTS_SEPARATE',
                    'estimated_energy_kcal':total_energy,'feeding_goal':goal,'meals_per_day':raw['meals_per_day'],'recipe_status':status,'recipe_kind':KINDS[goal],
                    'design_classification':'DISEASE_ADAPTED_RECIPE' if adaptations else 'HEALTHY_RECIPE','executable':raw['consumer_executable']},
                'recipe_components':components,'supplements':supp,'replacement_options':alternatives,'disease_adaptations':adaptations,'warnings':warnings,
                'nutrition_explanation':{'ingredient_reasons':[{'ingredient_id':x['ingredient_id'],'explanation':x['purpose']} for x in components],
                    'supplement_reasons':[{'supplement_type':s['supplement_type'],'explanation':s['purpose']} for s in supp],
                    'current_supplement_contributions':state['current_contributions'],'validation_level':raw.get('nutrition_validation_level'),
                    'nutrition_audit':raw.get('nutrition_audit'),'disease_design_policy':None if target is None else target['design_policy'],
                    'daily_energy_target_kcal':None if target is None else target['daily_energy_kcal'],'complete_balanced_claim':False,
                    'all_micronutrients_verified':False if raw.get('nutrition_validation_level')=='MANUFACTURER_GUIDED' else None},
                'fresh_food_share':{'recommended_energy_share':None if not target else total_energy/target['daily_energy_kcal'],
                    'maximum_extra_energy_share':None if full else .1,'remaining_main_diet_energy_kcal':raw.get('remaining_complete_food_energy_kcal'),
                    'extra_energy_allowance_kcal':None if state['estimate'] is None else state['estimate']['extra_energy_allowance_kcal'],
                    'main_diet_complete':c['current_diet_context']['main_diet'].get('is_complete'),'share_basis':'FEEDING_DAY'},
                'status':status,'errors':[],'reason_codes':raw['reasons'],'blocking_reasons':raw['disease_advice'].get('acute_red_flags',[]),
                'calculation_metadata':{'whole_recipe_recalculated':True,'input_hash':digest({'context':c,**raw['solver_request']}),'rounding_reaudited':raw.get('solver',{}).get('rounding_reaudited',False)}}
