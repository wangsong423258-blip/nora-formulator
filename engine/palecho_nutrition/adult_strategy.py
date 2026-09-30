"""Offline adult food-first planning and whole-diet contribution tracing.

This endpoint can produce COMPUTATIONAL_COMPLETE, never VALIDATED. Clinical
release continues through the existing independently approved recipe path.
"""
import json
from .profile import assess
from .requirements import required_nutrients,profile_coverage_issues
from .runtime import active_bounds,species_composition,_shares,_digest
from .whole_diet import Interval,NutrientSource,computational_source_issues,food_first_math
from .supplement_models import contribution
from .units import convert_unit

DEFAULT_FOODS=('FDC_171477','FDC_173424','FDC_169757','FDC_168449')
PREFERRED={'taurine':'DEFINED_NUTRIENT_SOURCE','calcium':'DEFINED_NUTRIENT_SOURCE','epa':'STANDARDIZED_OIL','dha':'STANDARDIZED_OIL','epa_dha':'STANDARDIZED_OIL',**{n:'MULTI_NUTRIENT_PREMIX' for n in ['iodine','zinc','copper','manganese','selenium','vitamin_d','vitamin_e','b9','b12','biotin','choline']}}

def supplement_database(store):
    """Preserve the original guarantee and expose separately normalized per-g fields."""
    result=[]
    units=store.keyed('nutrients','nutrient_id')
    aliases={'moisture':'water','folic acid':'b9','niacin':'b3','pantothenic acid':'b5','phylloquinone':'vitamin_k1','phylloquinone*':'vitamin_k1','pyridoxine':'b6','riboflavin':'b2','thiamine':'b1','vitamin b12':'b12','vitamin a':'vitamin_a','vitamin d2':'vitamin_d2','vitamin e':'vitamin_e'}
    for s in store.rows('supplements'):
        p=json.loads(s['evidence_package_json']);p['source_type']=s.get('source_type') or s['model_type']
        p['name']=s['name_zh'];p['product']=p.get('product_name');p['batch_or_lot']=p.get('lot_batch')
        p['min_usage']=None;p['max_usage']=s['max_daily_amount'];p['evidence_level']=p.get('evidence_strength')
        p['nutrient_matrix']=[]
        for r in store.rows('supplement_nutrients'):
            if r['supplement_id']!=s['supplement_id']:continue
            v=contribution(r,1,r['serving_mass_g'])
            canonical=aliases.get(r['exact_nutrient'].lower(),r['exact_nutrient'].lower());canonical_unit=units.get(canonical,{}).get('canonical_unit',v['unit'])
            normalized={k:convert_unit(v[k],v['unit'],canonical_unit) for k in ['actual_value','guaranteed_min','guaranteed_max','typical_value']}
            p['nutrient_matrix'].append({**r,'nutrient':canonical,'canonical_unit':canonical_unit,'canonical_min_per_g':normalized['guaranteed_min'],'canonical_max_per_g':normalized['guaranteed_max'],'canonical_actual_per_g':normalized['actual_value'],'chemical_form':('ERGOCALCIFEROL_D2' if canonical=='vitamin_d2' else 'FOLIC_ACID' if canonical=='b9' else None),'amount_per_g':v['actual_value'],'per_g_guaranteed_min':v['guaranteed_min'],'per_g_guaranteed_max':v['guaranteed_max'],'per_g_typical_value':v['typical_value'],'per_g_unit':v['unit'],'per_g_basis':'PER_1G_AS_SOLD','amount_per_g_evidence_type':r['evidence_type']})
        p['amount_per_g']=None;p['chemical_form']=p.get('chemical_form');p['nutrient']=p.get('exact_nutrient')
        p['formal_use_allowed']=s['auto_use_allowed']
        result.append(p)
    return result

def _supp_sources(store,sp,required):
    out=[];rejected=[];definitions=store.keyed('supplements','supplement_id');units=store.keyed('nutrients','nutrient_id')
    for p in supplement_database(store):
        d=definitions[p['supplement_id']];reasons=[]
        if p['evidence_acceptance']!='ACCEPTED':reasons.append('SUPPLEMENT_'+p['evidence_acceptance'])
        if not p['complete_matrix']:reasons.append('COMPLETE_MATRIX_MISSING')
        if not d['auto_use_allowed'] or d['review_status']!='APPROVED':reasons.append('SUPPLEMENT_NOT_FORMALLY_ELIGIBLE')
        if sp not in (p.get('species_allowed') or []):reasons.append('SPECIES_NOT_CONFIRMED')
        if 'ADULT' not in (p.get('life_stage_allowed') or []):reasons.append('ADULT_USE_NOT_CONFIRMED')
        if not d['precision_g'] or not d['max_daily_amount'] or not d['usage_limit_json']:reasons.append('EVIDENCED_USAGE_LIMIT_OR_PRECISION_MISSING')
        v={}
        for r in p['nutrient_matrix']:
            n=r['nutrient']
            if n not in units or r['canonical_unit']!=units[n]['canonical_unit']:continue
            actual=r['canonical_actual_per_g'];low=actual if actual is not None else r['canonical_min_per_g'];high=actual if actual is not None else r['canonical_max_per_g']
            v[n]=Interval(None if low is None else low*100,None if high is None else high*100,r['source_id'],r['source_locator'],r['evidence_type'])
        me=v.get('me_'+sp.lower());water=v.get('water')
        if me is None or water is None:reasons.append('ME_OR_DM_CARRIER_UNKNOWN')
        missing=sorted(required-set(v))
        if missing:reasons.append({'MATRIX_MISSING_NUTRIENTS':missing})
        # Vitamin D2 is intentionally not mapped to D3 activity or total D.
        if reasons:rejected.append({'source_id':p['supplement_id'],'reasons':reasons});continue
        out.append(NutrientSource(p['supplement_id'],p['source_type'],v,me,water,d['max_daily_amount'],d['precision_g'],species=tuple(p['species_allowed']),life_stages=tuple(p['life_stage_allowed']),food_state='AS_SOLD',evidence_acceptance='ACCEPTED',complete_matrix=True,safety_envelope_source=d['usage_limit_json'],nutrient_units={n:r['canonical_unit'] for n,r in units.items()}))
    return out,rejected

def food_bound_review_hash(record,food,species,requirements):
    # Scope excludes the signature payload itself, avoiding a self-referential hash.
    return _digest({'record':{k:v for k,v in record.items() if k!='one_sided_safety_review_json'},'food':food,'species':species,'requirements':requirements})

def plan_adult(pet,store,*,food_ids=None,extra_food_ids=(),required_food_ids=()):
    a=assess(pet,store);sp=a['pet']['species'];profile=a.get('profile_id')
    selected=list(food_ids if food_ids is not None else store.config.get('food_supplement_strategy',{}).get('adult_candidate_food_ids',DEFAULT_FOODS))
    base={'recipe_status':'NEEDS_REVIEW','computational_status':'NOT_COMPUTATIONAL_COMPLETE','profile_id':profile,'data_hash':store.meta['data_content_sha256'],'grams':None,'clinical_release':False,'production_recipe':False,'complete_balanced_claim':False,'planned_food_ids':selected,'planned_food_count':len(selected),'used_food_count':0,'used_supplement_count':0,'supplement_doses':None,'required_food_count':[4,7],'blockers':[]}
    if a['recipe_status'] is not None or a['pet']['diseases'] or a.get('life_stage') not in ['DOG_ADULT','CAT_ADULT']:
        base['blockers']=['ADULT_HEALTHY_SCOPE_ONLY',a.get('recipe_status')];return base
    base['energy_target_kcal']=a['energy']['DER_start_kcal']
    if base['energy_target_kcal'] is None or a['reassessment_needed']:base['blockers']=['INDIVIDUAL_ENERGY_ASSESSMENT_REQUIRED'];return base
    if len(set(selected+list(extra_food_ids)))!=len(selected)+len(extra_food_ids):raise ValueError('Duplicate candidate foods')
    definitions=store.keyed('ingredients','ingredient_id');nut=store.keyed('nutrients','nutrient_id');source_defs=store.keyed('sources','source_id')
    if not set(selected+list(extra_food_ids))<=set(definitions):raise ValueError('Unknown food candidate')
    bounds=active_bounds(a,store);required=required_nutrients(sp,profile)-{'ca_p_ratio'}
    required|={b.nutrient for b in bounds if b.nutrient!='ca_p_ratio' and (b.minimum is not None or b.maximum is not None)}
    required|={'calcium','phosphorus','water','me_'+sp.lower()}
    records={(r['ingredient_id'],r['nutrient_id']):r for r in store.rows('ingredient_nutrients')}
    foods=[];exclusions=[];catalog=[]
    for i in selected+list(extra_food_ids):
        f=definitions[i];v={};reasons=[]
        tags={i,f['food_category']}|set((f['allergen_tags'] or '').split(';'))
        if tags&(set(a['pet']['allergies'])|set(a['pet']['dislikes'])):reasons.append('ALLERGY_OR_USER_EXCLUSION')
        if 'available_ingredients' in a['pet'] and i not in a['pet']['available_ingredients']:reasons.append('UNAVAILABLE')
        if f['toxicity_flag'] or not f[sp.lower()+'_allowed']:reasons.append('FOOD_SAFETY_OR_SPECIES_EXCLUSION')
        if 'ADULT' not in (f['life_stage_allowed'] or '').split(';'):reasons.append('LIFE_STAGE_NOT_SUPPORTED')
        if f['weight_basis']!='COOKED_WEIGHT' or f['portion_basis']!='EDIBLE_WEIGHT':reasons.append('COOKED_EDIBLE_STATE_REQUIRED')
        for n in sorted(required):
            key='vitamin_a_'+sp.lower() if n=='vitamin_a' else n;r=records.get((i,key));value=r['value'] if r else None
            if r:
                catalog.append({'ingredient_id':i,'nutrient':n,'value_per_100g':value,'unit':r['unit'],'basis':r['basis'],'food_state':r['food_state'],'source_id':r['source_id'],'source_locator':r['source_locator'],'daily_food_contribution':None,'status':'KNOWN_REFERENCE' if value is not None else 'UNKNOWN'})
            if value is None:
                lo=r.get('lower_bound') if r else None;hi=r.get('upper_bound') if r else None;bs=source_defs.get(r.get('bound_source_id')) if r else None
                if lo is None or not bs or bs['read_status'] in ['BIBLIOGRAPHY_ONLY','ABSTRACT_ONLY','NEEDS_REVIEW'] or not r.get('bound_source_locator'):
                    reasons.append('UNKNOWN:'+n);continue
                if hi is None:
                    # Lack of an established UL is not evidence of unlimited safety.
                    policy=json.loads(r.get('one_sided_safety_review_json') or '{}')
                    scope=food_bound_review_hash(r,f,sp,[b for b in store.rows('requirements') if b['profile_id']==profile])
                    if policy.get('input_hash')!=scope or not all(policy.get(k) for k in ['reviewer_name','reviewer_credential','review_date']) or policy.get('decision')!='APPROVED' or sp not in policy.get('species',[]) or policy.get('safety_source_id') not in source_defs:reasons.append('UNKNOWN_UPPER_SAFETY_SCOPE:'+n)
                v[n]=Interval(lo,hi,r['bound_source_id'],r['bound_source_locator'],'SPECIFICATION_RANGE')
                if r['food_state']!=f['food_state'] or r['basis']!='PER_100G_AS_FED' or r['unit']!=nut[key]['canonical_unit']:reasons.append('DATA_METHOD_OR_UNIT_MISMATCH:'+n)
                continue
            src=source_defs.get(r['source_id'])
            if not src or src['read_status'] in ['BIBLIOGRAPHY_ONLY','ABSTRACT_ONLY','NEEDS_REVIEW'] or not r['source_locator']:reasons.append('SOURCE_NOT_USABLE:'+n)
            if r['food_state']!=f['food_state'] or r['basis']!='PER_100G_AS_FED' or r['unit']!=nut[key]['canonical_unit']:reasons.append('DATA_METHOD_OR_UNIT_MISMATCH:'+n)
            if r.get('additional_source_id'):
                csrc=source_defs.get(r['additional_source_id'])
                if not csrc or csrc['read_status'] in ['BIBLIOGRAPHY_ONLY','ABSTRACT_ONLY','NEEDS_REVIEW']:reasons.append('CONVERSION_SOURCE_MISSING:'+n)
            v[n]=Interval(value,value,r['source_id'],r['source_locator'],'DATABASE_POINT')
        if not f['me_method'] or not f['assay_scope']:reasons.append('ME_METHOD_APPLICABILITY_NOT_CONFIRMED')
        if f.get('me_source_type_'+sp.lower()) not in ['MEASURED','DATABASE','CALCULATED']:reasons.append('ME_SOURCE_TYPE_UNKNOWN')
        if f.get('me_source_type_'+sp.lower())=='CALCULATED' and f['me_method'] not in {'FEDIAF_2025_NATURAL','FEDIAF_2025_NATURAL_'+sp}:reasons.append('INGREDIENT_ME_NOT_APPROVED_FOR_ADDITIVE_WHOLE_DIET_MODEL')
        maximum=f['max_amount'];minimum=f['min_amount'] or 0
        for limit in store.rows('ingredient_limits'):
            if limit['ingredient_id']!=i or limit['species'] not in ['BOTH',sp] or limit['life_stage'] not in ['ALL',a['life_stage']] or limit['disease_id'] is not None:continue
            if limit['operator']=='EXCLUDE':reasons.append('LIMIT_EXCLUSION:'+limit['limit_id'])
            if limit['operator']=='MAX_AMOUNT':maximum=limit['value'] if maximum is None else min(maximum,limit['value'])
            if limit['operator']=='MIN_AMOUNT':minimum=max(minimum,limit['value'])
        if maximum is None or f['precision_g'] is None:reasons.append('REVIEWED_PORTION_AND_DISPENSING_LIMITS_MISSING')
        elif maximum<minimum:reasons.append('PORTION_LIMIT_CONFLICT')
        # Optional known nutrients remain available to every contribution audit.
        for (ii,n),r in records.items():
            if ii==i and n not in v and n not in required and r['value'] is not None and r['food_state']==f['food_state'] and r['basis']=='PER_100G_AS_FED':v[n]=Interval(r['value'],r['value'],r['source_id'],r['source_locator'],'DATABASE_POINT')
        if reasons:exclusions.append({'source_id':i,'reasons':reasons});continue
        foods.append(NutrientSource(i,'FOOD',v,v['me_'+sp.lower()],v['water'],maximum,f['precision_g'],minimum,0 if f['availability_cn']=='COMMON_USER_PRIORITY' else 1,None if f['unit_price_cny_per_kg'] is None else f['unit_price_cny_per_kg']/1000,0 if f['preparation_difficulty']=='LOW' else 1,species=(sp,),life_stages=('ADULT',),food_state=f['food_state'],evidence_acceptance='ACCEPTED',nutrient_units={n:r['canonical_unit'] for n,r in nut.items()}))
    supplements,rejected=_supp_sources(store,sp,required)
    coverage=profile_coverage_issues(store.rows('requirements'),profile)
    conflicts=[c['id'] for c in store.config['nutrition_conflicts'] if c['status']=='NEEDS_REVIEW' and c.get('species','BOTH') in ['BOTH',sp]]
    issues=computational_source_issues(foods+supplements,sp,'ADULT')
    result=food_first_math([f for f in foods if f.id in selected],[f for f in foods if f.id in extra_food_ids],supplements,bounds,base['energy_target_kcal'],energy_tolerance=store.config['energy_rounding_tolerance_fraction'],min_foods=4,max_foods=7,required=required_food_ids,budget=a['pet'].get('budget_cny_per_day'),food_shares=_shares(a,store,foods))
    base.update(solver_result=result,food_exclusions=exclusions,supplement_exclusions=rejected,food_reference_matrix=catalog,blockers=coverage+conflicts+issues,preferred_sources=PREFERRED,contributions=None)
    if result['status']=='NUMERIC_PASS' and not base['blockers']:
        grams=result['grams'];by={s.id:s for s in foods+supplements}
        base.update(recipe_status='NEEDS_REVIEW',computational_status='COMPUTATIONAL_COMPLETE',grams=grams,used_food_count=sum(by[i].source_type=='FOOD' for i in grams),used_supplement_count=sum(by[i].source_type!='FOOD' for i in grams),supplement_doses={i:g for i,g in grams.items() if by[i].source_type!='FOOD'},contributions=result['audit']['contributions'])
        base['computational_recipe_hash']=_digest({'pet':a['pet'],'grams':grams,'data_hash':base['data_hash']})
        base['final_diet_validation_plan']=final_diet_validation_plan(base,store)
    else:base['blockers']+=result.get('blockers',[])+(['FOOD_COMPOSITION_OR_PROCESS_INPUTS'] if exclusions else [])+(['NO_ACCEPTED_COMPLETE_SUPPLEMENT_MATRIX'] if not supplements else [])
    return base

def final_diet_validation_plan(result,store):
    if result.get('computational_status')!='COMPUTATIONAL_COMPLETE' or not result.get('grams'):return {'status':'BLOCKED_BY_COMPUTATIONAL_BASELINE','samples':[]}
    return {'status':'DRAFT_REQUIRES_ACTUAL_BATCH_PROTOCOL','recipe_hash':result['computational_recipe_hash'],'data_hash':store.meta['data_content_sha256'],'sampling_object':'FINAL_COOKED_MIXED_DIET_AS_CONSUMED','samples':[{'source_id':i,'planned_g_per_day':g,'lot':None,'actual_weight':None,'cooking_method':store.keyed('ingredients','ingredient_id').get(i,{}).get('food_state','AS_SOLD_SUPPLEMENT'),'cooking_time_minutes':None,'internal_temperature_C':None,'cooling_protocol':None,'mixing':None,'supplement_addition_time':None} for i,g in result['grams'].items()], 'final_mass_g':None,'homogenization_protocol':None,'sampling_method':None,'replicates':None,'laboratory':None,'analytical_panel':'Full required species-specific nutrient profile, proximate/ME-method inputs, minima/maxima/ratios; LOD/LOQ and uncertainty required','reviewer_name':None,'reviewer_credential':None,'decision':None}

def replan_replacement(pet,old,new,store):
    from .runtime import solve,recipe_digest
    baseline=solve(pet,store)
    if baseline['recipe_status']!='VALIDATED':return {'recipe_status':'NEEDS_REVIEW','substitution_status':'BLOCKED_BY_BASELINE_RECIPE','grams':None}
    if baseline.get('recipe_digest') not in store.meta.get('approved_recipe_hashes',[]):return {'substitution_status':'BLOCKED_BY_BASELINE_RECIPE','grams':None}
    if old==new or old not in baseline['grams']:raise ValueError('Invalid replacement')
    groups=store.rows('substitution_groups');a={r['group_id'] for r in groups if r['ingredient_id']==old};b={r['group_id'] for r in groups if r['ingredient_id']==new}
    if not a&b:raise ValueError('Replacement requires a shared candidate group')
    ids=[i for i in baseline['grams'] if i in store.keyed('ingredients','ingredient_id') and i!=old]+[new]
    result=plan_adult(pet,store,food_ids=ids,required_food_ids=[new])
    result.update(substitution_status='NEEDS_REVIEW',replacement_mode='FULL_FOOD_AND_SUPPLEMENT_REOPTIMIZATION',fixed_supplement_doses=False)
    return result
