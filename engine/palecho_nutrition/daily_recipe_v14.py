"""API 1.4 food preparation advice; original solver and advanced layer unchanged.

Micronutrient/taurine/EPA-DHA completion is an explicit reminder scope, not a
complete-diet pass. Energy, food safety, disease upper limits and food-core
requirements still go through the existing rounded solver and audit.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from .daily_recipe_v13 import DailyRecipeEngine as AdvancedDailyRecipeEngine
from .daily_profile_v13 import normalize_daily_profile
from .daily_disease_v13 import daily_disease_advice, daily_disease_design
from .freshfood_contract import require, warning
from .profile import lifecycle, energy_start
from .runtime import active_bounds
from .requirements import profile_coverage_issues
from .practical_math import solve_reference, audit_reference
from .practical_sources import source_candidates
from .nutrient_reminders import reminder_food_bounds, nutrient_reminders, SCOPE_NOTE

ENGINE_VERSION='freshfood-reminder-1.4.0'
ADVANCED_SUPPLEMENT_LAYER='AVAILABLE'


class DailyRecipeEngine(AdvancedDailyRecipeEngine):
    # Versioned policy hooks; 1.4 defaults retain its frozen behavior.
    def _normalize_profile(self, profile):
        return normalize_daily_profile(profile, self.store)

    def _energy_start(self, pet, requirement_profile):
        return energy_start(pet, requirement_profile, self.store)

    def _source_candidates(self, pet, stage, daily, excluded):
        return source_candidates(pet, stage, self.store, daily, excluded, include_supplements=False)

    def _disease_design(self, pet, advice, bounds, energy, stage):
        return daily_disease_design(pet, advice, bounds, energy, stage)

    def _food_bounds(self, bounds, pet):
        return reminder_food_bounds(bounds)

    def _design_once(self,profile,*,specs=(),excluded=(),required=(),energy_factor_override=None):
        normalized,check,warnings=self._normalize_profile(profile)
        require(not specs, 'ADVANCED_SUPPLEMENT_LAYER_USE_API_1_3', 'supplements')
        pet=deepcopy(check['engine_pet']);specs=[]
        advice=daily_disease_advice(pet,self.store)
        raw={'pet':pet,'recipe_status':'NO_SAFE_RECIPE','daily_foods':[],'supplements':[],
             'disease_advice':advice,'daily_care':advice.get('daily_care',{}),'reasons':[],
             'use_case':'DAILY_FRESH_FOOD_RECIPE','complete_diet':False,'consumer_executable':False,
             'meals_per_day':2,'data_hash':self.store.meta['data_content_sha256'],
             'solver_request':{'excluded':sorted(excluded),'required':sorted(required)},'feeding_notes':[]}
        state={'profile':normalized,'specs':specs,'raw':raw,'target':None,'eligible_foods':[],
               'warnings':warnings,'single_component_reason':None,'pending_supplements':[]}
        def finish(status,reasons=()):
            raw['recipe_status']=status;raw['reasons']+=list(reasons)
            merge=deepcopy(raw['disease_advice'].get('rule_merge',{}))
            solved=status in {'RECOMMENDED','RECOMMENDED_WITH_SUPPLEMENTS'}
            merge.update(status='MERGED_AND_SOLVED' if solved else status,
                         whole_recipe_check='PASSED_FOOD_CORE_CHECK_NOT_COMPLETE_NUTRITION' if solved else 'NOT_PASSED',
                         reason_codes=list(raw['reasons']))
            for decision in merge.get('compatible_combinations',[]):
                decision['status']='PASSED_FOOD_CORE_CHECK_NOT_COMPLETE_NUTRITION' if solved else status
            raw['disease_advice']['rule_merge']=merge
            if state['target'] is not None:state['target']['design_policy']['rule_merge']=deepcopy(merge)
            state['result']=self._present(state)
            return state
        # Safety screening precedes all energy targets and dispensing decisions.
        if advice['status']!='PRACTICAL_CLEAR':return finish(advice['status'],advice.get('reasons',[]))
        require(normalized.get('body_condition') is not None, 'BODY_CONDITION_REQUIRED', 'body_condition')
        try:stage,requirement_profile=lifecycle(pet,self.store)
        except ValueError:
            require(False, 'MISSING_GROWTH_INFORMATION' if pet['species']=='DOG' and not pet.get('expected_adult_weight_kg') else 'LIFE_STAGE_CONTEXT_REQUIRED', 'expected_adult_weight_kg')
        require(requirement_profile is not None, 'UNSUPPORTED_LIFE_STAGE', 'life_stage')
        require(not (pet['species']=='DOG' and 'GROWTH' in stage and not pet.get('expected_adult_weight_kg')),
                'MISSING_GROWTH_INFORMATION', 'expected_adult_weight_kg')
        coverage=profile_coverage_issues(self.store.rows('requirements'),requirement_profile)
        require(not coverage, 'NUTRIENT_REQUIREMENTS_UNAVAILABLE', 'life_stage', ','.join(coverage))
        try:energy=self._energy_start(pet,requirement_profile)
        except ValueError:
            require(False, 'GROWTH_ENERGY_CONTEXT_INVALID' if 'GROWTH' in stage else 'ENERGY_MODEL_UNAVAILABLE', 'expected_adult_weight_kg')
        maintenance=energy['DER_start_kcal'] or (energy.get('interval_kcal') or [None])[0]
        require(maintenance is not None, 'ENERGY_MODEL_UNAVAILABLE', 'life_stage')
        bounds=active_bounds({'profile_id':requirement_profile,'pet':pet,'disease_constraints':[]},self.store)
        bounds,daily,policy,reasons=self._disease_design(pet,advice,bounds,maintenance,stage)
        if energy_factor_override is not None:
            daily = maintenance * energy_factor_override
            policy['body_condition_strategy'].update(energy_factor=energy_factor_override, daily_energy_kcal=daily)
        composition={'version':'DAILY_RECIPE_COMPOSITION_1.4','target_component_count':policy.get('component_count_range',[3,6] if pet['species']=='DOG' else [2,5]),
                     'constraint_kind':'SOFT_OBJECTIVE','main_component_excluded_categories':['OIL','ORGAN'],
                     'species_structure':'ANIMAL_PROTEIN_WITH_OPTIONAL_ENERGY_AND_FIBER' if pet['species']=='DOG' else 'ANIMAL_PROTEIN_PRIORITY_LOW_CARBOHYDRATE',
                     'fixed_food_ratios':False}
        policy['recipe_composition_policy']=composition
        raw.update(life_stage=stage,profile_id=requirement_profile,energy={**energy,'DER_start_kcal':daily},
                   meals_per_day=3 if 'GROWTH' in stage else 2)
        # Reduced calories retain the original daily nutritional minimums.
        if daily<maintenance:
            bounds=[replace(b,minimum=b.minimum*maintenance/daily) if b.minimum is not None and b.basis=='PER_1000_KCAL_ME' else b for b in bounds]
        state['reference_bounds']=list(bounds)
        if policy.get('check_active_nutrient_completion_capacity'):
            policy['completion_reference_bounds']=[asdict(b) for b in bounds]
        bounds=self._food_bounds(bounds,pet)
        policy['scope']='PRACTICAL_FOOD_CORE_NOT_COMPLETE_NUTRITION'
        state['target']={'daily_energy_kcal':daily,'fresh_food_energy_kcal':daily,'life_stage':stage,
                         'nutrient_constraints':[asdict(b) for b in bounds],
                         'disease_constraints':advice.get('recipe_constraint_requirements',[]),'design_policy':policy}
        # Merged contradictions remain in the solver bounds; no ordinary-state gate.
        raw['merge_diagnostics']=reasons
        foods,rejected=self._source_candidates(pet,stage,daily,set(excluded)|set(check['excluded_ingredients']))
        foods=[s for s in foods if s['category'] not in policy.get('excluded_categories',[]) and s['id'] not in policy.get('exclude_ids',[])]
        if set(advice.get('diseases',[]))&{'PANCREATITIS_DOG','HYPERLIPIDEMIA'}:
            foods=[s for s in foods if s['category'] not in {'MEAT','POULTRY','FISH','EGG','ORGAN'} or (s['values'].get('fat') or 0)<=10]
        for source in foods:
            source['cost']+=0 if source['definition'].get('china_availability') in {'HIGH','COMMON','EASY','COMMON_USER_PRIORITY'} else .1
        state['eligible_foods']=foods;raw['source_exclusions']=rejected
        solution=solve_reference(foods,bounds,daily,required,species=pet['species'],design_policy=policy)
        raw['solver_attempts']=[{'phase':'PRACTICAL_FOOD_CORE','status':solution['status'],
                                'reason_codes':solution.get('blockers',[])}]
        raw['solver']=solution
        require(solution['status']!='SOLVER_UNRESOLVED','SOLVER_NOT_COMPLETED','recipe')
        if solution['status']!='REFERENCE_PASS':
            return finish('NO_SAFE_RECIPE',solution.get('blockers') or ['NO_FEASIBLE_RECIPE_WITH_AVAILABLE_SOURCES'])
        raw['nutrition_audit']=solution['audit']
        raw['nutrition_validation_level']='PRACTICAL_FOOD_CORE'
        raw['nutrition_audit'].update(scope='FOOD_CORE_ONLY',all_micronutrients_verified=False,complete_balanced_claim=False)
        state['food_reference_audit']=audit_reference(foods,state['reference_bounds'],solution['grams'],daily)
        raw['food_reference_audit']=deepcopy(state['food_reference_audit'])
        self._materialize(state,foods,solution['grams'])
        main=[s for s in foods if solution['grams'].get(s['id'],0)>0 and s['category'] not in {'OIL','ORGAN'}]
        if len(main)==1:
            state['single_component_reason']='MEDICAL_LIMITATION' if advice['diseases'] else 'RESTRICTION_LIMITATION' if check['excluded_ingredients'] or excluded else 'NO_SAFE_ALTERNATIVE'
        raw['consumer_executable']=True
        return finish('RECOMMENDED')

    def _present(self,state):
        result=super()._present(state)
        for field in ('required_supplements','supplements'):
            result.pop(field,None)
        result.update(presentation_mode='PRACTICAL_REMINDER',
                      advanced_supplement_layer=ADVANCED_SUPPLEMENT_LAYER,
                      nutrition_scope='FOOD_CORE_WITH_NUTRIENT_REMINDERS',
                      complete_balanced_claim=False,
                      nutrient_reminders=nutrient_reminders(state),
                      long_term_feeding_note=SCOPE_NOTE)
        result['daily_feeding_plan']['amount_basis']='FOOD_ONLY'
        result['daily_feeding_plan']['notes']=list(dict.fromkeys(result['daily_feeding_plan']['notes']+[SCOPE_NOTE]))
        result['recipe_summary'].update(amount_basis='FOOD_ONLY',complete_balanced_claim=False,
                                       design_classification='PRACTICAL_FAMILY_FOOD_ADVICE')
        for item in result['warnings']:
            if item['code']=='REFERENCE_DATA_SCOPE':
                item['message']='食材采用代表值；此处核对食物部分，不代表已完成全部营养来源的核算。'
            elif item['code']=='DISEASE_ADAPTED_NOT_TREATMENT':
                item['message']='疾病信息用于日常饮食适配，不能替代个体诊疗安排。'
        result['nutrition_explanation']=[x for x in result['nutrition_explanation'] if x['kind']!='SUPPLEMENT']
        for item in result['nutrition_explanation']:
            if item['kind']=='NUTRITION_AUDIT':
                item.update(validation_level='PRACTICAL_FOOD_CORE',all_micronutrients_verified=False,
                            complete_balanced_claim=False,explanation=SCOPE_NOTE)
        # Detailed completion gaps remain internal diagnostic evidence; the V1
        # contract does not include quantities or implied doses for supplements.
        if result['nutrition_audit']:
            result['nutrition_audit']={k:v for k,v in result['nutrition_audit'].items() if k!='rows'}
        return result
