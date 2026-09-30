"""API 1.9 Ingredient-First Quick Meal orchestration, isolated from API 1.8."""
from copy import deepcopy
import math
from .practical import digest
from .quick_meal import ADVANCED
from .quick_meal_support import SCOPE_NOTE,nutrition_support
from .ingredient_first_repository import IngredientRepository
from .ingredient_first_model import normalize_profile,model
from .ingredient_first_eligibility import IngredientEligibilityEngine,missing_categories
from .ingredient_first_solver import CombinationFeasibilityCheck
from .ingredient_first_audit import CHECKS,QuickMealScientificAudit,food_facts
from .ingredient_first_cooking import cooking_plan
from .recipe_me import solve_with_me,METHOD

ENGINE_VERSION='freshfood-ingredient-first-1.9.0'
READY={'QUICK_MEAL_RECOMMENDED','QUICK_MEAL_WITH_NUTRITION_NOTES','QUICK_MEAL_DISEASE_ADAPTED'}

class IngredientFirstQuickMealEngine:
    def __init__(self,store,repository=None):self.store=store;self.repo=repository or IngredientRepository()

    def context(self,profile,selection=None):
        p,pet,advice,warnings=normalize_profile(profile,selection,self.store,self.repo)
        m=None if advice['acute_red_flags'] else model(p,pet,advice,self.store,self.repo)
        if m is not None:
            from .disease_ingredient_matrix import rows_for
            matrix=rows_for(p,pet,advice,self.repo.registry)
            m['disease_evidence_matrix']=matrix
            m['disease_cooking_notes']=list(dict.fromkeys(row['message'] for row in matrix))
            chosen=[self.repo.records[i] for i in p['ingredient_selection']['ingredient_ids'] if i in self.repo.records]
            predictions={f['ingredient_id']:self.repo.energy(f,pet['species']) for f in chosen}
            ready=bool(chosen) and all(e['pet_me_kcal_per_100g'] is not None for e in predictions.values())
            m['pet_me_coefficients']={i:e['pet_me_kcal_per_100g'] for i,e in predictions.items()} if ready else None
            m['me_model_readiness']={'status':'CALCULATED' if ready else 'MISSING_REQUIRED_ANALYSES',
                'all_selected_foods_covered':ready,'unknown_inputs':{i:e['pet_me_prediction']['missing_inputs'] for i,e in predictions.items() if e['pet_me_kcal_per_100g'] is None},
                'source':'NRC2006_TDF_CALVEZ2019','formula_version':METHOD,'human_and_pet_energy_mixed':False}
        eligibility=IngredientEligibilityEngine(self.repo).evaluate(p,pet,advice,m)
        return p,pet,advice,warnings,m,eligibility

    def design(self,profile,selection=None):
        p,pet,advice,warnings,m,eligibility=self.context(profile,selection)
        selected=p['ingredient_selection']['ingredient_ids'];lookup={e['ingredient_id']:e for e in eligibility}
        r={'status':'SELECTION_REQUIRED','product':'FreshFood Ingredient-First Quick Meal','product_layer':'QUICK_MEAL_V1',
          'meal_scope':p['meal_scope'],'pet_summary':p,'selected_ingredient_set':deepcopy(p['ingredient_selection']),
          'estimated_energy_target':None if m is None else {'kcal':m['target'],'energy_target_is_estimate':True,'basis':'MONITORED_STARTING_ESTIMATE'},
          'estimated_daily_energy_target':None if m is None else {'kcal':m['energy']['daily_kcal'],'energy_target_is_estimate':True},
          'recipe_energy':0,'recipe_energy_basis':METHOD,'recipe_pet_me_kcal':None,'dog_me':None,'cat_me':None,'energy_validation':None,
          'recipe_components':[],'daily_or_meal_total_g':0,'meal_count':0,'suggested_daily_meal_count':0 if m is None else m['suggested_meal_count'],
          'ingredient_eligibility':eligibility,'nutrition_notes':[],'health_support_recommendations':[],'disease_support_recommendations':[],
          'cooking_plan':None,'key_nutrients':{},'warnings':warnings,'reason_codes':[],
          'scientific_checks':{k:'NOT_APPLICABLE' for k in CHECKS},'scientific_audit':None,'quick_meal_scientific_acceptance':'NOT_APPLICABLE',
          'complete_balanced_claim':False,'scope_note':SCOPE_NOTE,'advanced_complete_diet_layer':deepcopy(ADVANCED),
          'support_result':None,'combination_conflict':None,'missing_required_categories':[],
          'calculation_metadata':{'engine_version':ENGINE_VERSION,'selection_mode':'USER_SELECTED_SET',
            'input_hash':digest(p),'ingredient_data_hash':self.repo.data_hash,'whole_recipe_recalculated':True,
            'equal_split_used':False,'food_adoption_variables':False,'unselected_ingredients_added':False,'simplification_used':False,
            'model':m,'source_conflicts':deepcopy(self.repo.registry['source_conflicts'])},
          'explanations':{'why_this_energy_target':None if m is None else m['energy'],
            'why_this_protein_target':None if m is None else m['nutrient_targets']['protein'],
            'why_this_fat_target':None if m is None else m['nutrient_targets']['fat'],
            'why_each_selected_ingredient_amount':{},'disease_adjustments':[] if m is None else m['disease_adjustments'],
            'engineering_constraints':[]}}
        def stop(status,code,reason):
            r.update(status=status,reason_codes=[code],support_result={'reason':reason,'no_ordinary_recipe':True,'user_must_change_selection_or_profile':True})
            return {'profile':p,'result':r}
        if advice['acute_red_flags']:
            r['warnings'].append({'code':'ACUTE_RED_FLAGS','details':advice['acute_red_flags']})
            return stop('ACUTE_SUPPORT_RESULT','ACUTE_STATE_CONTRAINDICATION','当前急性状态需要及时临床评估；不生成普通鲜食方案，也不建议自行停食或改变药物。')
        if not selected:return stop('SELECTION_REQUIRED','USER_SELECTED_SET_REQUIRED','请先依据食材可选状态确定本次食材集合。后端不会代选。')
        rejected=[lookup[i] for i in selected if lookup[i]['eligibility']=='DISABLED']
        if rejected:
            r['rejected_ingredients']=deepcopy(rejected)
            r['scientific_checks']['FOOD_SAFETY']='FAIL';r['quick_meal_scientific_acceptance']='FAIL'
            return stop('SELECTION_REJECTED','INGREDIENT_SELECTION_DISABLED','已选集合包含当前不可使用的食材；请更换后重新提交，不会静默删除。')
        missing=missing_categories(selected,eligibility,self.repo)
        if missing:
            r['missing_required_categories']=missing
            return stop('MISSING_REQUIRED_CATEGORY','MISSING_REQUIRED_CATEGORY','缺少本产品的动物性核心类别；请自行选择一种或多种可选食材。')
        foods=[self.repo.records[i] for i in sorted(selected)]
        if not m.get('pet_me_coefficients'):
            return stop('SCIENTIFIC_AUDIT_FAILED','ME_DATA_INCOMPLETE','缺少犬猫ME预测所需数据，未使用人类食品热量替代。')
        solution,both_me=solve_with_me(foods,m,self.repo)
        r['calculation_metadata']['solver']={k:v for k,v in solution.items() if k not in {'grams','constraints','why_each_selected_ingredient_amount'}}
        if solution['status']=='AUDIT_FAILED':
            r['quick_meal_scientific_acceptance']='FAIL'
            return stop('SCIENTIFIC_AUDIT_FAILED','SCIENTIFIC_AUDIT_FAILED','求解结果未通过最终克数及犬猫ME审计，未发布Recipe或CookingPlan。')
        if solution['status']=='SOLVER_UNRESOLVED':
            from .freshfood_contract import ContractError
            raise ContractError('RECIPE_SOLVER_FAILED')
        if solution['status']!='SOLVED':
            affected=solution.get('affected_constraint') or ['FINAL_CONSTRAINT_AUDIT' if solution['status']=='AUDIT_FAILED' else 'SOLVER_UNRESOLVED']
            available=[x for x in eligibility if x['selectable'] and x['ingredient_id'] not in selected]
            # Suggestions are explicitly candidates requiring re-solve. They do
            # not claim a new combination is feasible before it has been solved.
            suggestions=[]
            for old in foods:
                options=[x['ingredient_id'] for x in available if x['category']==old['category']]
                if m['fat_max'] is not None:options.sort(key=lambda i:self.repo.records[i]['nutrients_per_100g']['fat']/self.repo.records[i]['nutrients_per_100g']['energy'])
                suggestions.append({'replace_ingredient_id':old['ingredient_id'],'recommended_options':options[:5],'requires_whole_recipe_feasibility_check':True,'automatically_applied':False})
            r['combination_conflict']={'code':'SELECTION_COMBINATION_CONFLICT','conflicting_ingredients':selected,
              'reason':'已选食材在当前营养、疾病、实际用量和工程限制下不能发布可执行配方。',
              'affected_constraint':affected,'constraint_details':solution.get('constraints',[]),
              'recommended_replacements':suggestions,'diagnostic_scope':solution.get('diagnostic_scope','SOLVER_STATUS'),
              'solver_status':solution['status'],'ingredients_silently_removed':False}
            r['quick_meal_scientific_acceptance']='FAIL'
            return stop('SELECTION_COMBINATION_CONFLICT','SELECTION_COMBINATION_CONFLICT',r['combination_conflict']['reason'])
        grams=solution['grams']
        if any(type(g) not in (int,float) or not math.isfinite(g) for g in grams.values()):
            r['scientific_checks']['PRACTICAL_GRAMS']='FAIL';r['quick_meal_scientific_acceptance']='FAIL'
            return stop('SCIENTIFIC_AUDIT_FAILED','PRACTICAL_GRAMS_INVALID','求解输出含无效克数，未发布配方。')
        facts=food_facts(foods,grams)
        facts['energy']['basis']='USDA_FOOD_ENERGY_REFERENCE_NOT_PET_ME'
        components=[]
        for f in foods:
            g=grams.get(f['ingredient_id'],0)
            # Do not create a fake positive component when solver output was
            # corrupted. The exact-selected-set audit will fail below.
            if g<=0:continue
            components.append({'ingredient_id':f['ingredient_id'],'display_name':f['display_name_cn'],'canonical_name':f['canonical_name'],
              'amount_g':g,'category':f['category'],'food_state':f['food_state'],'weight_basis':f['weight_basis'],'portion_basis':f['portion_basis'],
              'source_id':f['authoritative_source_id'],'fdc_id':f['fdc_id'],'source_version':f['source_version'],'record_sha256':f['record_sha256'],
              'energy_kcal':g*m['pet_me_coefficients'][f['ingredient_id']]/100,
              'dog_me':both_me['DOG']['ingredient_contributions_kcal'][f['ingredient_id']],
              'cat_me':both_me['CAT']['ingredient_contributions_kcal'][f['ingredient_id']],
              'energy_model':{**self.repo.energy(f,pet['species']),
                'pet_me_kcal_per_100g':m['pet_me_coefficients'][f['ingredient_id']],
                'value_per_100g':m['pet_me_coefficients'][f['ingredient_id']],
                'prediction_scope':'FINAL_MIXTURE_CONDITIONED_INGREDIENT_CONTRIBUTION',
                'pet_me_prediction':{**{k:v for k,v in both_me[pet['species']].items() if k not in {
                    'coefficients_per_100g','ingredient_contributions_kcal','analytical_inputs_per_100g','gross_energy_kcal',
                    'proximate_sum_g_per_100g','composition_closure_error_g_per_100g'}},
                  'value':g*m['pet_me_coefficients'][f['ingredient_id']]/100,'mass_g':g,
                  'analytical_inputs_scope':'FINAL_MIXTURE_DIGESTIBILITY_WITH_THIS_INGREDIENT_NUTRIENT_VECTOR',
                  'basis':'SELECTED_INGREDIENT_PORTION_IN_FINAL_MIXTURE'}}})
        # The evidence-backed support engine is shared, never its food solver.
        support_state={'raw':{'daily_foods':components,'pet':pet,'life_stage':m['life_stage'],'disease_advice':advice},'facts':facts}
        notes,health,disease,support_warnings=nutrition_support(support_state,self.store)
        plan=cooking_plan(components,m,self.repo,notes,health,disease)
        audit=QuickMealScientificAudit(self.repo).run(selected,components,m,eligibility,plan)
        r.update(scientific_checks=audit['checks'],scientific_audit=audit,quick_meal_scientific_acceptance=audit['status'])
        r['explanations']['why_each_selected_ingredient_amount']=solution.get('why_each_selected_ingredient_amount',{})
        r['explanations']['engineering_constraints']=[x for x in audit['constraint_audit'] if x['classification']=='ENGINEERING_LIMIT']
        if audit['status']=='FAIL':
            return stop('SCIENTIFIC_AUDIT_FAILED','SCIENTIFIC_AUDIT_FAILED','最终克数的独立审计失败，未发布普通Recipe或CookingPlan。')
        r.update(status='QUICK_MEAL_DISEASE_ADAPTED' if m['diseases'] else 'QUICK_MEAL_WITH_NUTRITION_NOTES' if notes else 'QUICK_MEAL_RECOMMENDED',
          recipe_components=components,recipe_energy=sum(c['energy_kcal'] for c in components),daily_or_meal_total_g=sum(c['amount_g'] for c in components),
          meal_count=m['meal_count'],key_nutrients=facts,cooking_plan=plan,nutrition_notes=notes,health_support_recommendations=health,disease_support_recommendations=disease)
        r['warnings']+=[{'code':'SUPPORT_EVIDENCE_UNAVAILABLE','message':x} for x in support_warnings]
        r.update(recipe_pet_me_kcal=r['recipe_energy'],recipe_energy_basis=METHOD,
          dog_me=both_me['DOG']['value'],cat_me=both_me['CAT']['value'])
        r['calculation_metadata']['whole_recipe_me']=both_me
        tolerance=self.repo.policy['energy_tolerance'];delta=r['recipe_energy']-m['target']
        r['energy_validation']={'status':'PASS' if abs(delta)<=m['target']*tolerance+1e-7 else 'FAIL',
          'species':pet['species'],'recipe_total_me_kcal':r['recipe_energy'],'pet_energy_target_kcal':m['target'],
          'difference_kcal':delta,'difference_fraction':delta/m['target'],
          'allowed_minimum_kcal':m['target']*(1-tolerance),'allowed_maximum_kcal':m['target']*(1+tolerance),
          'tolerance_classification':'ENGINEERING_PORTION_TOLERANCE_NOT_PREDICTION_CONFIDENCE_INTERVAL',
          'formula':METHOD,'prediction_not_measurement':True}
        r['warnings'].append({'code':'ME_PREDICTION_LIMITATIONS','message':'犬猫ME按整餐营养成分预测，并非该动物实测消化率；鲜食、幼龄及疾病适用性仍有外推限制，需结合进食和体况监测。'})
        if facts['ca_p_ratio'] is None or facts['ca_p_ratio']<1:
            r['warnings'].append({'code':'LONG_TERM_CA_P_NOT_COMPLETE','message':'这份食物不能据此用于长期完整日粮；长期钙磷与全微量营养由Advanced Complete Diet处理。'})
        return {'profile':p,'result':r}
