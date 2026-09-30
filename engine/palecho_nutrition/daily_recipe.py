"""Pet-only, offline daily recipe design for FreshFood API 1.2.

The independent entry point has no diet-context adapter or feeding-mode branch.
Food and declared supplements share the same rounded, independently audited
solve. Product specifications are optional inputs to a subsequent redesign.
"""
from copy import deepcopy
from dataclasses import asdict, replace

from .daily_profile import normalize_daily_profile
from .daily_disease import daily_disease_advice, daily_disease_design
from .freshfood_contract import require, warning
from .profile import lifecycle, energy_start
from .runtime import active_bounds
from .requirements import profile_coverage_issues
from .practical import digest
from .practical_sources import source_candidates
from .practical_math import solve_reference
from .user_supplements import user_sources, validate_spec, selection_guides
from .recipe_design import COMPONENTS, PURPOSES, SUPPLEMENT_PURPOSES, supplement_type

ENGINE_VERSION='freshfood-daily-1.2.0'
CARE_FIELDS=('foods_to_limit','foods_to_avoid','foods_preferred','hydration_notes',
             'feeding_notes','weight_monitoring','appetite_monitoring','stool_monitoring','red_flags')


def designDailyFreshFoodRecipe(profile,store,*,specs=(),excluded=(),required=()):
    return DailyRecipeEngine(store).design(profile,specs=specs,excluded=excluded,required=required)['result']


class DailyRecipeEngine:
    def __init__(self,store):self.store=store

    def design(self,profile,*,specs=(),excluded=(),required=()):
        normalized,check,warnings=normalize_daily_profile(profile,self.store)
        pet=deepcopy(check['engine_pet']);specs=deepcopy(list(specs));ids=set();types=set()
        for spec in specs:
            validated=validate_spec(spec,self.store,pet['species'])
            require(validated['status']!='INVALID','INVALID_PRODUCT_SPEC','supplements',','.join(validated['errors']))
            require(spec['id'] not in ids and spec['supplement_type'] not in types,'DUPLICATE_SUPPLEMENT_TYPE_OR_ID')
            ids.add(spec['id']);types.add(spec['supplement_type'])
        pet['user_supplements']=specs
        advice=daily_disease_advice(pet,self.store)
        raw={'pet':pet,'recipe_status':'LIMITED_DATA','daily_foods':[],'supplements':[],
             'disease_advice':advice,'daily_care':advice.get('daily_care',{}),'reasons':[],
             'use_case':'DAILY_FRESH_FOOD_RECIPE','complete_diet':True,'consumer_executable':False,
             'meals_per_day':2,'data_hash':self.store.meta['data_content_sha256'],
             'solver_request':{'excluded':sorted(excluded),'required':sorted(required)},'feeding_notes':[]}
        state={'profile':normalized,'specs':specs,'raw':raw,'target':None,'eligible_foods':[],
               'warnings':warnings,'single_component_reason':None,'pending_supplements':[]}
        def finish(status,reasons=()):
            raw['recipe_status']=status;raw['reasons']+=list(reasons)
            merge=deepcopy(raw['disease_advice'].get('rule_merge',{}))
            solved=status in {'RECOMMENDED','RECOMMENDED_WITH_SUPPLEMENTS'}
            merge.update(status='MERGED_AND_SOLVED' if solved else status,
                         whole_recipe_check='PASSED_WHOLE_RECIPE_CHECK' if solved else 'NOT_PASSED',
                         reason_codes=list(raw['reasons']))
            for decision in merge.get('compatible_combinations',[]):
                decision['status']='PASSED_WHOLE_RECIPE_CHECK' if solved else status
            raw['disease_advice']['rule_merge']=merge
            if state['target'] is not None:state['target']['design_policy']['rule_merge']=deepcopy(merge)
            state['result']=self._present(state)
            return state
        # Safety screening precedes all energy targets and dispensing decisions.
        if advice['status']!='PRACTICAL_CLEAR':return finish(advice['status'],advice.get('reasons',[]))
        if normalized.get('body_condition') is None:return finish('PROFESSIONAL_REVIEW',['BODY_CONDITION_REQUIRED'])
        try:stage,requirement_profile=lifecycle(pet,self.store)
        except ValueError:return finish('PROFESSIONAL_REVIEW',['LIFE_STAGE_CONTEXT_REQUIRED'])
        if requirement_profile is None:return finish('PROFESSIONAL_REVIEW',['UNSUPPORTED_LIFE_STAGE'])
        coverage=profile_coverage_issues(self.store.rows('requirements'),requirement_profile)
        if coverage:return finish('PROFESSIONAL_REVIEW',coverage)
        try:energy=energy_start(pet,requirement_profile,self.store)
        except ValueError:return finish('PROFESSIONAL_REVIEW',['GROWTH_ENERGY_CONTEXT_REQUIRED' if 'GROWTH' in stage else 'ENERGY_MODEL_UNAVAILABLE'])
        maintenance=energy['DER_start_kcal'] or (energy.get('interval_kcal') or [None])[0]
        if maintenance is None:return finish('PROFESSIONAL_REVIEW',['ENERGY_MODEL_UNAVAILABLE'])
        bounds=active_bounds({'profile_id':requirement_profile,'pet':pet,'disease_constraints':[]},self.store)
        bounds,daily,policy,reasons=daily_disease_design(pet,advice,bounds,maintenance,stage)
        composition={'version':'DAILY_RECIPE_COMPOSITION_1.2','target_component_count':[3,6] if pet['species']=='DOG' else [2,5],
                     'constraint_kind':'SOFT_OBJECTIVE','main_component_excluded_categories':['OIL','ORGAN'],
                     'species_structure':'ANIMAL_PROTEIN_WITH_OPTIONAL_ENERGY_AND_FIBER' if pet['species']=='DOG' else 'ANIMAL_PROTEIN_PRIORITY_LOW_CARBOHYDRATE',
                     'fixed_food_ratios':False}
        policy['recipe_composition_policy']=composition
        raw.update(life_stage=stage,profile_id=requirement_profile,energy={**energy,'DER_start_kcal':daily},
                   meals_per_day=3 if 'GROWTH' in stage else 2)
        # Reduced calories retain the original daily nutritional minimums.
        if daily<maintenance:
            bounds=[replace(b,minimum=b.minimum*maintenance/daily) if b.minimum is not None and b.basis=='PER_1000_KCAL_ME' else b for b in bounds]
        state['target']={'daily_energy_kcal':daily,'fresh_food_energy_kcal':daily,'life_stage':stage,
                         'nutrient_constraints':[asdict(b) for b in bounds],
                         'disease_constraints':advice.get('recipe_constraint_requirements',[]),'design_policy':policy}
        if reasons:return finish('PROFESSIONAL_REVIEW',reasons)
        foods,rejected=source_candidates(pet,stage,self.store,daily,set(excluded)|set(check['excluded_ingredients']),include_supplements=False)
        foods=[s for s in foods if s['category'] not in policy.get('excluded_categories',[]) and s['id'] not in policy.get('exclude_ids',[])]
        if set(advice.get('diseases',[]))&{'PANCREATITIS_DOG','HYPERLIPIDEMIA'}:
            foods=[s for s in foods if s['category'] not in {'MEAT','POULTRY','FISH','EGG','ORGAN'} or (s['values'].get('fat') or 0)<=10]
        for source in foods:
            source['cost']+=0 if source['definition'].get('china_availability') in {'HIGH','COMMON','EASY'} else .1
        state['eligible_foods']=foods;raw['source_exclusions']=rejected
        # A generic fish-derived carrier does not identify its fish species.
        # Preserve species-specific food restrictions, but require a compatible
        # carrier declaration for supplements when a fish allergy is present.
        supplement_pet=deepcopy(pet)
        fish_allergens={tag for item in self.store.rows('ingredients') if item['food_category']=='FISH'
                        for tag in (item['allergen_tags'] or '').split(';') if tag}
        if fish_allergens&set(pet['allergies']):supplement_pet['allergies']=sorted(set(pet['allergies'])|{'FISH'})
        user,validation,errors=user_sources(supplement_pet,stage,self.store,daily,bounds)
        if errors:return finish('PROFESSIONAL_REVIEW',errors)
        for source in user:
            d=source['definition'];source['supplement_type']=d['supplement_type']
            if d['supplement_type']=='OMEGA3_FISH_OIL':
                original=next(s for s in specs if s['id']==d['id'])
                per=original.get('serving_amount',1)
                if original.get('serving_unit')=='mg':per*=.001
                elif original.get('serving_unit')=='scoop':per*=original['grams_per_scoop']
                if original.get('fish_oil_total_mg') is not None:
                    fat=original['fish_oil_total_mg']/1000/per*100
                    source['values']['fat']=max(source['values'].get('fat',0),fat)
                else:
                    # Declared EPA+DHA is a lower fat contribution, never the
                    # whole oil concentration or an upper bound on total fat.
                    source['values']['fat']=max(source['values'].get('fat',0),source['values'].get('epa_dha',0))
                if source['unit']=='g':fat_upper=100.
                elif original.get('product_mass_g_per_serving') is not None:fat_upper=original['product_mass_g_per_serving']/per*100
                elif original.get('pure_oil') is True and original.get('fish_oil_total_mg') is not None:fat_upper=original['fish_oil_total_mg']/1000/per*100
                elif source['upper'].get('fat') is not None:fat_upper=source['upper']['fat']
                else:
                    return finish('LIMITED_DATA',['FISH_OIL_TOTAL_MASS_REQUIRED_FOR_FAT_SCREEN'])
                source['upper']['fat']=max(source['values']['fat'],fat_upper)
                source['provenance']['fat']={'source_id':'USER_LABEL:'+d['id'],'evidence_type':'USER_CONFIRMED_LABEL_DECLARED',
                    'lower_method':'DECLARED_TOTAL_OIL_MASS' if original.get('fish_oil_total_mg') is not None else 'KNOWN_DECLARED_EPA_DHA_LOWER_CONTRIBUTION',
                    'upper_method':'PRODUCT_MASS_ENVELOPE_OR_DECLARED_TOTAL_FAT','actual_concentration':None}
                previous_energy=[source['energy_low'],source['energy_high']]
                source['energy_low']=max(source['energy_low'],9*source['values']['fat']/100)
                source['energy_high']=max(source['energy_high'],9*source['upper']['fat']/100,source['energy_low'])
                d['runtime_energy_screen']={'label_or_original_interval_kcal_per_unit':previous_energy,
                    'reference_interval_kcal_per_unit':[source['energy_low'],source['energy_high']],
                    'method':'NINE_KCAL_PER_G_KNOWN_FAT_LOWER_AND_TOTAL_PRODUCT_MASS_UPPER_ENVELOPE',
                    'actual_measured_energy':False,'label_zero_cannot_override_positive_declared_oil':True}
                if original.get('energy_kcal_per_serving') is not None and previous_energy[1]<source['energy_low']-1e-8:
                    warnings.append(warning('FISH_OIL_ENERGY_LABEL_CONFLICT_SCREENED',
                        '标签热量低于已声明脂肪的参考能量；使用明确的脂肪与产品质量能量包络重算，请复核标签。','required_supplements'))
        guided=any(s['definition']['supplement_mode']=='LABEL_GUIDED' for s in user)
        if guided:
            if advice.get('diseases'):return finish('PROFESSIONAL_REVIEW',['DISEASE_DESIGN_REQUIRES_QUANTIFIED_SUPPLEMENT_PANEL'])
            from .recipe_design_guidance import guided_bounds
            bounds=guided_bounds(bounds)
        # Food first: add supplements only when food lacks a feasible audited
        # solution, or the owner has provided a product for the new calculation.
        solution=solve_reference(foods,bounds,daily,required,species=pet['species'],design_policy=policy)
        sources=foods
        if solution['status']!='REFERENCE_PASS' or user:
            catalog,_=source_candidates({**supplement_pet,'dislikes':[]},stage,self.store,daily,include_supplements=True)
            defaults=[]
            for source in catalog:
                if source['type']=='FOOD':continue
                source['supplement_type']=supplement_type(source,pet['species'])
                if source['supplement_type'] in types or guided:continue
                if source['id']=='V1_FM_CANI_COOKING':source['required_food_categories']=['STARCH','VEGETABLE','OIL']
                if 'CKD' in advice.get('diseases',[]) and source['type']=='DEFINED_NUTRIENT_SOURCE' and (source['values'].get('phosphorus') or 0)>0:continue
                defaults.append(source)
            sources=foods+user+defaults
            solution=solve_reference(sources,bounds,daily,required,species=pet['species'],design_policy=policy)
        raw['solver']=solution
        if solution['status']!='REFERENCE_PASS':
            # A narrowly scoped diagnostic can identify the need for a product
            # label without fabricating a product matrix or publishing an
            # under-supplied meal. All other original constraints still apply.
            # An elastic diagnostic's arbitrary slack row is NOT evidence that
            # a particular supplement will repair an infeasible recipe.
            needs_epa=any(b.nutrient=='epa_dha' and b.minimum is not None and b.minimum>0 for b in bounds)
            has_epa_supplement=any(s['type']!='FOOD' and (s['values'].get('epa_dha') or 0)>0 for s in sources)
            if (solution['status']=='INFEASIBLE' and needs_epa and not has_epa_supplement
                    and 'OMEGA3_FISH_OIL' not in types and 'FISH' not in supplement_pet['allergies']):
                diagnostic_bounds=[replace(b,minimum=None,dependency={}) if b.nutrient=='epa_dha' else b for b in bounds]
                diagnostic=solve_reference(sources,diagnostic_bounds,daily,required,species=pet['species'],design_policy=policy)
                if diagnostic['status']=='REFERENCE_PASS':
                    raw['supplement_spec_diagnostic']={'nutrient_id':'epa_dha','removed_minimum_only':True,
                        'all_other_constraints_pass':True,'diagnostic_foods_released':False,
                        'product_suitability_and_dose_require_whole_recipe_recalculation':True}
                    state['pending_supplements']=['OMEGA3_FISH_OIL']
                    return finish('LIMITED_DATA',['SUPPLEMENT_PRODUCT_SPEC_REQUIRED:OMEGA3_FISH_OIL'])
            return finish('PROFESSIONAL_REVIEW',solution.get('blockers') or ['DESIGN_UNRESOLVED'])
        raw['nutrition_audit']=solution['audit'];raw['nutrition_validation_level']='MANUFACTURER_GUIDED' if guided else 'FORMULA_CALCULATED'
        if guided:raw['nutrition_audit'].update(all_micronutrients_verified=False,scope='FOOD_CORE_PLUS_MANUFACTURER_GUIDANCE')
        self._materialize(state,sources,solution['grams'])
        main=[s for s in sources if solution['grams'].get(s['id'],0)>0 and s['type']=='FOOD' and s['category'] not in {'OIL','ORGAN'}]
        if len(main)==1:
            state['single_component_reason']='MEDICAL_LIMITATION' if advice.get('diseases') else 'RESTRICTION_LIMITATION' if check['excluded_ingredients'] or excluded else 'NO_SAFE_ALTERNATIVE'
            warnings.append(warning('SINGLE_COMPONENT_RECIPE','在当前营养、安全、食材及可称量约束下主要食物仅一种；原因已明确记录。','recipe_components'))
        raw['consumer_executable']=True
        return finish('RECOMMENDED_WITH_SUPPLEMENTS' if raw['supplements'] else 'RECOMMENDED')

    def _materialize(self,state,sources,grams):
        raw=state['raw']
        for source in sources:
            amount=grams.get(source['id'],0);definition=source['definition']
            if not amount:continue
            if source['type']=='FOOD':
                raw['daily_foods'].append({'ingredient_id':source['id'],'name_zh':definition['name_zh'],'grams_cooked':amount,'display_grams':amount,
                    'food_state':definition['food_state'],'source_id':definition['source_id'],'energy_reference_kcal':source['energy_low']*amount})
            else:
                is_user=source['id'].startswith('USER:')
                raw['supplements'].append({'supplement_id':source['id'],'user_spec_id':definition.get('id'),'supplement_type':source['supplement_type'],
                    'product_name':definition['product_name'],'daily_amount':amount,'unit':source['unit'],
                    'source_id':'USER_LABEL:'+definition['id'] if is_user else definition['source_id'],
                    'practical_usable':True,'division_allowed':definition.get('division_allowed',False),'required_measurement_increment':source['quantum'],
                    'addition_instruction':definition.get('addition_instruction','按指定标签，临喂前加入冷却的食物。'),
                    'addition_source_id':definition.get('addition_source_id','PRACTICAL_PROCESS_POLICY'),
                    'spec_hash':definition.get('spec_hash',digest(definition)),'specification':deepcopy(definition),
                    'origin':'USER_AVAILABLE' if is_user else 'VERIFIED_CATALOG_REFERENCE',
                    'energy_kcal_interval':[source['energy_low']*amount,source['energy_high']*amount]})
        raw['recipe_hash']=digest({'foods':raw['daily_foods'],'supplements':raw['supplements'],'profile':state['profile'],
            'specs':state['specs'],'solver_request':raw['solver_request'],'data_hash':raw['data_hash']})

    def _present(self,state):
        raw=state['raw'];target=state['target'];definitions=self.store.keyed('ingredients','ingredient_id')
        components=[];alternatives=[];guides={g['supplement_type']:g for g in selection_guides(self.store)}
        for row in raw['daily_foods']:
            iid=row['ingredient_id'];definition=definitions[iid];kind=COMPONENTS[definition['food_category']];amount=row['grams_cooked']
            options=[{'ingredient_id':s['id'],'display_name':s['definition']['name_zh'],'requires_whole_recipe_recalculation':True}
                for s in sorted(state['eligible_foods'],key=lambda s:(s['preference_penalty'],s['cost'],s['id']))
                if s['id']!=iid and COMPONENTS[s['category']]==kind][:5]
            span=raw.get('solver',{}).get('food_amount_ranges',{}).get(iid,{'amount_min_g':amount,'amount_max_g':amount})
            components.append({'component_type':kind,'ingredient_id':iid,'display_name':definition['name_zh'],'amount_g':amount,
                'amount_min_g':span['amount_min_g'],'amount_max_g':span['amount_max_g'],'purpose':[PURPOSES[kind]],
                'replaceable':bool(options),'replacement_options':options,'weight_basis':definition['weight_basis'],'food_state':definition['food_state'],
                'portion_basis':'EDIBLE_WEIGHT','china_availability':definition['china_availability'],'cost_level':definition['cost_level'],
                'preparation_hint':definition['cooking_method_id']})
            alternatives.append({'source_ingredient_id':iid,'options':options,'requires_whole_recipe_recalculation':True})
        supplements=[]
        for source in raw['supplements']:
            reference=source['origin']=='VERIFIED_CATALOG_REFERENCE';kind=source['supplement_type']
            supplements.append({'supplement_type':kind,'user_spec_id':source['user_spec_id'],'product_reference_id':source['supplement_id'],
                'display_name':source['product_name'],'purpose':[SUPPLEMENT_PURPOSES[kind]],'selection_guide':guides.get(kind,{}),
                'daily_amount':source['daily_amount'],'calculated_dose':source['daily_amount'],'dose_unit':source['unit'],
                'origin':source['origin'],'spec_hash':source['spec_hash'],'specification':source['specification'],
                'user_spec_required':reference,'user_spec_status':'REFERENCE_PRODUCT_ONLY' if reference else 'PROVIDED',
                'need_status':'REQUIRED','dose_scope':'EXACT_REFERENCE_PRODUCT' if reference else 'USER_LABEL_CALCULATED',
                'product_substitution_requires_recalculation':True,'addition_instruction':source['addition_instruction']})
        for kind in state['pending_supplements']:
            supplements.append({'supplement_type':kind,'user_spec_id':None,'product_reference_id':None,
                'display_name':'提供 EPA / DHA 含量的鱼油产品标签','purpose':[SUPPLEMENT_PURPOSES[kind]],
                'selection_guide':guides.get(kind,{}),'daily_amount':None,'calculated_dose':None,'dose_unit':None,
                'origin':'POST_RECIPE_LABEL_REQUIRED','spec_hash':None,'specification':None,
                'user_spec_required':True,'user_spec_status':'NOT_PROVIDED','need_status':'REQUIRED_TO_CALCULATE',
                'dose_scope':'PENDING_WHOLE_RECIPE_RECALCULATION','product_substitution_requires_recalculation':True,
                'addition_instruction':None,'dose_pending_reason':'EPA_DHA_LABEL_REQUIRED_NO_UNVERIFIED_RECIPE_RELEASED'})
        adaptations=[]
        advice=raw['disease_advice']
        for disease in advice.get('disease_adaptations',advice.get('disease_details',[])):
            item={'disease_id':disease['disease_id'],'display_name':disease['name_zh'],
                  'classification':'DISEASE_ADAPTED_RECIPE','design_changes':disease.get('adjustments',[]),
                  'explanation':disease.get('food_direction',[]),'source_id':disease.get('source_id'),
                  'numerical_treatment_prescription':False}
            for field in CARE_FIELDS:item[field]=deepcopy(disease.get(field,advice.get(field,[])))
            item['nutrition_action_level']=disease.get('nutrition_action_level',disease.get('classification'))
            item['category']=disease.get('category')
            adaptations.append(item)
        total=sum(c['amount_g'] for c in components);meals=raw['meals_per_day']
        total_energy=sum(f['energy_reference_kcal'] for f in raw['daily_foods'])+sum(s['energy_kcal_interval'][1] for s in raw['supplements'])
        hydration=[]
        if target and target['design_policy'].get('retain_cooking_water'):
            hydration.append('按指定烹调和沥水方式称取熟食后，可按进食与饮水耐受另加清水增加湿润程度；清水不计入食材克重，不加入未核算的肉汤或浮油。')
        plan={'daily_total_food_g':total,'daily_food_g':total,'daily_total_g':total,'amount_basis':'FOOD_ONLY_SUPPLEMENTS_SEPARATE',
              'meals_per_day':meals,'food_g_per_meal':round(total/meals,1),'amount_per_meal_g':round(total/meals,1),
              'notes':raw['feeding_notes'],'hydration_notes':hydration}
        warnings=list(state['warnings'])+[warning('REFERENCE_DATA_SCOPE','食材采用代表值、补剂采用明确标签；不是实测完整日粮或疾病治疗处方认证。')]
        if any(s['user_spec_required'] for s in supplements):warnings.append(warning('SUPPLEMENT_SPEC_AFTER_RECIPE','配方生成后核对所购补剂标签；参考剂量仅适用于列明产品，换产品后重算。','required_supplements'))
        if adaptations:warnings.append(warning('DISEASE_ADAPTED_NOT_TREATMENT','疾病名称用于通用配方适配，不代表精准治疗处方。','diseases'))
        explanation=[{'kind':'INGREDIENT','ingredient_id':c['ingredient_id'],'explanation':c['purpose']} for c in components]
        explanation += [{'kind':'SUPPLEMENT','supplement_type':s['supplement_type'],'explanation':s['purpose']} for s in supplements]
        explanation.append({'kind':'NUTRITION_AUDIT','validation_level':raw.get('nutrition_validation_level'),
            'complete_balanced_claim':False,'all_micronutrients_verified':False if raw.get('nutrition_validation_level')=='MANUFACTURER_GUIDED' else None})
        if target:explanation.append({'kind':'DISEASE_POLICY','policy':target['design_policy']})
        return {'status':raw['recipe_status'],'recipe_kind':'DAILY_FRESH_FOOD_RECIPE','pet_summary':deepcopy(state['profile']),
            'daily_energy_target':None if target is None else {'kcal':target['daily_energy_kcal'],'unit':'kcal/day','life_stage':target['life_stage'],
                'source_id':raw['energy']['source_id'],'energy_strategy':target['design_policy'].get('energy_adjustment','LIFE_STAGE_STARTING_ESTIMATE')},
            'recipe_components':components,'required_supplements':supplements,'supplements':deepcopy(supplements),
            'disease_adaptations':adaptations,'nutrition_explanation':explanation,'nutrition_audit':raw.get('nutrition_audit'),
            'warnings':warnings,'replacement_options':alternatives,'daily_feeding_plan':plan,
            'single_component_reason':state['single_component_reason'],'recipe_composition_policy':None if target is None else target['design_policy']['recipe_composition_policy'],
            'recipe_summary':{'daily_total_g':total,'amount_basis':plan['amount_basis'],'estimated_energy_kcal':total_energy,
                'meals_per_day':meals,'recipe_status':raw['recipe_status'],'recipe_kind':'DAILY_FRESH_FOOD_RECIPE',
                'design_classification':'DISEASE_ADAPTED_RECIPE' if adaptations else 'HEALTHY_RECIPE','executable':raw['consumer_executable']},
            'errors':[],'reason_codes':raw['reasons'],'blocking_reasons':advice.get('acute_red_flags',[]),
            'calculation_metadata':{'whole_recipe_recalculated':True,'input_hash':digest({'profile':state['profile'],'specs':state['specs'],**raw['solver_request']}),
                'rounding_reaudited':raw.get('solver',{}).get('rounding_reaudited',False)}}
