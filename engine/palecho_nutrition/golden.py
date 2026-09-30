"""Reproducible healthy lifecycle cases and full audits. Never invent a recipe.

An absent recipe has UNKNOWN actual intake, not a zero-nutrient meal. Cases are
engineering examples, not individual clinical feeding recommendations.
"""
import json,collections
from .profile import assess,energy_start
from .runtime import solve,active_bounds,species_composition,substitute
from .requirements import required_nutrients

CASE_INPUTS=[
 ('DOG_EARLY_GROWTH','DOG',70,3,{'expected_adult_weight_kg':20,'neutered':False}),
 ('DOG_LATE_GROWTH_SMALL_MEDIUM','DOG',150,4,{'expected_adult_weight_kg':7,'neutered':False}),
 ('DOG_LATE_GROWTH_LARGE','DOG',150,16,{'expected_adult_weight_kg':35,'neutered':False}),
 ('DOG_ADULT','DOG',1095,10,{'growth_complete':True}),
 ('DOG_HEALTHY_SENIOR','DOG',4383,10,{'growth_complete':True,'life_stage_hint':'SENIOR'}),
 ('CAT_GROWTH','CAT',150,2.5,{'neutered':False}),
 ('CAT_ADULT','CAT',1095,4,{}),
 ('CAT_HEALTHY_SENIOR','CAT',4383,4,{}),
]

def cases(store):
    for case,sp,age,w,extra in CASE_INPUTS:
        p=dict(species=sp,breed='MIXED',age_days=age,sex='FEMALE',neutered=True,weight_kg=w,bcs=5,muscle_condition='NORMAL',activity='LOW',weight_trend='STABLE',diseases=[],recent_abnormalities=[],current_diet='COMPLETE_COMMERCIAL',allergies=[],dislikes=[],purpose='COMPLETE_DIET',weaned=True,**{})
        p.update(extra)
        note='Synthetic healthy-case input; energy is an initial estimate, not a measured individual requirement.'
        if sp=='CAT' and case=='CAT_GROWTH':
            a=assess(p,store);p['energy_target_kcal']=a['energy']['interval_kcal'][0]
            note+=' Kitten test selects the documented lower endpoint of the 4-9 month energy interval; no midpoint or universal kitten multiplier.'
        yield case,p,note

def composition_rows(store,sp):
    vectors={f['ingredient_id']:{} for f in store.rows('ingredients') if not f['toxicity_flag']}
    for r in store.rows('ingredient_nutrients'):
        if r['ingredient_id'] in vectors:vectors[r['ingredient_id']][r['nutrient_id']]=r['value']
    return {k:species_composition(v,sp) for k,v in vectors.items()}

def evaluate_golden(store):
    results=[]
    for case,p,note in cases(store):
        a=assess(p,store);result=solve(p,store);target=a['energy']['DER_start_kcal'];bounds=active_bounds(a,store)
        required=required_nutrients(p['species'],a['profile_id'])-{'ca_p_ratio'}
        vectors=composition_rows(store,p['species']);foods=[f for f in store.rows('ingredients') if not f['toxicity_flag']]
        per_food=[]
        for f in foods:
            missing=sorted(n for n in required|{'water'} if vectors[f['ingredient_id']].get(n) is None)
            per_food.append({'ingredient_id':f['ingredient_id'],'name_zh':f['name_zh'],'food_state':f['food_state'],'weight_basis':f['weight_basis'],
                'missing_nutrients':missing,'missing_count':len(missing),'known':len(required|{'water'})-len(missing),'total':len(required|{'water'}),'recipe_eligible':f['recipe_eligible']})
        per_food.sort(key=lambda r:(r['missing_count'],r['ingredient_id']))
        universal=sorted(set.intersection(*(set(f['missing_nutrients']) for f in per_food)))
        actual=result.get('nutrition_audit',{}).get('rows')
        if actual is None:
            actual=[]
            for b in bounds:
                established=b.minimum is not None or b.maximum is not None
                actual.append(dict(constraint_id=b.id,nutrient_id=b.nutrient,actual=None,actual_daily=None,actual_per_1000_kcal_ME=None,actual_per_100g_DM=None,
                    minimum=b.minimum,target=[b.minimum,b.maximum],maximum=b.maximum,unit=b.unit,basis=b.basis,source_id=b.source_id,source_locator=b.source_locator,
                    minimum_daily_reference=None if target is None or b.basis!='PER_1000_KCAL_ME' or b.minimum is None else b.minimum*target/1000,
                    maximum_daily_reference=None if target is None or b.basis!='PER_1000_KCAL_ME' or b.maximum is None else b.maximum*target/1000,
                    dependency=b.dependency,status='UNKNOWN_NO_RECIPE' if established else 'NOT_ESTABLISHED_CONDITIONAL_REVIEW',
                    explanation='Daily minima are reference floors; protein-dependent arginine minimum requires actual recipe protein. DM daily upper cannot be derived without actual dry matter.'))
        actual.insert(0,dict(nutrient_id='me_'+p['species'].lower(),actual=None if 'grams' not in result else result['nutrition_audit']['actual_kcal_ME_per_day'],minimum=target*(1-store.config['energy_rounding_tolerance_fraction']),target=target,maximum=target*(1+store.config['energy_rounding_tolerance_fraction']),unit='kcal',basis='PER_DAY',source_id=a['energy']['source_id'],status='UNKNOWN_NO_RECIPE' if 'grams' not in result else result['nutrition_audit']['energy_status']))
        results.append({'case_id':case,'input':p,'case_note':note,'life_stage':a['life_stage'],'profile_id':a['profile_id'],'daily_energy_target':target,
            'energy_definition':'initial_estimated_energy_target','energy':a['energy'],'weight_basis':'COOKED_WEIGHT','portion_basis':'EDIBLE_WEIGHT',
            'recipe_status':'VALIDATED' if result['recipe_status']=='VALIDATED' else 'NEEDS_REVIEW' if result['recipe_status'] in ['NO_VALID_RECIPE','UNKNOWN_COMPOSITION','NEEDS_REVIEW','REQUIRES_PROFESSIONAL_REVIEW'] else 'INVALID',
            'engine_status':result['recipe_status'],'feasibility':'NOT_ASSESSABLE_MISSING_COMPOSITION' if result.get('ingredient_exclusions') and not result.get('nutrition_audit') else result['recipe_status'],
            'ingredients':None if 'grams' not in result else [{'ingredient_id':i,'grams':g,'weight_basis':store.keyed('ingredients','ingredient_id')[i]['weight_basis'],'portion_basis':'EDIBLE_WEIGHT'} for i,g in result['grams'].items()],
            'nutrient_audit':actual,'universal_unknowns':universal,'composition_readiness':per_food,'ingredient_exclusions':result.get('ingredient_exclusions',[]),
            'blocking_conflicts':[c for c in store.config['nutrition_conflicts'] if c['status']=='NEEDS_REVIEW' and c['species'] in ['BOTH',p['species']]],
            'reasons':result.get('reasons',[]),'complete_balanced_claim':result.get('complete_balanced_claim',False)})
    return results

def substitution_regression(store,golden):
    pairs=[('FDC_172389','FDC_171478'),('FDC_171477','FDC_168250'),('FDC_168250','FDC_170633'),('FDC_175177','FDC_174185')]
    # Real replacement regressions are only attempted after a VALIDATED baseline.
    base=next((r for r in golden if r['case_id']=='DOG_ADULT'),None);out=[]
    for old,new in pairs:
        if base['recipe_status']!='VALIDATED':out.append(dict(old=old,new=new,status='NO_VALID_SUBSTITUTION',executed=False,reason='BLOCKED_BY_BASELINE_RECIPE',blocking_constraints=base['universal_unknowns']))
        else:
            r=substitute(base['input'],old,new,store)
            out.append(dict(old=old,new=new,status=r['substitution_status'],executed=True,engine_result=r))
    return out
