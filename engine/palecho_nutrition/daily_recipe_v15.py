"""API 1.5: audited food design plus evidence-aware active-nutrient targets."""
from copy import deepcopy
from .daily_recipe_v14 import DailyRecipeEngine as ReminderEngine
from .daily_disease_v13 import daily_disease_design, body_strategy
from .nutrient_reminders import reminder_food_bounds
from .supplement_recommendations import nutrient_matrix, recommendations
from .recipe_consistency import check_recipe
from .recommendation_evidence import source_record
from .profile import energy_start

ENGINE_VERSION='freshfood-daily-1.5.0'
PIPELINE=['SAFETY_CONTEXT','SPECIES_RESOLVER','LIFE_STAGE_RESOLVER','ENERGY_TARGET',
          'BODY_CONDITION_ADJUSTMENT','ACTIVITY_NEUTER_ADJUSTMENT','DISEASE_ADAPTATION',
          'FOOD_RESTRICTION_FILTER','INGREDIENT_CANDIDATE_RANKING','RECIPE_COMPOSITION_SOLVER',
          'WHOLE_RECIPE_NUTRITION_CHECK','SUPPLEMENT_RECOMMENDATIONS']


def energy_audit(state,store):
    if not state['target']:return None
    raw=state['raw'];pet=raw['pet'];policy=state['target']['design_policy'];body=policy['body_condition_strategy']
    base=body['base_energy_kcal'];final=state['target']['daily_energy_kcal']
    original=energy_start(pet,raw['profile_id'],store)
    no_disease=body_strategy(pet,base,raw['life_stage'],set())
    neuter=body['neuter_weight_management_factor'];body_factor=no_disease['energy_factor']/neuter
    planned=body_strategy(pet,base,raw['life_stage'],set(raw['disease_advice']['diseases']))
    disease_factor=planned['energy_factor']/no_disease['energy_factor']
    feasibility_factor=final/base/planned['energy_factor']
    consumed=sum(f['energy_reference_kcal'] for f in raw['daily_foods'])
    return {'base_energy':{'kcal':base,'rer_kcal':original['RER_kcal'],'rule_id':original['rule_id'],
                          'source_id':original['source_id'],'interval_kcal':original['interval_kcal']},
            'body_condition_adjustment':{'factor':body_factor,'strategy':body['strategy'],'weight_trend':pet['weight_trend'],'source_id':'PALECHO_SPEC','evidence_level':'PRODUCT_STARTING_HEURISTIC'},
            'activity_adjustment':{'activity':pet['activity'],'mode':'INCLUDED_IN_BASE_RULE_SELECTION','applied_again':False},
            'neuter_adjustment':{'neutered':body['neutered'],'base_rule_accounts_for_neuter':pet['species']=='CAT','additional_factor':neuter,'applied_once':True},
            'disease_adjustment':{'diseases':raw['disease_advice']['diseases'],'factor':disease_factor,'source_id':'PALECHO_SPEC','no_invented_disease_multiplier':True},
            'age_and_life_stage':{'age_months':pet['age_months_completed'],'life_stage':raw['life_stage'],'unvalidated_senior_multiplier_applied':False},
            'feasibility_adjustment':{'factor':feasibility_factor,'scope':'EXISTING_NUTRIENT_FLOOR_PRESERVING_FALLBACK'},
            'final_energy_target':final,'recipe_energy':consumed,'unit':'kcal/day',
            'deviation_fraction':None if not raw['daily_foods'] else (consumed-final)/final,
            'tolerance_fraction':.05,'energy_basis':'FOOD_REFERENCE_ENERGY_NOT_MEASURED_ME',
            'reconciliation_error_kcal':final-base*body_factor*neuter*disease_factor*feasibility_factor}


def support_result(raw):
    acute=raw['recipe_status']=='BLOCKED_ACUTE_CONDITION'
    return {'status':'ACUTE_SUPPORT_RESULT' if acute else 'SUPPORTIVE_FEEDING_RESULT',
            'reason':deepcopy(raw['disease_advice'].get('acute_red_flags') or raw['reasons']),
            'immediate_feeding_guidance':(['尽快联系兽医评估当前急性状态；能否经口喂食、饮水及其方式需结合当前进食和吞咽耐受决定。'] if acute else ['当前食材和限制组合尚不能形成经核对的方案；保留原有已确认且耐受的喂养安排，并核对缺失资料。']),
            'what_not_to_do':['不要强行灌食或灌水，不凭本结果生成长期日粮或自行改变药物。','不要为了生成方案删除真实异常、过敏或食物禁忌。'],
            'monitoring':['记录能否进食、饮水、呕吐、排尿和精神变化，并向接诊人员说明。'],
            'ordinary_long_term_recipe':False,'quantified_feeding_or_fluid_dose':None}


class DailyRecipeEngine(ReminderEngine):
    def _disease_design(self,pet,advice,bounds,energy,stage):
        bounds,daily,policy,reasons=daily_disease_design(pet,advice,bounds,energy,stage)
        policy.update(version='CN_DAILY_DISEASE_DESIGN_1.5',
            objective_priority='SAFETY_NUTRITION_DISEASE_AVAILABILITY_COMPLEXITY_COST_PREFERENCE',
            recipe_complexity_penalty='COUNT_AFTER_DISEASE_AND_AVAILABILITY_BEFORE_COST_AND_PREFERENCE',
            disease_objective_relative_slack=.05,
            soft_component_count_only=True,
            hydration_via_preparation=True,
            retry_infeasible_without_presolve=True,
            check_active_nutrient_completion_capacity=True)
        # This is a tolerance on soft ranking objectives only; nutrient/disease
        # upper and lower bounds are unchanged and independently re-audited.
        return bounds,daily,policy,reasons

    def _food_bounds(self,bounds,pet):
        # Renal phosphorus and renal/cardiac electrolyte minima stay in food.
        # Do not minimize these in food and then propose an unsupervised
        # phosphate/potassium/sodium top-up against the disease care notes.
        adjusted=reminder_food_bounds(bounds)
        ids={d['id'] for d in pet['diseases']};keep=set()
        if ids&{'CKD','PLN'}:keep.add('phosphorus')
        if ids&{'CKD','PLN','MMVD','HCM','DCM','CHF','HYPERTENSION'}:keep|={'sodium','potassium'}
        return [before if before.nutrient in keep else after for before,after in zip(bounds,adjusted)]

    def _present(self,state):
        result=super()._present(state);raw=state['raw']
        result.update(presentation_mode='PRACTICAL_NUTRIENT_TARGETS',
            nutrition_scope='FOOD_WITH_ACTIVE_NUTRIENT_COMPLETION_PLAN',
            result_type='DISEASE_ADAPTED_RECIPE' if result['disease_adaptations'] else 'DAILY_RECIPE',
            energy_audit=energy_audit(state,self.store),energy_target=state['target']['daily_energy_kcal'] if state['target'] else None,
            recipe_energy=sum(f['energy_reference_kcal'] for f in raw['daily_foods']),
            nutrient_matrix=nutrient_matrix(state,self.store),supplement_recommendations=[],support_result=None)
        result['supplement_recommendations']=recommendations(state,self.store,result['nutrient_matrix'])
        result['calculation_metadata']['pipeline']=PIPELINE
        result['calculation_metadata']['energy_inputs_applied_once']=True
        result['calculation_metadata']['solver_presolve_retries']=raw.get('solver',{}).get('presolve_retries',[])
        result['calculation_metadata']['hydration_strategy']='PREPARATION_AND_FEEDING_WITHOUT_FORCING_EXTRA_COMPONENTS'
        result['practical_rounding']={'ordinary_food_quantum_g':5,'oil_quantum_g':.5,
            'oil_measurement':'使用能够分辨0.5g的秤；未获密度证据不把油克数猜成mL或滴数。',
            'reaudited':result['calculation_metadata']['rounding_reaudited']}
        if result['recipe_composition_policy']:
            result['recipe_composition_policy']['version']='DAILY_RECIPE_COMPOSITION_1.5'
            result['recipe_composition_policy']['complexity_penalty']='FEWER_FOODS_BEFORE_COST_AND_PREFERENCES'
        # Formal exclusion annotations let future care authors and tests enforce
        # consistency without guessing the semantics of arbitrary prose.
        policy=state['target']['design_policy'] if state['target'] else {}
        for d in result['disease_adaptations']:
            categories=policy.get('excluded_categories',[])
            if categories:
                d['foods_to_avoid'].append({'text':'制作时保留本次合并饮食规则的食材排除要求。',
                    'food_categories':categories,'ingredient_ids':policy.get('exclude_ids',[]),
                    'source_ids':sorted({a['source_id'] for a in result['disease_adaptations'] if a.get('source_id')}),'scope':'MERGED_RECIPE_CONSTRAINTS'})
        result['disease_lifestyle_notes']=deepcopy(result['disease_adaptations'])
        result['consistency_check']=check_recipe(state,result,self.store)
        matrix=result['nutrient_matrix']
        result['whole_recipe_nutrition_check']={'status':'NO_DAILY_RECIPE' if not raw['daily_foods'] else 'REQUIRES_NUTRIENT_COMPLETION' if any(not r['food_covers_reference_minimum'] for r in matrix if r['target_min'] is not None) else 'FOOD_REFERENCE_MINIMA_COVERED',
            'food_core_pass':bool(raw.get('nutrition_audit',{}).get('pass')),
            'all_original_requirements_preserved_in_matrix':True,'unknowns_are_zero':False,
            'complete_balanced_claim':False,'commercial_product_verified':False,
            'unresolved_nutrients':[r['nutrient_id'] for r in matrix if r['calculation_status']!='REFERENCE_ESTIMATE'],
            'completion_is_not_an_applied_product_dose':True}
        result['disease_supplement_evidence']=[{'disease_id':d['disease_id'],
            'status':'NO_DIAGNOSIS_ONLY_QUANTIFIED_SUPPLEMENT_TARGET',
            'source':source_record(self.store,d.get('source_id'),'GENERAL_DISEASE_DIET_DIRECTION'),
            'message':'本规则支持食材/照护方向；没有足够适用的定量补剂证据时，不仅凭疾病名称追加补剂。'} for d in result['disease_adaptations']]
        if raw['recipe_status']=='BLOCKED_ACUTE_CONDITION':
            result['status']=result['result_type']='ACUTE_SUPPORT_RESULT';result['support_result']=support_result(raw)
        elif result['status']=='NO_SAFE_RECIPE':
            result['result_type']='SUPPORTIVE_FEEDING_RESULT';result['support_result']=support_result(raw)
        if result['consistency_check']['status']=='FAIL':
            result['status']='NO_SAFE_RECIPE';result['result_type']='SUPPORTIVE_FEEDING_RESULT'
            result['reason_codes']+=result['consistency_check']['violations']
            result['recipe_components']=[];result['supplement_recommendations']=[];result['recipe_summary']['executable']=False
            result['recipe_energy']=0
            if result['energy_audit']:result['energy_audit'].update(recipe_energy=0,deviation_fraction=None)
            result['whole_recipe_nutrition_check']['status']='CONSISTENCY_FAILED_NO_RECIPE_RELEASED'
            result['daily_feeding_plan'].update(daily_total_food_g=0,daily_food_g=0,daily_total_g=0,food_g_per_meal=0,amount_per_meal_g=0)
            raw['recipe_status']='NO_SAFE_RECIPE';raw['reasons']=result['reason_codes'];raw['consumer_executable']=False
            result['support_result']=support_result(raw)
        return result
