"""Public offline API. Never authorizes a recipe from a solver success flag alone."""
import hashlib, json
from dataclasses import replace
from .profile import assess
from .solver import Food,NutrientBound,solve_math,audit_math
from .store import matches
from .units import convert_basis
from .requirements import required_nutrients, profile_coverage_issues

def species_composition(vector,species):
    result=dict(vector)
    # Both activities are independently derived and traceable in Master.
    if 'vitamin_a_'+species.lower() in result:result['vitamin_a']=result['vitamin_a_'+species.lower()]
    return result

def _digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def active_bounds(assessment,store):
    bounds=[]
    for r in store.rows('requirements'):
        if r['profile_id']!=assessment['profile_id'] or not r['enforced'] or not matches(json.loads(r['condition_json']),assessment['pet']):continue
        bounds.append(NutrientBound(r['requirement_id'],r['nutrient_id'],r['unit'],r['basis'],r['minimum'],r['maximum'],r['source_id'],r['source_locator'],json.loads(r['dependency_json'])))
    for r in assessment['disease_constraints']:
        if not r['action'].startswith('HARD'):continue
        bounds.append(NutrientBound('DISEASE:'+r['rule_id'],r['nutrient_id'],r['unit'],r['basis'],
                      r['value'] if r['action']=='HARD_MIN' else None,r['value'] if r['action']=='HARD_MAX' else None,
                      r['source_id'],r['source_locator'],strict_minimum=r['operator']=='GT',strict_maximum=r['operator']=='LT'))
    return bounds

def _candidates(a,store,excluded=()):
    pet=a['pet'];sp=pet['species'];foods=[];rejected=[];nutrients=store.keyed('nutrients','nutrient_id')
    required={b.nutrient for b in active_bounds(a,store) if b.minimum is not None or b.maximum is not None}-{'ca_p_ratio'}
    required|=required_nutrients(sp,a['profile_id'])-{'ca_p_ratio'}
    required|={'calcium','phosphorus','water','me_'+sp.lower()}
    vector={f['ingredient_id']:{} for f in store.rows('ingredients')}
    records={}
    for r in store.rows('ingredient_nutrients'):
        vector[r['ingredient_id']][r['nutrient_id']]=r['value'];records[(r['ingredient_id'],r['nutrient_id'])]=r
    sources=store.keyed('sources','source_id');supplements={r['ingredient_id']:r for r in store.rows('supplements') if r['ingredient_id']}
    disease_ids={d['id'] for d in pet['diseases']}
    for f in sorted(store.rows('ingredients'),key=lambda f:f['ingredient_id']):
        reasons=[];i=f['ingredient_id'];v=species_composition(vector[i],sp)
        tags=set((f['allergen_tags'] or '').split(';'))|{f['food_category'],i}
        if i in excluded:reasons.append('EXCLUDED_BY_REPLACEMENT')
        if tags&set(pet['allergies']):reasons.append('ALLERGEN_EXCLUSION')
        if tags&set(pet['dislikes']):reasons.append('USER_REJECTED')
        if 'available_ingredients' in pet and i not in pet['available_ingredients']:reasons.append('UNAVAILABLE')
        if f['toxicity_flag']:reasons.append('TOXICITY_EXCLUSION')
        if not f[sp.lower()+'_allowed']:reasons.append('SPECIES_EXCLUSION')
        stage='WEANED_GROWTH' if 'GROWTH' in a['profile_id'] else a['life_stage'].split('_')[-1]
        if stage not in (f['life_stage_allowed'] or '').split(';'):reasons.append('LIFE_STAGE_EXCLUSION')
        if f['disease_allowed']=='NONE' and disease_ids:reasons.append('DISEASE_EXCLUSION')
        if not f['recipe_eligible'] or f['review_status']!='APPROVED':reasons.append('INGREDIENT_NOT_APPROVED')
        if f['raw_or_cooked']=='RAW':reasons.append('RAW_TO_COOKED_YIELD_RETENTION_NOT_VALIDATED')
        if f['raw_or_cooked']=='COOKED' and f.get('weight_basis')!='COOKED_WEIGHT':reasons.append('WEIGHT_BASIS_MISMATCH')
        if f.get('portion_basis')!='EDIBLE_WEIGHT':reasons.append('EDIBLE_PORTION_UNDEFINED')
        provenance={}
        for n in sorted(required):
            key='vitamin_a_'+sp.lower() if n=='vitamin_a' else n
            r=records.get((i,key));s=sources.get(r['source_id']) if r else None
            if not r or not s or not r['source_locator'] or s['read_status'] in ['BIBLIOGRAPHY_ONLY','ABSTRACT_ONLY','NEEDS_REVIEW']:
                reasons.append('NUTRIENT_SOURCE_MISSING:'+n)
            elif r['food_state']!=f['food_state'] or r['basis']!='PER_100G_AS_FED' or r['unit']!=nutrients[key]['canonical_unit']:
                reasons.append('NUTRIENT_UNIT_BASIS_STATE_INVALID:'+n)
            else:provenance[n]={'source_id':r['source_id'],'source_locator':r['source_locator'],'additional_source_id':r['additional_source_id'],'food_state':r['food_state']}
            if r and r['value'] is not None and (key in ['vitamin_a_dog','vitamin_a_cat','vitamin_d3_activity'] or r.get('additional_source_id')):
                conversion=sources.get(r.get('additional_source_id'))
                if not conversion or conversion['read_status'] in ['BIBLIOGRAPHY_ONLY','ABSTRACT_ONLY','NEEDS_REVIEW'] or conversion['source_type']=='PROJECT_POLICY':reasons.append('NUTRIENT_CONVERSION_SOURCE_MISSING:'+n)
        if i in supplements:
            s=supplements[i]
            if not s['auto_use_allowed'] or not s['exact_composition_json'] or not s['batch_or_spec'] or not s['assay_source_id'] or not s['usage_limit_json'] or s['review_status']!='APPROVED':reasons.append('SUPPLEMENT_COMPOSITION_NOT_VERIFIED')
        missing=sorted(n for n in required if v.get(n) is None)
        if missing:reasons.append({'UNKNOWN_NUTRIENTS':missing})
        if f['precision_g'] is None or f['max_amount'] is None:reasons.append('DISPENSING_LIMITS_UNKNOWN')
        if pet.get('budget_cny_per_day') is not None and f['unit_price_cny_per_kg'] is None:reasons.append('PRICE_UNKNOWN_FOR_HARD_BUDGET')
        maximum=f['max_amount'];minimum=f['min_amount'] or 0
        for r in store.rows('ingredient_limits'):
            if r['ingredient_id']!=i or r['species'] not in ['BOTH',sp]:continue
            if r['life_stage'] not in ['ALL',a['life_stage']]:continue
            if r['disease_id'] is not None and r['disease_id'] not in disease_ids:continue
            if r['operator']=='EXCLUDE':reasons.append({'LIMIT':r['limit_id'],'source_id':r['source_id']})
            if r['operator']=='MAX_AMOUNT':maximum=r['value'] if maximum is None else min(maximum,r['value'])
            if r['operator']=='MIN_AMOUNT':minimum=max(minimum,r['value'])
        if maximum is not None and minimum>maximum:reasons.append('INGREDIENT_AMOUNT_CONFLICT')
        if reasons:rejected.append({'ingredient_id':i,'reasons':reasons});continue
        # If measured prices are absent, use only explicit editorial cost tiers, never invented CNY.
        cost=(f['unit_price_cny_per_kg']/1000 if f['unit_price_cny_per_kg'] is not None else {'LOW':1,'MEDIUM':2,'HIGH':3,'UNKNOWN':4}[f['cost_level_cn']])
        foods.append(Food(i,v,v['me_'+sp.lower()],v['water'],maximum,f['precision_g'],minimum,
                          0 if f['availability_cn']=='COMMON_USER_PRIORITY' else 1,cost,0 if f['preparation_difficulty']=='LOW' else 1,f['source_id'],nutrient_sources=provenance))
    definitions=store.keyed('ingredients','ingredient_id')
    if any(definitions[f.id]['unit_price_cny_per_kg'] is None for f in foods):
        foods=[replace(f,cost_per_g={'LOW':1,'MEDIUM':2,'HIGH':3,'UNKNOWN':4}[definitions[f.id]['cost_level_cn']]) for f in foods]
    return foods,rejected

def _shares(a,store,foods):
    result=[];ids={f.id for f in foods};diseases={d['id'] for d in a['pet']['diseases']}
    for r in store.rows('ingredient_limits'):
        if r['ingredient_id'] not in ids or r['operator']!='MAX_SHARE':continue
        if r['species'] not in ['BOTH',a['pet']['species']] or r['life_stage'] not in ['ALL',a['life_stage']]:continue
        if r['disease_id'] is not None and r['disease_id'] not in diseases:continue
        result.append({'id':r['limit_id'],'ingredient_id':r['ingredient_id'],'basis':r['basis'],'maximum':r['value'],'source_id':r['source_id']})
    return result

def recipe_digest(grams,assessment,store):
    return _digest({'grams':grams,'species':assessment['pet']['species'],'profile_id':assessment['profile_id'],
                    'disease_ids':sorted(d['id'] for d in assessment['pet']['diseases']),
                    'data_content_sha256':store.meta['data_content_sha256']})

def bound_conflicts(bounds):
    """Detect direct bound contradictions before food selection; no assumed caloric density."""
    groups={};conflicts=[]
    for b in bounds:
        basis='PER_1000_KCAL_ME' if b.basis in ['PER_1000_KCAL_ME','PER_100_KCAL_ME','PER_MJ_ME'] else b.basis
        def cv(v):return None if v is None else convert_basis(v,b.basis,basis,me_kcal=1000)
        groups.setdefault((b.nutrient,basis),[]).append((b,cv(b.minimum),cv(b.maximum)))
    for (nut,basis),rows in groups.items():
        lows=[x for x in rows if x[1] is not None];highs=[x for x in rows if x[2] is not None]
        if not lows or not highs:continue
        lo=max(lows,key=lambda x:x[1]);hi=min(highs,key=lambda x:x[2])
        if lo[1]>hi[2] or lo[1]==hi[2] and (lo[0].strict_minimum or hi[0].strict_maximum):
            conflicts.append({'nutrient_id':nut,'basis':basis,'minimum':lo[1],'maximum':hi[2],
                              'constraint_ids':[lo[0].id,hi[0].id],'source_ids':[lo[0].source_id,hi[0].source_id]})
    return conflicts

def solve(pet,store,*,excluded=(),required=()):
    a=assess(pet,store)
    a['auto_recipe_allowed']=False
    a['production_ready']=store.meta['production_ready'];a['data_version']=store.meta['data_version']
    if a.get('profile_id') and 'disease_constraints' in a:
        conflicts=bound_conflicts(active_bounds(a,store))
        if conflicts and a['recipe_status']!='AUTO_RECIPE_BLOCKED':
            a.update(recipe_status='REQUIRES_PROFESSIONAL_REVIEW',constraint_conflicts=conflicts,relaxed_constraints=False)
    if a['recipe_status'] is not None:return a
    coverage=profile_coverage_issues(store.rows('requirements'),a['profile_id'])
    if coverage:
        a.update(recipe_status='NEEDS_REVIEW',reasons=coverage,complete_balanced_claim=False);return a
    foods,rejected=_candidates(a,store,excluded)
    a['ingredient_exclusions']=rejected
    if not foods:
        a.update(recipe_status='NO_VALID_RECIPE',reasons=['CANDIDATES_EMPTY: no ingredient has the required evidence, complete applicable vector and reviewed dispensing limits.'],relaxed_constraints=False)
        return a
    if a['pet']['diseases']:
        a.update(recipe_status='REQUIRES_PROFESSIONAL_REVIEW',reasons=['DISEASE_PRODUCTION_FROZEN'],production_recipe=False);return a
    if a['reassessment_needed']:
        a.update(recipe_status='REQUIRES_PROFESSIONAL_REVIEW',reasons=['BCS/MCS, weight trend or recent symptoms require an individualized energy and daily nutrient plan.']);return a
    if a['energy']['DER_start_kcal'] is None:
        a.update(recipe_status='REQUIRES_PROFESSIONAL_REVIEW',reasons=['Energy interval needs an individual target or the animal is outside the model domain.']);return a
    bounds=active_bounds(a,store);shares=_shares(a,store,foods)
    result=solve_math(foods,bounds,a['energy']['DER_start_kcal'],energy_tolerance=store.config['energy_rounding_tolerance_fraction'],
                      required_foods=required,budget=a['pet'].get('budget_cny_per_day'),food_shares=shares)
    if result['status']!='NUMERIC_PASS':
        a.update(recipe_status=result['status'],solver_diagnostics=result)
        if result['status']=='NO_VALID_RECIPE' and any(c['id'].startswith('DISEASE:') for c in result.get('conflicts',[])):
            a['recipe_status']='REQUIRES_PROFESSIONAL_REVIEW'
        return a
    digest=recipe_digest(result['grams'],a,store)
    a['nutrition_audit']=result['audit'];a['recipe_digest']=digest
    unresolved=[c['id'] for c in store.config.get('nutrition_conflicts',[]) if c['status']=='NEEDS_REVIEW' and c.get('species','BOTH') in ['BOTH',a['pet']['species']]]
    approved=not unresolved and store.meta['production_ready'] and digest in store.meta.get('approved_recipe_hashes',[])
    if not approved:
        a.update(recipe_status='NEEDS_REVIEW',reasons=['Numerical audit is insufficient: no matching independent recipe/process approval.']+unresolved,complete_balanced_claim=False)
        return a
    a.update(recipe_status='VALIDATED',grams=result['grams'],complete_balanced_claim=True,auto_recipe_allowed=True,solver=result['method'])
    a['nutrition_audit']['complete_food_claim']=True
    a['feeding_plan_hash']=_digest({'pet':a['pet'],'grams':a['grams'],'recipe_digest':digest})
    return a

def audit_recipe(pet,grams,store):
    a=assess(pet,store)
    if a['recipe_status'] is not None:return a
    if a['pet']['diseases']:return {'recipe_status':'REQUIRES_PROFESSIONAL_REVIEW','reasons':['DISEASE_PRODUCTION_FROZEN'],'complete_balanced_claim':False}
    coverage=profile_coverage_issues(store.rows('requirements'),a['profile_id'])
    if coverage:return {'recipe_status':'NEEDS_REVIEW','reasons':coverage,'complete_balanced_claim':False}
    if type(grams) is not dict or not grams:return {'recipe_status':'INVALID_INPUT','reasons':['Recipe grams must be a nonempty object']}
    foods,rejected=_candidates(a,store)
    unknown=set(grams)-{f.id for f in foods}
    if unknown:
        return {'recipe_status':'NO_VALID_RECIPE','complete_balanced_claim':False,
                'reasons':['Recipe contains unapproved, contraindicated or composition-incomplete ingredients'],
                'ingredient_exclusions':[r for r in rejected if r['ingredient_id'] in unknown]}
    target=a['energy']['DER_start_kcal']
    if target is None or a['reassessment_needed']:return {'recipe_status':'REQUIRES_PROFESSIONAL_REVIEW','reasons':['Individual feeding target required']}
    try:audit=audit_math(foods,active_bounds(a,store),grams,target,store.config['energy_rounding_tolerance_fraction'],food_shares=_shares(a,store,foods),budget=a['pet'].get('budget_cny_per_day'))
    except ValueError as e:return {'recipe_status':'INVALID_INPUT','reasons':[str(e)]}
    unresolved=any(c['status']=='NEEDS_REVIEW' and c.get('species','BOTH') in ['BOTH',a['pet']['species']] for c in store.config.get('nutrition_conflicts',[]))
    approved=not unresolved and store.meta['production_ready'] and recipe_digest(grams,a,store) in store.meta.get('approved_recipe_hashes',[])
    passed=audit['all_numeric_requirements_pass']
    return {'recipe_status':('VALIDATED' if approved else 'NEEDS_REVIEW') if passed else 'NO_VALID_RECIPE',
            'complete_balanced_claim':bool(passed and approved),'nutrition_audit':audit}

def substitute(pet,old_ingredient_id,new_ingredient_id,store):
    groups=store.rows('substitution_groups')
    old={r['group_id'] for r in groups if r['ingredient_id']==old_ingredient_id}
    new={r['group_id'] for r in groups if r['ingredient_id']==new_ingredient_id}
    if not old&new or old_ingredient_id==new_ingredient_id:
        return {'recipe_status':'INVALID_INPUT','substitution_status':'NO_VALID_SUBSTITUTION','reasons':['Distinct ingredients in a shared candidate group required']}
    baseline=solve(pet,store)
    if baseline['recipe_status']!='VALIDATED':
        return {'recipe_status':'NEEDS_REVIEW','substitution_status':'BLOCKED_BY_BASELINE_RECIPE','replacement_mode':'FULL_REOPTIMIZATION','fixed_weight_conversion':False,'grams':None}
    from .adult_strategy import replan_replacement
    if baseline.get('life_stage') in ['DOG_ADULT','CAT_ADULT']:
        return replan_replacement(pet,old_ingredient_id,new_ingredient_id,store)
    result=solve(pet,store,excluded=[old_ingredient_id],required=[new_ingredient_id])
    result['replacement_mode']='FULL_REOPTIMIZATION';result['fixed_weight_conversion']=False
    result['substitution_status']='SUBSTITUTION_VALID' if result['recipe_status']=='VALIDATED' else 'NO_VALID_SUBSTITUTION'
    return result

def nutrient_food_map(store,grams=None):
    foods=store.keyed('ingredients','ingredient_id');out=[]
    for n in store.rows('nutrients'):
        if n['role']!='PROFILE_NUTRIENT':continue
        sources=[]
        for r in store.rows('ingredient_nutrients'):
            if r['nutrient_id']==n['nutrient_id'] and r['value'] is not None and r['value']>0:
                i=r['ingredient_id'];f=foods[i]
                sources.append({'ingredient_id':i,'name_zh':f['name_zh'],'value':r['value'],'unit':r['unit'],'basis':r['basis'],
                                'food_state':r['food_state'],'source_id':r['source_id'],'recipe_eligible':f['recipe_eligible'],
                                'actual_contribution':None if grams is None or i not in grams else r['value']*grams[i]/100})
        out.append({'nutrient_id':n['nutrient_id'],'category':n['display_category'],'name_zh':n['name_zh'],
                    'candidate_sources':sorted(sources,key=lambda r:(-r['value'],r['ingredient_id'])),'candidate_only':True})
    return out
