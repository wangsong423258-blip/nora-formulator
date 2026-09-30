"""Deterministic input, triage, lifecycle, energy and disease assessment."""
from datetime import date
import json, math
from .units import number, UnitError
from .store import matches

class InputError(ValueError):pass

def _check(ok,msg):
    if not ok:raise InputError(msg)

def validate_pet(p,store):
    _check(type(p) is dict,'Pet input must be a JSON object')
    p=dict(p)
    required=['species','breed','sex','neutered','weight_kg','bcs','muscle_condition','activity','weight_trend','diseases','recent_abnormalities','current_diet','allergies','dislikes','purpose','weaned']
    _check(all(k in p for k in required),'Missing fields: '+','.join(k for k in required if k not in p))
    _check(p['species'] in ['DOG','CAT'],'species must be DOG or CAT')
    _check(p['sex'] in ['FEMALE','MALE','UNKNOWN'],'Invalid sex')
    _check(type(p['neutered']) is bool and type(p['weaned']) is bool,'neutered/weaned must be booleans')
    _check(isinstance(p['breed'],str) and bool(p['breed']),'breed required; MIXED/UNKNOWN allowed')
    breed=p['breed'].strip()
    p['breed']=store.config.get('breed_aliases',{}).get(breed.lower(),breed.upper().replace(' ','_'))
    p['weight_kg']=number(p['weight_kg'],positive=True)
    _check(type(p['bcs']) is int and 1<=p['bcs']<=9,'BCS requires an integer on the 1–9 scale')
    _check(p['muscle_condition'] in ['NORMAL','MILD_LOSS','MODERATE_LOSS','SEVERE_LOSS','UNKNOWN'],'Unknown MCS')
    _check(p['weight_trend'] in ['STABLE','GAINING','LOSING','UNKNOWN'],'Unknown weight trend')
    _check(isinstance(p['current_diet'],str) and bool(p['current_diet']),'Current diet required')
    for field in ['allergies','dislikes','recent_abnormalities']:
        _check(type(p[field]) is list and all(type(v) is str for v in p[field]),field+' must be an array of codes')
        _check(len(set(p[field]))==len(p[field]),'Duplicate '+field)
    has_age='age_days' in p;has_dob='birth_date' in p
    _check(has_age!=has_dob,'Provide exactly one of age_days or birth_date + as_of_date')
    from .life_stage_resolver import LifeStageResolver
    try:
        age = (LifeStageResolver.age(birth_date=p['birth_date'],as_of_date=p.get('as_of_date')) if has_dob
               else p.get('_calendar_age') or LifeStageResolver.age(days=p['age_days']))
    except ValueError as exc: raise InputError(str(exc)) from exc
    p.update({k:age[k] for k in ('age_days','age_years_completed','age_months_completed')})
    _check(p['activity'] in (['LOW','MODERATE_LOW_IMPACT','MODERATE_HIGH_IMPACT','HIGH'] if p['species']=='DOG' else ['LOW','ACTIVE']),'Activity code not supported for species')
    if 'expected_adult_weight_kg' in p:number(p['expected_adult_weight_kg'],positive=True)
    if 'growth_complete' in p:_check(type(p['growth_complete']) is bool,'growth_complete must be boolean')
    if 'energy_target_kcal' in p:number(p['energy_target_kcal'],positive=True)
    _check(p.get('reproductive_status','NONE') in ['NONE','PREGNANCY','LACTATION'],'Invalid reproductive status')
    foods=store.keyed('ingredients','ingredient_id');tags=set()
    for f in foods.values():tags.update((f['allergen_tags'] or '').split(';'));tags.add(f['food_category'])
    known=set(foods)|tags
    for field in ['allergies','dislikes']:_check(all(x in known and bool(x) for x in p[field]),'Unknown '+field+' code; cannot silently ignore')
    if 'available_ingredients' in p:
        _check(type(p['available_ingredients']) is list and all(x in foods for x in p['available_ingredients']),'Unknown available ingredient')
    if 'budget_cny_per_day' in p:number(p['budget_cny_per_day'],positive=True)
    _check(type(p['diseases']) is list,'diseases must be an array')
    catalog=store.keyed('diseases','disease_id');seen=set()
    for d in p['diseases']:
        _check(type(d) is dict and d.get('id') in catalog,'Unknown disease: subtype/diagnosis must be resolved')
        _check(set(d)<= {'id','subtype','stage','clinical'},'Unknown disease-level fields; clinical measurements belong inside clinical')
        _check(d['id'] not in seen,'Duplicate disease');seen.add(d['id'])
        _check(catalog[d['id']]['species'] in ['BOTH',p['species']],'Disease belongs to another species')
        _check(type(d.get('clinical',{})) is dict,'clinical data must be a JSON object')
        for key,definition in json.loads(catalog[d['id']]['clinical_units_json']).items():
            value=d.get('clinical',{}).get(key)
            if value is None:continue
            _check(type(value) is dict and set(['value','unit','basis'])<=set(value),'Clinical measurement needs value/unit/basis: '+key)
            _check(value['unit']==definition['unit'] and value['basis']==definition['basis'],'Ambiguous clinical measurement units/basis: '+key)
            number(value['value'],nonnegative=True)
    allowed=set(store.config['red_flags'])|set(store.config['recognized_nonurgent_signs'])
    _check(set(p['recent_abnormalities'])<=allowed,'Unrecognized abnormality requires clinical clarification')
    return p

def lifecycle(p,store):
    from .life_stage_resolver import LifeStageResolver
    return LifeStageResolver.stage(p,store)


def energy_start(p,profile,store):
    rules=store.keyed('energy_rules','energy_rule_id');w=p['weight_kg']
    rer=rules['RER']['coefficient']*w**rules['RER']['exponent']
    if profile.startswith('DOG_GROWTH'):rid='DOG_GROWTH'
    elif profile=='CAT_GROWTH':rid='CAT_KITTEN_U4' if p['age_months_completed']<4 else 'CAT_KITTEN_4_9' if p['age_months_completed']<9 else 'CAT_KITTEN_9_12'
    elif p['species']=='DOG':rid='DOG_'+p['activity']
    else:rid='CAT_INDOOR_NEUTERED' if p['neutered'] or p['activity']=='LOW' else 'CAT_ACTIVE'
    r=rules[rid];model=r['model'];lo=hi=None
    if model=='POWER':lo=hi=r['coefficient']*w**r['exponent']
    elif model=='POWER_RANGE':lo=r['lower']*w**r['exponent'];hi=r['upper']*w**r['exponent']
    elif model=='KITTEN_MER_RANGE':
        base=r['coefficient']*w**r['exponent'];lo=base*r['lower'];hi=base*r['upper']
    elif model=='PUPPY_FEDIAF':
        pars=json.loads(r['parameters_json'])
        _check('expected_adult_weight_kg' in p,'Expected adult weight required for puppy energy')
        if p['age_days']>pars['age_max_years']*365.2425:
            return {'RER_kcal':rer,'DER_start_kcal':None,'interval_kcal':None,'rule_id':rid,'source_id':r['source_id'],'status':'OUTSIDE_MODEL_DOMAIN'}
        ratio=w/p['expected_adult_weight_kg']
        _check(0<ratio<=1,'Growing dog current weight exceeds expected adult weight; reassess')
        lo=hi=(pars['intercept']-pars['ratio_coefficient']*ratio)*w**r['exponent']
    chosen=lo if lo==hi else None
    if 'energy_target_kcal' in p:
        # A value alone is not permission to dilute the nutrient intake of a low-energy animal.
        chosen=p['energy_target_kcal'] if lo<=p['energy_target_kcal']<=hi else None
    return {'RER_kcal':rer,'DER_start_kcal':chosen,'interval_kcal':[lo,hi],'rule_id':rid,'source_id':r['source_id'],
            'status':'STARTING_ESTIMATE' if chosen else 'TARGET_SELECTION_REQUIRED','followup':'记录体重、BCS、MCS与实际进食量；调整总量后重新核验每日必需营养，不作机械同比缩放。'}

def assess(p,store):
    try:p=validate_pet(p,store)
    except (InputError,UnitError,ValueError,TypeError) as e:return {'recipe_status':'INVALID_INPUT','reasons':[str(e)]}
    base={'recipe_status':None,'reasons':[],'pet':p,'source_ids':[]}
    flags=sorted(set(p['recent_abnormalities'])&set(store.config['red_flags']))
    if flags:
        base.update(recipe_status='AUTO_RECIPE_BLOCKED',reasons=flags,action='及时就医；停止自动配方。');return base
    if p['purpose'] not in store.config['supported_purposes']:
        base.update(recipe_status='UNSUPPORTED',reasons=['混合喂养/零食需要现有总日粮的完整营养向量；本版不单独验证鲜食部分。']);return base
    try:stage,profile=lifecycle(p,store)
    except (InputError,UnitError) as e:
        base.update(recipe_status='INVALID_INPUT',reasons=[str(e)]);return base
    base.update(life_stage=stage,profile_id=profile)
    if not store.keyed('life_stages','stage_id')[stage]['supported']:
        base.update(recipe_status='UNSUPPORTED',reasons=[stage+' not supported in V1']);return base
    base['nutrition_categories']=sorted({r['display_category'] for r in store.rows('nutrients')})
    base['lifestyle']=[];base['strategies']=[];base['disease_constraints']=[]
    catalog=store.keyed('diseases','disease_id');ids={d['id'] for d in p['diseases']}
    for d in p['diseases']:
        definition=catalog[d['id']];ctx={**d.get('clinical',{}),**{k:v for k,v in d.items() if k!='clinical'}}
        for key in json.loads(definition['clinical_units_json']):
            if key in ctx and ctx[key] is not None:ctx[key]=ctx[key]['value']
        missing=[]
        for field in ['subtype','stage']:
            if definition['requires_'+field] and not ctx.get(field):missing.append(field)
        if definition['requires_clinical_data']:
            missing.extend(k for k in definition['clinical_fields'].split(';') if k and (k not in ctx or ctx[k] is None))
        if missing:base['reasons'].append({'disease':d['id'],'missing_clinical_data':sorted(set(missing))})
        # Historical triage routing is retained for clinical audits; it never permits
        # disease recipe production. solve/audit_recipe enforce the universal freeze.
        if not definition.get('triage_only_allowed',False):base['reasons'].append({'disease':d['id'],'policy':'PROFESSIONAL_PLAN_REQUIRED'})
        if not matches(json.loads(definition['auto_condition_json']),ctx):base['reasons'].append({'disease':d['id'],'policy':'AUTO_CONDITION_NOT_MET'})
        if ctx.get('clinical_status') in ['ACUTE','UNSTABLE'] or ctx.get('subtype')=='ACUTE' or ctx.get('obstruction_excluded') is False:
            base.update(recipe_status='AUTO_RECIPE_BLOCKED');base['reasons'].append('Acute/unstable or obstruction not excluded')
        base['lifestyle'].extend(r for r in store.rows('disease_lifestyle') if r['disease_id']==d['id'])
        for r in store.rows('disease_rules'):
            if r['disease_id']!=d['id'] or r['species'] not in [p['species'],'BOTH']:continue
            if r['action']=='STRATEGY' and matches(json.loads(r['condition_json']),ctx):base['strategies'].append(r)
            elif matches(json.loads(r['condition_json']),ctx):base['disease_constraints'].append(r)
        base['source_ids'].append(definition['source_id'])
    base['conflicts']=[r for r in store.rows('disease_conflicts') if r['kind']=='DISEASE_PAIR' and r['disease_A'] in ids and r['disease_B'] in ids]
    for c in base['conflicts']:
        if c['chosen_rule']=='REQUIRES_PROFESSIONAL_REVIEW':base['reasons'].append({'conflict_id':c['conflict_id'],'reason':c['difference']})
    if base['recipe_status']=='AUTO_RECIPE_BLOCKED':return base
    if base['reasons']:base['recipe_status']='REQUIRES_PROFESSIONAL_REVIEW'
    try:base['energy']=energy_start(p,profile,store)
    except (InputError,UnitError) as e:
        base.update(recipe_status='INVALID_INPUT');base['reasons'].append(str(e));return base
    # Risk findings affect the decision, not an invented age/neuter multiplier.
    base['reassessment_needed']=p['bcs'] not in [4,5] or p['muscle_condition']!='NORMAL' or p['weight_trend']!='STABLE' or bool(p['recent_abnormalities'])
    return base
