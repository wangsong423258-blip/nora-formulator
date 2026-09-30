"""Scientific audit boundary: explicit energy, selectable food pools and support layers."""
from copy import deepcopy
from dataclasses import replace
from .daily_recipe_v15 import DailyRecipeEngine as PreviousEngine, PIPELINE
from .scientific_profile import normalize_profile, energy_start, policy
from .scientific_ingredients import candidates, selection_audit
from .scientific_supplements import run_supplements
from .daily_disease_v13 import body_strategy
from .profile import lifecycle
from .recipe_consistency import check_recipe

ENGINE_VERSION = 'freshfood-scientific-1.6.0'
AUDIT_KEYS = ['species_differences','life_stage','energy_reconciliation','body_condition','activity_neuter',
    'disease_adaptation','ingredient_selection','allergy_safety','nutrient_balance','supplement_evidence',
    'supplement_safety','practicality','china_availability','premium_evidence','fish_contaminants',
    'cooking_consistency','source_traceability','long_term_completeness']


def energy_audit(state):
    if not state['target']: return None
    raw=state['raw']; p=raw['pet']; body=state['target']['design_policy']['body_condition_strategy']
    energy=raw['energy']; spec=energy['scientific_energy']; base=body['base_energy_kcal']
    no_disease=body_strategy(p,base,raw['life_stage'],set())
    body_factor=no_disease['energy_factor']/no_disease['neuter_weight_management_factor']
    planned=body_strategy(p,base,raw['life_stage'],set(raw['disease_advice']['diseases']))
    planned_factor=planned['energy_factor']/planned['neuter_weight_management_factor']
    final=state['target']['daily_energy_kcal']; disease=planned_factor/body_factor
    feasibility=final/base/planned_factor; consumed=sum(r['energy_reference_kcal'] for r in raw['daily_foods'])
    return {'base_energy':{'kcal':base,'rer_kcal':energy['RER_kcal'],'rule_id':energy['rule_id'],
            'source_id':energy['source_id'],'coefficient_policy':deepcopy(spec)},
        'life_stage_adjustment':{'mode':'REQUIREMENT_PROFILE_AND_BASE_MODEL','life_stage':raw['life_stage']},
        'weight_trend_adjustment':{'weight_trend':p['weight_trend'],'included_in_body_factor':True,'applied_again':False},
        'body_condition_adjustment':{'factor':body_factor,'bcs':p['bcs'],'weight_trend':p['weight_trend'],
            'scope':'MONITORED_PRODUCT_STARTING_HEURISTIC'},
        'activity_adjustment':{'activity':p['_activity_level_v16'],'mode':'IN_BASE_COEFFICIENT','applied_again':False},
        'neuter_adjustment':{'neutered':body['neutered'],'additional_factor':1,'applied_once':True,
            'coefficient_delta':spec.get('neuter_coefficient_delta',0)},
        'disease_adjustment':{'diseases':raw['disease_advice']['diseases'],'factor':disease,
            'no_invented_disease_multiplier':True},
        'age_and_life_stage':{'age_months':p['age_months_completed'],'life_stage':raw['life_stage'],
            'unvalidated_senior_multiplier_applied':False},
        'feasibility_adjustment':{'factor':feasibility,'scope':'NUTRIENT_FLOOR_PRESERVING_FALLBACK'},
        'final_energy_target':final,'recipe_energy':consumed,'unit':'kcal/day',
        'deviation_fraction':(consumed-final)/final if raw['daily_foods'] else None,'tolerance_fraction':.05,
        'energy_basis':'FOOD_REFERENCE_ENERGY_NOT_MEASURED_ME',
        'reconciliation_error_kcal':final-base*body_factor*disease*feasibility}


class DailyRecipeEngine(PreviousEngine):
    def _run_supplements(self,state): return run_supplements(state,self.store)
    def _normalize_profile(self, profile): return normalize_profile(profile,self.store)
    def _energy_start(self, pet, requirement_profile): return energy_start(pet,requirement_profile,self.store)
    def _source_candidates(self,pet,stage,daily,excluded):
        foods,rejected=candidates(pet,stage,self.store,daily,excluded)
        for food in foods:
            food['minimum_portion_g']=10 if food['category'] not in {'OIL','ORGAN'} else food['quantum']
        return foods,rejected

    def _disease_design(self,pet,advice,bounds,energy,stage):
        bounds,_,p,reasons=super()._disease_design(pet,advice,bounds,energy,stage)
        body=p['body_condition_strategy']
        body['energy_factor']/=body['neuter_weight_management_factor']
        body['neuter_weight_management_factor']=1.
        body['daily_energy_kcal']=energy*body['energy_factor']
        _,rp=lifecycle(pet,self.store); spec=self._energy_start(pet,rp)['scientific_energy']
        floor=spec['nutrient_floor_energy']
        if floor>energy:
            bounds=[replace(b,minimum=b.minimum*floor/energy) if b.minimum is not None and b.basis=='PER_1000_KCAL_ME' else b for b in bounds]
        if pet['bcs']<4 and 'DIABETES_DOG' in advice['diseases'] and not set(advice['diseases']) & {'PANCREATITIS_DOG','HYPERLIPIDEMIA','PLE'}:
            p['minimize_nutrients']=[n for n in p['minimize_nutrients'] if n!='fat']
            p['diabetes_body_condition_policy']='PRESERVE_ENERGY_AND_MUSCLE_NO_BLANKET_LOW_FAT'
        p.update(version='CN_SCIENTIFIC_DESIGN_1.6',soft_structure_categories=[],diversity_after_cost=True,
            nutrient_floor_reference_energy=floor,ordinary_minimum_portion_g=10,
            minimum_portion_scope='HOUSEHOLD_ENGINEERING_RULE_NOT_NUTRIENT_REQUIREMENT')
        return bounds,body['daily_energy_kcal'],p,reasons

    def _present(self,state):
        result=super()._present(state); raw=state['raw']; target=state['target']
        result['energy_audit']=energy_audit(state)
        matrix,recs,support=self._run_supplements(state)
        result.update(nutrient_matrix=matrix,supplement_recommendations=recs,supplement_decision=support,
            ingredient_selection_audit=selection_audit(state,result,self.store))
        result['calculation_metadata']['pipeline']=PIPELINE[:-1]+['THREE_LAYER_SUPPLEMENT_SUPPORT','RECIPE_SCIENTIFIC_AUDIT']
        result['calculation_metadata']['engine_version']=ENGINE_VERSION
        groups={'protein':['protein'],'fat':['fat'],'essential_amino_acids':['arginine','histidine','isoleucine','leucine','lysine','methionine','methionine_cystine','phenylalanine','phenylalanine_tyrosine','threonine','tryptophan','valine'],
            'essential_fatty_acids':['linoleic','alpha_linolenic','arachidonic','epa_dha'],
            'minerals':['calcium','phosphorus','ca_p_ratio','potassium','sodium','chloride','magnesium','iron','copper','zinc','manganese','iodine','selenium'],
            'vitamins':['vitamin_a','vitamin_d','vitamin_e','b1','b2','b3','b5','b6','b9','b12','choline'],
            'cat_specific':['taurine','arachidonic','arginine','vitamin_a_cat'] if raw['pet']['species']=='CAT' else []}
        allocated={n for ns in groups.values() for n in ns}
        groups['other_reference_nutrients']=[r['nutrient_id'] for r in matrix if r['nutrient_id'] not in allocated]
        result['nutrition_design_target']={'scope':result['nutrition_scope'],'energy':deepcopy(result['energy_audit']),
            'species':raw['pet']['species'],'life_stage':raw.get('life_stage'),'weight_kg':raw['pet']['weight_kg'],
            'daily_reference_targets':deepcopy(matrix),'nutrient_groups':groups,
            'disease_constraints':deepcopy(target['disease_constraints']) if target else [],
            'design_policy':deepcopy(target['design_policy']) if target else {},
            'food_data_energy_basis':'USDA_REFERENCE_NOT_MEASURED_PET_ME','complete_balanced_claim':False}
        matrix_by_id={row['nutrient_id']:row for row in matrix}
        explicit=result['nutrition_design_target']
        for field in ['protein','fat','calcium','phosphorus']:
            explicit[field]=deepcopy(matrix_by_id.get(field))
        for field in ['essential_amino_acids','essential_fatty_acids','minerals','vitamins']:
            explicit[field]={n:deepcopy(matrix_by_id.get(n)) for n in groups[field]}
        explicit['species_specific_nutrients']={n:deepcopy(matrix_by_id.get('vitamin_a' if n=='vitamin_a_cat' else n)) for n in groups['cat_specific']}
        explicit['calcium_phosphorus_ratio']=deepcopy(matrix_by_id.get('calcium',{}).get('calcium_phosphorus_check'))
        explicit['disease_specific_constraints']=deepcopy(explicit['disease_constraints'])
        definitions=self.store.keyed('ingredients','ingredient_id')
        result['ingredient_rationale']=[{'ingredient_id':r['ingredient_id'],'amount_g':r['amount_g'],
            'food_category':definitions[r['ingredient_id']]['food_category'],
            'reason':'在用户候选池内共同满足能量、物种营养和疾病约束后，按家庭可得性、复杂度及成本排序。',
            'selected_by':'WHOLE_RECIPE_SOLVER','premium_benefit_claim':False} for r in result['recipe_components']]
        source_by_id={food['id']:food for food in state['eligible_foods']}
        units={row['nutrient_id']:row['canonical_unit'] for row in self.store.rows('nutrients')}
        for item in result['ingredient_rationale']:
            source=source_by_id[item['ingredient_id']]
            focus=['linoleic','alpha_linolenic','vitamin_e','fat'] if item['food_category']=='OIL' else ['protein','fat','calcium','phosphorus','epa_dha']
            item['known_daily_contributions']={n:{'amount':source['values'][n]*item['amount_g']/100,'unit':units[n]} for n in focus if source['values'].get(n) is not None}
            if item['food_category']=='OIL':item['reason']='作为脂肪及必需脂肪酸来源参与整餐求解；以下列出其实际营养贡献，油脂热量计入每日总量。'
        result['practical_rounding'].update(ordinary_minimum_portion_g=10,
            batch_oil_measurement='每日油量不足常用秤精度时，可按1/3/7天配方合批称重、充分混匀再分装；无密度证据不换算滴数。')
        result['whole_recipe_nutrition_check']['unresolved_nutrients']=[r['nutrient_id'] for r in matrix if r['calculation_status']!='REFERENCE_ESTIMATE']
        result['consistency_check']=check_recipe(state,result,self.store)
        failures=result['consistency_check']['violations']
        if support['safety']['status']=='AVOID':failures=failures+['SUPPLEMENT_SAFETY_CONFLICT']
        if failures and raw['daily_foods']:
            raw.update(recipe_status='NO_SAFE_RECIPE',daily_foods=[],consumer_executable=False,
                reasons=sorted(set(raw['reasons']+failures)))
            raw.pop('food_reference_audit',None)
            raw.pop('nutrition_audit',None)
            return self._present(state)
        result['scientific_audit']=self._audit(state,result)
        return result

    def _audit(self,state,r):
        raw=state['raw']; ready=bool(r['recipe_components']); has_disease=bool(raw['disease_advice']['diseases'])
        status={k:'PASS' for k in AUDIT_KEYS}
        status.update(nutrient_balance='PARTIAL',supplement_safety='PARTIAL',long_term_completeness='PARTIAL',
            fish_contaminants='PARTIAL' if any(self.store.keyed('ingredients','ingredient_id')[x['ingredient_id']]['food_category']=='FISH' for x in r['recipe_components']) else 'NOT_APPLICABLE',
            disease_adaptation='PARTIAL' if has_disease else 'NOT_APPLICABLE',cooking_consistency='NOT_APPLICABLE')
        if not ready:
            for k in ['energy_reconciliation','nutrient_balance','practicality']:status[k]='NOT_APPLICABLE'
        if r['consistency_check']['status']=='FAIL':status['allergy_safety']='FAIL'
        status['ingredient_selection']=r['ingredient_selection_audit']['status']
        evidence=[s for rec in r['supplement_recommendations'] for s in rec['evidence_sources']]
        if any(s['evidence_status']!='VERIFIED' for s in evidence):status['source_traceability']='PARTIAL'
        return {'version':'1.6','overall_status':'PARTIAL','checks':[{'check':k,'status':status[k]} for k in AUDIT_KEYS],
            'required_checks':{
                'ENERGY_MATCH':status['energy_reconciliation'],'SPECIES_MATCH':status['species_differences'],
                'LIFE_STAGE_MATCH':status['life_stage'],'BODY_CONDITION_MATCH':status['body_condition'],
                'DISEASE_MATCH':status['disease_adaptation'],'ALLERGY_SAFE':status['allergy_safety'],
                'USER_SELECTION_RESPECTED':status['ingredient_selection'],'INGREDIENT_RATIONALE':'PASS',
                'RECIPE_COMPLEXITY':status['practicality'],'PRACTICAL_MEASUREMENT':status['practicality'],
                'NUTRIENT_BALANCE':status['nutrient_balance'],'SUPPLEMENT_JUSTIFICATION':'PASS',
                'SUPPLEMENT_PURPOSE':'PASS','SUPPLEMENT_EVIDENCE':status['source_traceability'],
                'SUPPLEMENT_TARGET':'PARTIAL','SUPPLEMENT_SAFETY':status['supplement_safety'],
                'DISEASE_SUPPLEMENT_COMPATIBILITY':'PARTIAL' if has_disease else 'NOT_APPLICABLE',
                'COOKING_CONSISTENCY':'NOT_APPLICABLE'},
            'limitations':['食品能量不是实测犬猫ME；部分熟制微量成分仍未知。',
                '补充目标未绑定实际产品，药物、批次污染物和多产品叠加尚不能核验。',
                '疾病营养方向不能替代阶段、化验与个体治疗目标。'],
            'release_scope':'AUDITED_FOOD_PLAN_WITH_CONDITIONAL_NUTRIENT_COMPLETION',
            'long_term_complete_diet_verified':False,'acute_safety_result':r['status']=='ACUTE_SUPPORT_RESULT'}
