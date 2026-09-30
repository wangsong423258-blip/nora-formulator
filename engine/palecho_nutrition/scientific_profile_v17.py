"""Four-purpose input: documented findings are distinct from recipe deficits."""
from copy import deepcopy
from .scientific_profile import normalize_profile as previous, normalize_selection as old_selection
from .freshfood_contract import require

PUBLIC_CATEGORIES={'ANIMAL_PROTEIN','ENERGY_SOURCE','FIBER_SOURCE'}
CATEGORY_MAP={'OPTIONAL_EGG':'SECONDARY_ANIMAL_FOOD','OPTIONAL_ORGAN':'ORGAN','FAT_SOURCE':'OIL'}

def normalize_selection(value,store):
    value={} if value is None else deepcopy(value)
    require(isinstance(value,dict),'INGREDIENT_SELECTION_INVALID')
    groups=value.get('categories',{})
    require(isinstance(groups,dict) and set(groups)<=PUBLIC_CATEGORIES,'SELECTION_CATEGORY_INVALID')
    result=old_selection(value,store)
    defs=store.keyed('ingredients','ingredient_id')
    require(all(i in defs for ids in groups.values() for i in ids),'INGREDIENT_NOT_IN_COMMON_CATALOG')
    return result

def clinical_context(value):
    value={} if value is None else deepcopy(value)
    require(isinstance(value,dict) and set(value)<={'documented_deficiencies','risk_factors','mmvd_stage','cognitive_dysfunction_report'},'CLINICAL_CONTEXT_INVALID')
    deficiencies=value.get('documented_deficiencies',[])
    require(isinstance(deficiencies,list),'DEFICIENCY_LIST_REQUIRED')
    seen=set()
    for d in deficiencies:
        require(isinstance(d,dict) and set(d)=={'active_nutrient','clinician_confirmed','report_reference'},'DEFICIENCY_EVIDENCE_REQUIRED')
        require(d['active_nutrient'] in {'TAURINE','COBALAMIN'} and d['active_nutrient'] not in seen,'DEFICIENCY_NUTRIENT_INVALID')
        require(d['clinician_confirmed'] is True and isinstance(d['report_reference'],str) and 0<len(d['report_reference'].strip())<=300,'DEFICIENCY_EVIDENCE_REQUIRED')
        seen.add(d['active_nutrient'])
    risk=value.get('risk_factors',[])
    require(isinstance(risk,list) and all(v in {'MOBILITY_DECLINE','STIFFNESS','OBESITY'} for v in risk),'RISK_FACTOR_INVALID')
    require(value.get('mmvd_stage') in {None,'A','B1','B2','C','D'},'MMVD_STAGE_INVALID')
    report=value.get('cognitive_dysfunction_report')
    require(report is None or isinstance(report,str) and 0<len(report.strip())<=300,'COGNITIVE_REPORT_INVALID')
    return {'documented_deficiencies':sorted(deficiencies,key=lambda d:d['active_nutrient']), 'risk_factors':sorted(set(risk)), 'mmvd_stage':value.get('mmvd_stage'),'cognitive_dysfunction_report':report}

def normalize_profile(profile,store):
    incoming=deepcopy(profile)
    require(isinstance(incoming,dict),'PROFILE_OBJECT_REQUIRED')
    context=clinical_context(incoming.pop('clinical_nutrition',None))
    incoming['ingredient_selection']=normalize_selection(incoming.get('ingredient_selection'),store)
    normalized,check,warnings=previous(incoming,store)
    normalized['clinical_nutrition']=context
    check['engine_pet']['_clinical_nutrition_v17']=context
    return normalized,check,warnings
