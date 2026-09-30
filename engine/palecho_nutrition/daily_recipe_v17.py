"""API 1.7 scientific contract: evidence purpose, deletion trials and meals."""
from copy import deepcopy
from .daily_recipe_v16 import DailyRecipeEngine as PreviousEngine
from .scientific_profile_v17 import normalize_profile
from .scientific_supplements_v17 import run_supplements, GOALS, block_nutrients
from .recipe_consistency import check_recipe
from .daily_recipe_v15 import support_result
ENGINE_VERSION='freshfood-scientific-1.7.0'


def scientific_audit(state,r,store):
    raw=state['raw'];pet=raw['pet'];defs=store.keyed('ingredients','ingredient_id');foods=r['recipe_components'];ready=bool(foods)
    checks={};e=r['energy_audit'];stage=raw.get('life_stage','');recs=r['supplement_recommendations']
    checks['ENERGY_VALID']='NOT_APPLICABLE' if not ready else 'PASS' if e and abs(e['deviation_fraction'])<=.050001 and abs(e['reconciliation_error_kcal'])<1e-6 else 'FAIL'
    checks['SPECIES_VALID']='PASS' if all(defs[f['ingredient_id']][pet['species'].lower()+'_allowed'] for f in foods) and (not ready or stage.startswith(pet['species'])) else 'FAIL'
    food_stage='WEANED_GROWTH' if 'GROWTH' in stage else stage.removeprefix(pet['species']+'_')
    stage_allowed=all(food_stage in (defs[f['ingredient_id']]['life_stage_allowed'] or '').split(';') for f in foods)
    checks['LIFE_STAGE_VALID']='NOT_APPLICABLE' if not ready else 'PASS' if stage_allowed and stage.startswith(pet['species']) and ('GROWTH' not in stage or pet['species']=='CAT' or pet.get('expected_adult_weight_kg')) else 'FAIL'
    checks['BCS_VALID']='NOT_APPLICABLE' if not ready else 'PASS' if e['body_condition_adjustment']['bcs']==pet['bcs'] and e['weight_trend_adjustment']['weight_trend']==pet['weight_trend'] else 'FAIL'
    consistency=check_recipe(state,r,store)
    checks['DISEASE_VALID']='FAIL' if ready and not r['whole_recipe_nutrition_check']['food_core_pass'] or any('DISEASE' in v or 'CARE_AVOID' in v for v in consistency['violations']) else 'PARTIAL' if raw['disease_advice']['diseases'] else 'NOT_APPLICABLE'
    checks['ALLERGY_VALID']='FAIL' if any('ALLERGEN' in v for v in consistency['violations']) else 'PASS'
    checks['INGREDIENT_SELECTION_VALID']=r['ingredient_selection_audit']['status']
    main=sum(defs[f['ingredient_id']]['food_category'] not in {'OIL','ORGAN'} for f in foods)
    usual=(3,6) if pet['species']=='DOG' else (2,5)
    checks['RECIPE_COMPLEXITY_VALID']='NOT_APPLICABLE' if not ready else 'PASS' if usual[0]<=main<=usual[1] else 'PARTIAL'
    unneeded=[x for x in recs if x['goal']=='NUTRIENT_COMPLETION' and x['nutrient_matrix'] and all(v['food_covers_reference_minimum'] for v in x['nutrient_matrix'])]
    checks['SUPPLEMENT_NEEDED']='FAIL' if unneeded else 'PARTIAL' if any(x['target_amount'] is None for x in recs) else 'PASS'
    required=['title','why_recommended','physiologic_role','recipe_reason','species_applicability','life_stage_applicability','active_nutrient','target_basis','label_should_show','conditional_requirements']
    checks['SUPPLEMENT_PURPOSE_VALID']='PASS' if all(x['goal'] in GOALS and all(x.get(k) for k in required) for x in recs) else 'FAIL'
    checks['SUPPLEMENT_EVIDENCE_VALID']='PASS' if all(x['evidence_level'] in {'EVIDENCE_A','EVIDENCE_B'} and x['evidence_source_ids'] and all(s.get('URL') for s in x['evidence_sources']) for x in recs) else 'FAIL'
    invalid=[]
    for x in recs:
        if x['auto_recommend'] and (x['target_amount'] is None or x['additional_amount_needed'] is None):invalid.append(x['recommendation_id'])
        if x['target_amount'] is not None and any(v['calculation_status']!='REFERENCE_ESTIMATE' for v in x['nutrient_matrix']):invalid.append(x['recommendation_id'])
    checks['SUPPLEMENT_TARGET_VALID']='FAIL' if invalid else 'PARTIAL' if any(x['target_amount'] is None for x in recs) else 'PASS'
    safety=r['supplement_decision']['safety']
    checks['SUPPLEMENT_SAFETY_VALID']='FAIL' if safety['status']=='AVOID' or 'SUPPLEMENT_SAFETY_CONFLICT' in raw['reasons'] else 'PARTIAL' if recs else 'NOT_APPLICABLE'
    checks['SUPPLEMENT_DIET_INTERACTION_VALID']='FAIL' if safety['duplicate_active_nutrients'] or safety['disease_conflicts'] or safety['upper_conflicts'] else 'PARTIAL' if recs else 'NOT_APPLICABLE'
    checks['COOKING_VALID']='NOT_EVALUATED_UNTIL_PREPARATION'
    failures=[k for k,v in checks.items() if v=='FAIL']
    return dict(version='1.7',overall_status='FAIL' if failures else 'PARTIAL',required_checks=checks,
        checks=[{'check':k,'status':v} for k,v in checks.items()],critical_failures=failures,
        limitations=['食品参考热量不是犬猫实测ME，未知营养背景仍需补全。','产品面板、临床个体目标和药物交互未全部核实。'],
        release_scope='REVIEW_ONLY_FOOD_PLAN_AND_CONDITIONAL_NUTRIENT_REFERENCE',long_term_complete_diet_verified=False,acute_safety_result=r['status']=='ACUTE_SUPPORT_RESULT')

class DailyRecipeEngine(PreviousEngine):
    def _source_candidates(self,pet,stage,daily,excluded):
        foods,rejected=super()._source_candidates(pet,stage,daily,excluded)
        if pet['species']=='DOG' and any(d['id']=='EPI' for d in pet['diseases']):
            missing=[f for f in foods if f['category'] in {'STARCH','VEGETABLE'} and f['values'].get('dietary_fiber') is None]
            rejected += [{'id':f['id'],'reasons':['EPI_PLANT_FIBER_BACKGROUND_UNKNOWN']} for f in missing]
            foods=[f for f in foods if f not in missing]
        return foods,rejected
    def _disease_design(self,pet,advice,bounds,energy,stage):
        bounds,daily,policy,reasons=super()._disease_design(pet,advice,bounds,energy,stage)
        if pet['species']=='DOG' and 'EPI' in advice['diseases']:
            policy.update(prefer_low_known_plant_fiber=True,epi_diet_source='MERCK_EPI2026',
                epi_diet_scope='LOWER_KNOWN_PLANT_FIBER_NOT_MEASURED_TOTAL_FIBER_OR_THERAPEUTIC_LIMIT')
        if getattr(self,'_deletion_trial',False):
            # Do not force a replacement merely to fill the usual count range.
            # All nutrient and disease hard bounds remain identical.
            policy['component_count_range']=[1,6 if pet['species']=='DOG' else 5]
        return bounds,daily,policy,reasons
    def _normalize_profile(self,profile):return normalize_profile(profile,self.store)
    def _run_supplements(self,state):return run_supplements(state,self.store)
    def _audit(self,state,r):return scientific_audit(state,r,self.store)
    def _present(self,state):
        raw=state['raw'];pet=raw['pet'];stage=raw.get('life_stage','');diseases=set(raw['disease_advice']['diseases'])
        if 'GROWTH' in stage:meals=4 if pet['species']=='CAT' or pet['age_months_completed']<4 else 3;reason='幼年阶段采用较小份量分餐，随生长和耐受调整。'
        elif pet['species']=='CAT':meals=4;reason='猫采用多次小餐，便于控制每日总量并支持觅食行为。'
        elif diseases & {'EPI','CIE_DOG','PLE','PANCREATITIS_DOG'} and 'DIABETES_DOG' not in diseases:meals=3;reason='稳定且能够进食时，将同一日量分成较小餐次，观察消化耐受。'
        else:meals=2;reason='稳定成犬采用两餐作为家庭执行起点。'
        raw['meals_per_day']=meals
        result=super()._present(state)
        if pet['species']=='DOG' and 'EPI' in diseases and result['recipe_components']:
            sources={f['id']:f for f in state['eligible_foods']}
            known=sum(c['amount_g']/100*sources[c['ingredient_id']]['values']['dietary_fiber'] for c in result['recipe_components'] if sources[c['ingredient_id']]['category'] in {'STARCH','VEGETABLE'})
            unknown=[c['ingredient_id'] for c in result['recipe_components'] if sources[c['ingredient_id']]['values'].get('dietary_fiber') is None]
            result['nutrition_design_target']['epi_fiber_strategy']={'known_plant_food_fiber_g':known,'unquantified_food_ids':unknown,
                'total_dietary_fiber_g':None if unknown else sum(c['amount_g']/100*sources[c['ingredient_id']]['values']['dietary_fiber'] for c in result['recipe_components']),
                'source_id':'MERCK_EPI2026','therapeutic_total_fiber_target':None,'scope':'DIRECTIONAL_FOOD_RANKING_WITH_UNKNOWNS_PRESERVED'}
        if result['recipe_components']:
            feeding=result['daily_feeding_plan'];total=feeding['daily_total_food_g'];per=round(total/meals,1)
            # Preserve exact mass in API averaging and expose practical residual
            # allocation separately; do not silently lose grams across meals.
            feeding.update(food_g_per_meal=total/meals,amount_per_meal_g=total/meals)
            feeding['meal_portions_g']=[per]*(meals-1)+[round(total-per*(meals-1),1)]
            feeding['meal_strategy']={'reason':reason,'scope':'MONITORED_HOUSEHOLD_STARTING_STRATEGY','source_ids':['AAFP_FEEDING2018'] if pet['species']=='CAT' else ['AAHA_NUTRITION2021'],'exact_count_is_guideline_dose':False,
                'medication_schedule_priority':bool(diseases & {'DIABETES_DOG','DIABETES_CAT','EPI'}),'instructions':'总日量不变；已有胰岛素、胰酶或临床餐时方案时须按既定安排分配，不自行调整药物。'}
        else:
            result['daily_feeding_plan']['meal_portions_g']=[]
            result['daily_feeding_plan']['meal_strategy']={'reason':'当前非普通喂养方案。','scope':'SUPPORT_RESULT','source_ids':[],'exact_count_is_guideline_dose':False,'medication_schedule_priority':True,'instructions':'按当前支持结果处理。'}
        result['calculation_metadata']['engine_version']=ENGINE_VERSION
        result['calculation_metadata']['pipeline'][-2:]=['FOUR_PURPOSE_EVIDENCE_SAFETY_TARGET','COMPUTED_SCIENTIFIC_AUDIT']
        result['scientific_audit']=self._audit(state,result)
        if result['scientific_audit']['critical_failures'] and raw['daily_foods']:
            failed=deepcopy(result['scientific_audit'])
            raw.update(recipe_status='NO_SAFE_RECIPE',daily_foods=[],consumer_executable=False,reasons=raw['reasons']+failed['critical_failures'])
            raw.pop('food_reference_audit',None);raw.pop('nutrition_audit',None)
            result=self._present(state);result['scientific_audit']['blocked_original_audit']=failed
            result['scientific_audit']['overall_status']='FAIL'
            result['scientific_audit']['critical_failures']=failed['critical_failures']
        return result

    def design(self,profile,**kwargs):
        state=super().design(profile,**kwargs);history=[]
        excluded=set(kwargs.get('excluded',()));required=set(kwargs.get('required',()))
        defs=self.store.keyed('ingredients','ingredient_id')
        chosen={r['ingredient_id'] for r in state['result']['recipe_components']}
        # Explicitly identified alternative cooking states of chicken breast.
        # Never add their weights or substitute their nutrition vectors 1:1.
        duplicate_states={'FDC_171477','FDC_171478'} if {'FDC_171477','FDC_171478'}<=chosen else set()
        small=[r['ingredient_id'] for r in sorted(state['result']['recipe_components'],key=lambda c:c['amount_g']) if (r['amount_g']<=10 or r['ingredient_id'] in duplicate_states) and defs[r['ingredient_id']]['food_category'] not in {'OIL','ORGAN'} and r['ingredient_id'] not in required]
        for iid in small:
            if iid not in {c['ingredient_id'] for c in state['result']['recipe_components']}:continue
            before=state['result'];trial_engine=DailyRecipeEngine(self.store)
            trial_engine._deletion_trial=True
            trial=super(DailyRecipeEngine,trial_engine).design(profile,**{**kwargs,'excluded':sorted(excluded|{iid})})
            after=trial['result'];reasons=[]
            if not after['recipe_components']:reasons.append('NO_VALID_REPLACEMENT')
            if len(after['recipe_components'])>=len(before['recipe_components']):reasons.append('NO_COMPLEXITY_REDUCTION')
            prior={r['nutrient_id']:r for r in before['nutrient_matrix']};later={r['nutrient_id']:r for r in after['nutrient_matrix']}
            for n,r in later.items():
                old=prior.get(n,{})
                if r['food_contribution_estimate'] is None and old.get('food_contribution_estimate') is not None:reasons.append('NEW_UNKNOWN:'+n)
                if n in block_nutrients(set(state['raw']['disease_advice']['diseases'])):continue
                a=r.get('additional_amount_needed');b=old.get('additional_amount_needed')
                if a is not None and b is not None and a-b>max(b*.05,(old.get('target_min') or 0)*.05)+1e-6:reasons.append('WORSE_COMPLETION:'+n)
            for n in state['target']['design_policy'].get('minimize_nutrients',[]) if state['target'] else []:
                a=later.get(n,{}).get('food_known_subtotal');b=prior.get(n,{}).get('food_known_subtotal')
                if a is None or b is None or a>b*1.05+1e-6:reasons.append('WORSE_DISEASE_OBJECTIVE:'+n)
            if state['target'] and state['target']['design_policy'].get('prefer_low_known_plant_fiber') and after['recipe_components']:
                if after['nutrition_design_target']['epi_fiber_strategy']['known_plant_food_fiber_g']>before['nutrition_design_target']['epi_fiber_strategy']['known_plant_food_fiber_g']*1.05+1e-6:reasons.append('WORSE_KNOWN_PLANT_FIBER_DIRECTION')
            accepted=not reasons
            history.append({'ingredient_id':iid,'removed_and_fully_resolved':True,'accepted':accepted,'reason_codes':reasons or ['FEWER_COMPONENTS_WITHOUT_MEANINGFUL_NUTRITION_OR_DISEASE_LOSS'],'before_components':len(before['recipe_components']),'after_components':len(after['recipe_components'])})
            if accepted:state=trial;excluded.add(iid)
        state['result']['complexity_review']={'deletion_trials':history,'relative_worsening_tolerance':.05,'completion_change_basis':'MAX_OF_5_PERCENT_PRIOR_GAP_AND_5_PERCENT_DAILY_REFERENCE','scope':'ENGINEERING_MARGINAL_COMPARISON_NOT_CLINICAL_EQUIVALENCE','hard_bounds_preserved':True}
        return state
