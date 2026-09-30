"""Validate JSON types before aliases, hashing, legacy validation or MILP.

Weight ranges are an operational envelope, not a diagnostic definition of
normal body size. Out-of-envelope animals need an individually reviewed plan.
"""
import math
from .freshfood_contract import require

WEIGHT_RANGE_KG = {'DOG': (0.1, 150.0), 'CAT': (0.1, 30.0)}

def enum(value, allowed, field, nullable=False):
    if value is None and nullable: return
    require(isinstance(value, str), 'INVALID_FIELD_TYPE', field)
    require(value in allowed, 'INVALID_ENUM', field)

def validate_types(p, partial=False):
    require(isinstance(p, dict), 'INVALID_FIELD_TYPE', 'profile')
    enums = {
        'species': {'DOG', 'CAT'}, 'meal_scope': {'DAY','MEAL'},
        'activity_level': {'LOW','NORMAL','HIGH','VERY_HIGH','ACTIVE','MODERATE_LOW_IMPACT','MODERATE_HIGH_IMPACT'},
        'sex': {'MALE','FEMALE','UNKNOWN'},
        'weight_trend': {'STABLE','GAINING','LOSING','UNKNOWN','GAIN','LOSS'},
        'muscle_condition': {'NORMAL','MILD_LOSS','MODERATE_LOSS','SEVERE_LOSS','UNKNOWN'},
        'life_stage': {'GROWTH','ADULT','MATURE','SENIOR','EARLY_GROWTH','LATE_GROWTH','LATE_GROWTH_SMALL_MEDIUM','LATE_GROWTH_LARGE','LARGE_BREED_GROWTH','UNWEANED'},
    }
    for field, allowed in enums.items():
        if field in p: enum(p[field], allowed, field, field=='life_stage')
    for field in ('weight_kg','weight','ideal_weight_kg','expected_adult_weight_kg'):
        if field not in p or p[field] is None and (partial or field=='ideal_weight_kg'): continue
        v=p[field]
        require(type(v) in (int,float), 'INVALID_FIELD_TYPE', field)
        lo,hi=WEIGHT_RANGE_KG.get(p.get('species'), (0.1,150))
        require(math.isfinite(v) and lo <= v <= hi, 'OUT_OF_RANGE', field)
    for field in ('age_years','age_months','body_condition','BCS','bcs'):
        if field not in p or p[field] is None: continue
        v=p[field]
        if field=='body_condition' and isinstance(v,str):
            enum(v, {'VERY_THIN','THIN','IDEAL','NORMAL','OVERWEIGHT','OBESE','SEVERE_UNDERWEIGHT','MILD_UNDERWEIGHT','MILD_OVERWEIGHT'}, field);continue
        require(type(v) is int, 'INVALID_FIELD_TYPE', field)
        lo,hi=(0,40) if field=='age_years' else (0,11) if field=='age_months' else (1,9)
        require(lo <= v <= hi, 'OUT_OF_RANGE', field)
    for field in ('birth_date','as_of_date','breed_id','breed_name','profile_id'):
        if field in p and p[field] is not None: require(isinstance(p[field],str),'INVALID_FIELD_TYPE',field)
    for field in ('neutered','neuter','growth_complete','weaned'):
        if field in p and p[field] is not None: require(type(p[field]) is bool,'INVALID_FIELD_TYPE',field)
    for field in ('recent_symptoms','current_symptoms','disliked_foods'):
        if field in p:
            require(isinstance(p[field],list),'INVALID_FIELD_TYPE',field)
            require(all(isinstance(v,str) for v in p[field]),'INVALID_FIELD_TYPE',field)
    for field in ('diseases','diagnosed_diseases','disease_subtypes','food_restrictions'):
        if field not in p: continue
        require(isinstance(p[field],list),'INVALID_FIELD_TYPE',field)
        for i,r in enumerate(p[field]):
            path=f'{field}[{i}]'
            if isinstance(r,str) and field!='food_restrictions':continue
            require(isinstance(r,dict),'INVALID_FIELD_TYPE',path)
            for k,v in r.items():
                if k in ('disease_id','id','subtype','stage','clinical_status','ingredient_id','ingredient','reason'):
                    require(v is None and k=='stage' or isinstance(v,str),'INVALID_FIELD_TYPE',path+'.'+k)
            if field=='food_restrictions' and 'reason' in r:
                enum(r['reason'],{'ALLERGY','CONFIRMED_ALLERGY','INTOLERANCE','VET_RESTRICTED','VET_AVOID'},path+'.reason')
    c=p.get('clinical_nutrition')
    if c is not None:
        require(isinstance(c,dict),'INVALID_FIELD_TYPE','clinical_nutrition')
        if 'mmvd_stage' in c: enum(c['mmvd_stage'],{'A','B1','B2','C','D'},'clinical_nutrition.mmvd_stage',True)
        if 'risk_factors' in c:
            require(isinstance(c['risk_factors'],list),'INVALID_FIELD_TYPE','clinical_nutrition.risk_factors')
            for v in c['risk_factors']:enum(v,{'MOBILITY_DECLINE','STIFFNESS','OBESITY'},'clinical_nutrition.risk_factors')
        if 'documented_deficiencies' in c:
            require(isinstance(c['documented_deficiencies'],list),'INVALID_FIELD_TYPE','clinical_nutrition.documented_deficiencies')
            for d in c['documented_deficiencies']:
                require(isinstance(d,dict),'INVALID_FIELD_TYPE','clinical_nutrition.documented_deficiencies')
                if 'active_nutrient' in d:enum(d['active_nutrient'],{'TAURINE','COBALAMIN'},'clinical_nutrition.documented_deficiencies.active_nutrient')
