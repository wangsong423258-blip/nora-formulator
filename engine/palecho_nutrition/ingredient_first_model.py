"""Profile, individual energy estimates and reviewed nutrient/disease directions."""
from copy import deepcopy
import math
from .freshfood_contract import require
from .quick_meal import normalize_input
from .profile import lifecycle
from .daily_disease_v13 import daily_disease_advice
from .practical import digest
from .ingredient_first_repository import CATEGORIES

def normalize_selection(value,repo):
    if value is None:return {'mode':'USER_SELECTED_SET','ingredient_ids':[],'categories':{}}
    if isinstance(value,list):value={'ingredient_ids':value}
    require(isinstance(value,dict) and set(value)<={'mode','ingredient_ids','categories'},'INGREDIENT_SELECTION_INVALID')
    require(value.get('mode','USER_SELECTED_SET')=='USER_SELECTED_SET','SELECTION_MODE_UNSUPPORTED')
    require('ingredient_ids' in value or 'categories' in value,'SELECTED_INGREDIENT_IDS_REQUIRED')
    groups=value.get('categories',{})
    require(isinstance(groups,dict) and set(groups)<=set(CATEGORIES),'SELECTION_CATEGORY_INVALID')
    for group,ids in groups.items():
        require(isinstance(ids,list) and all(isinstance(i,str) for i in ids),'SELECTION_ARRAY_REQUIRED',group)
        for iid in ids:
            require(iid in repo.records or iid.startswith('TOX_'),'UNKNOWN_INGREDIENT_ID',iid)
            if iid in repo.records:require(repo.records[iid]['category']==group,'SELECTION_CATEGORY_MISMATCH',iid)
    flattened=[i for ids in groups.values() for i in ids]
    ids=value.get('ingredient_ids',flattened)
    require(isinstance(ids,list) and all(isinstance(i,str) for i in ids),'SELECTION_ARRAY_REQUIRED')
    require(len(ids)==len(set(ids)) and len(flattened)==len(set(flattened)),'DUPLICATE_INGREDIENT_SELECTION')
    if 'ingredient_ids' in value and 'categories' in value:require(set(ids)==set(flattened),'SELECTION_INPUT_CONFLICT')
    require(len(ids)<=repo.policy['max_selected_count'],'TOO_MANY_SELECTED_INGREDIENTS')
    require(all(i in repo.records or i in {'TOX_ONION','TOX_GARLIC','TOX_CHOCOLATE','TOX_GRAPE'} for i in ids),'UNKNOWN_INGREDIENT_ID')
    normalized={}
    for iid in sorted(ids):
        cat=repo.records[iid]['category'] if iid in repo.records else 'OPTIONAL_OTHER'
        normalized.setdefault(cat,[]).append(iid)
    return {'mode':'USER_SELECTED_SET','ingredient_ids':sorted(ids),'categories':normalized}

def normalize_profile(profile,selection,store,repo):
    require(isinstance(profile,dict),'PROFILE_OBJECT_REQUIRED')
    from .ingredient_first_input import validate_types
    validate_types(profile)
    incoming=deepcopy(profile)
    for alias,canonical in [('BCS','body_condition'),('bcs','body_condition'),('neuter','neutered'),('current_symptoms','recent_symptoms')]:
        if alias in incoming:
            require(canonical not in incoming or incoming[canonical]==incoming[alias],'PROFILE_ALIAS_CONFLICT',alias)
            incoming[canonical]=incoming.pop(alias)
    embedded=incoming.pop('ingredient_selection',None)
    if embedded is not None and selection is not None:require(normalize_selection(embedded,repo)==normalize_selection(selection,repo),'SELECTION_INPUT_CONFLICT')
    selected=normalize_selection(selection if selection is not None else embedded,repo)
    restrictions=incoming.pop('food_restrictions',[])
    ideal=incoming.pop('ideal_weight_kg',None)
    require(ideal is None or type(ideal) in (float,int) and math.isfinite(ideal) and ideal>0,'IDEAL_WEIGHT_INVALID')
    p,check,warnings=normalize_input(incoming,None,store)
    require(p.get('body_condition') is not None,'BODY_CONDITION_REQUIRED','body_condition')
    require(isinstance(restrictions,list),'ARRAY_REQUIRED','food_restrictions')
    excluded={};tags=set(t for f in repo.records.values() for t in f['allergen_tags'])|set(CATEGORIES)
    for r in restrictions:
        require(isinstance(r,dict) and set(r) in [{'ingredient_id','reason'},{'ingredient','reason'}],'RESTRICTION_OBJECT_INVALID')
        iid=r.get('ingredient_id',r.get('ingredient'))
        require(isinstance(iid,str) and iid in set(repo.records)|tags|{'GRAINS'},'UNKNOWN_INGREDIENT_ID','food_restrictions')
        reason={'CONFIRMED_ALLERGY':'ALLERGY','VET_AVOID':'VET_RESTRICTED'}.get(r['reason'],r['reason'])
        require(reason in {'ALLERGY','INTOLERANCE','VET_RESTRICTED'},'RESTRICTION_REASON_INVALID')
        # A cooking state or source release does not remove a documented
        # allergen. Expand an exact-food allergy to its declared food family;
        # a veterinarian's exact-record restriction remains exact by default.
        family=set(repo.records[iid]['allergen_tags']) if iid in repo.records and reason in {'ALLERGY','INTOLERANCE'} else set()
        for f in repo.records.values():
            if iid==f['ingredient_id'] or iid==f['category'] or iid in f['allergen_tags'] or family&set(f['allergen_tags']) or iid=='GRAINS' and set(f['allergen_tags'])&{'RICE','OAT','MILLET','BARLEY','BUCKWHEAT','QUINOA'}:
                excluded[f['ingredient_id']]={'reason':reason,'input':iid,'allergen_family_expansion':sorted(family)}
    p.update(ingredient_selection=selected,food_restrictions=deepcopy(restrictions),ideal_weight_kg=ideal)
    pet=check['engine_pet'];pet['_ingredient_selection_v19']=selected;pet['_exclusions_v19']=excluded
    advice=daily_disease_advice(pet,store)
    return p,pet,advice,warnings

def model(p,pet,advice,store,repo):
    rules=repo.registry['rules'];policy=repo.policy;sp=pet['species'];weight=pet['weight_kg']
    growth=p.get('life_stage') in {'GROWTH','EARLY_GROWTH','LATE_GROWTH','LATE_GROWTH_SMALL_MEDIUM','LATE_GROWTH_LARGE','LARGE_BREED_GROWTH'}
    try:stage,reference=lifecycle(pet,store)
    except ValueError:stage,reference=None,None
    if stage is None and sp=='DOG' and growth:
        stage='DOG_GROWTH';reference='DOG_GROWTH_EARLY' if pet['age_months_completed']<4 else 'DOG_GROWTH_LATE_SMALL'
    require(stage is not None,'GROWTH_CONTEXT_REQUIRED','expected_adult_weight_kg',
            '还需要确认生长情况。请填写预计成年体重；确实不清楚时可选择“不清楚”。')
    require(reference is not None and 'UNWEANED' not in stage,'UNSUPPORTED_LIFE_STAGE','life_stage',
            '当前生命阶段暂不支持自动鲜食配方，请核对年龄、断奶及生长情况。')
    growth='GROWTH' in stage;months=pet['age_months_completed'];diseases=set(advice['diseases'])
    bcs=pet['bcs'];trend=pet['weight_trend']
    condition='SEVERE_UNDERWEIGHT' if bcs<=2 else 'UNDERWEIGHT' if bcs==3 else 'IDEAL' if bcs<=5 else 'OVERWEIGHT' if bcs<=7 else 'OBESE'
    ideal=p.get('ideal_weight_kg');use_ideal=ideal is not None and bcs>=6 and not growth
    if use_ideal:require(ideal<=weight,'IDEAL_WEIGHT_EXCEEDS_CURRENT_OVERWEIGHT_WEIGHT')
    basis_weight=ideal if use_ideal else weight
    rer_rule=rules['RER']['value'];rer=rer_rule['coefficient']*basis_weight**rer_rule['exponent']
    rule_ids=['RER'];interval=None
    if growth and sp=='DOG':
        adult=pet.get('expected_adult_weight_kg')
        if adult and pet['age_days']<=365.2425:
            require(weight<=adult,'EXPECTED_ADULT_WEIGHT_INVALID')
            r=rules['PUPPY_FEDIAF']['value'];base=(r['intercept']-r['ratio_coefficient']*weight/adult)*weight**r['exponent'];rid='PUPPY_FEDIAF'
        else:
            r=rules['PUPPY_MER']['value'];base=rer*r['early' if months<r['age_boundary_months'] else 'late'];rid='PUPPY_MER'
    elif growth:
        r=rules['KITTEN_FEDIAF']['value'];lo,hi=r['under4' if months<4 else 'under9' if months<9 else 'under12']
        baseline=r['coefficient']*weight**r['exponent'];base=baseline*lo;interval=[baseline*lo,baseline*hi];rid='KITTEN_FEDIAF'
    else:
        neuter='neutered' if pet['neutered'] else 'intact'
        base=rer*rules['ADULT_MER']['value'][sp][neuter];rid='ADULT_MER'
    rule_ids.append(rid)
    activity_factor=1. if growth else policy['activity_modifiers'][pet['_activity_level_v16']]
    body_factor=1. if growth or use_ideal else policy['body_modifiers'][condition]
    if not growth and not use_ideal:
        if 'OBESITY' in diseases and bcs>=6:body_factor=min(body_factor,policy['body_modifiers']['OBESE'])
        if trend=='LOSING' and bcs>=3:body_factor=min(policy['body_factor_max'],body_factor+policy['trend_increment'])
        if trend=='GAINING' and bcs>=6:body_factor-=policy['trend_increment']
    daily=base*activity_factor*body_factor
    rule_ids+=['ENG_ACTIVITY_MODIFIERS','ENG_BODY_MODIFIERS','ENG_TREND_INCREMENT']
    meal_rules=policy['meals']
    count=meal_rules['CAT'] if sp=='CAT' else meal_rules['GROWTH_YOUNG'] if growth and months<4 else meal_rules['GROWTH_OLDER_DOG'] if growth else meal_rules['DOG_GI'] if diseases&{'EPI','CIE_DOG','PLE','PANCREATITIS_DOG'} else meal_rules['DOG_ADULT']
    target=daily/count if p['meal_scope']=='MEAL' else daily
    nutrient_targets={}
    for n in ['protein','fat']:
        rid=f'{reference}:{n}:PER_1000_KCAL_ME:NUTRITIONAL'
        require(rid in rules,'NUTRIENT_TARGET_RULE_MISSING',rid)
        nutrient_targets[n]={'minimum_g_per_1000kcal':rules[rid]['value'],'rule_id':rid,
          'original_basis':'PER_1000_KCAL_ME','runtime_basis':'PER_1000_KCAL_PREDICTED_PET_ME',
          'scope':'FEDIAF_MACRO_REFERENCE_SCREEN_NOT_COMPLETE_NUTRITION'}
        rule_ids.append(rid)
    adjustments=[];soft=[];fat_max=None
    disease_stages={d['disease_id']:d.get('stage') for d in p.get('diseases',[])}
    def add(rid,nutrient,kind,reason):
        rule_ids.append(rid);adjustments.append({'rule_id':rid,'nutrient':nutrient,'rule_type':kind,'reason':reason,'source_ids':rules[rid]['source_ids']})
        if kind in {'SOFT_LIMIT','PREFERRED'} and nutrient:soft.append(nutrient)
    if 'CKD' in diseases:
        if disease_stages.get('CKD') in {'2','3','4'}:add('CKD_PHOSPHORUS','phosphorus','SOFT_LIMIT','Prefer lower phosphorus while preserving protein/energy; no serum-to-food conversion.')
        add('CKD_MONITOR',None,'MONITOR','Renal stage, potassium and hydration need clinical monitoring; this meal is not a renal prescription.')
    if sp=='DOG' and 'PANCREATITIS_DOG' in diseases:
        fat_max=rules['DOG_PANCREATITIS_FAT']['value'];add('DOG_PANCREATITIS_FAT','fat','DISEASE_LIMIT','Canine <20g/1000kcal predicted ME; final-mixture density is checked.')
    if 'HYPERLIPIDEMIA' in diseases:add('HYPERLIPIDEMIA','fat','SOFT_LIMIT','No unsourced diagnosis-only triglyceride dietary threshold.')
    if 'PANCREATITIS_CAT' in diseases:add('CAT_PANCREAS','fat','SOFT_LIMIT','Moderate lower-fat preference only; no canine numerical limit. SOURCE_CONFLICT retained.')
    if 'DIABETES_CAT' in diseases:add('CAT_DIABETES','carbohydrate','PREFERRED','Lower-carbohydrate direction; no automatic removal of starch.')
    if 'DIABETES_DOG' in diseases:add('DOG_DIABETES',None,'MONITOR','Consistent feeding and existing medication timing; no feline carbohydrate target.')
    if diseases&{'CIE_DOG','CIE_CAT','CHRONIC_DIARRHEA','EPI','PLE','FOOD_RESPONSIVE_ENTEROPATHY'}:
        add('GI_INDIVIDUAL',None,'MONITOR','Digestibility/food response unknown; no inferred universal fiber target.')
    if diseases&{'MMVD','HCM','DCM','CHF','HYPERTENSION'}:
        if sp=='CAT':add('CARDIAC_CAT','sodium' if 'CHF' in diseases else None,'SOFT_LIMIT' if 'CHF' in diseases else 'MONITOR','Feline source; adequate intake first, no HCM-only sodium threshold.')
        else:
            mmvd_stage=p.get('clinical_nutrition',{}).get('mmvd_stage') or disease_stages.get('MMVD')
            restricted='CHF' in diseases or mmvd_stage in {'B2','C','D'}
            add('CARDIAC_SODIUM','sodium' if restricted else None,'SOFT_LIMIT' if restricted else 'MONITOR',
                'Stage B2/C/D or CHF: lower sodium preference; A/B1/unknown: monitor without inferred restriction.')
    if sp=='DOG' and 'COPPER_HEPATOPATHY' in diseases:add('COPPER_HEPATOPATHY','copper','SOFT_LIMIT','Confirmed canine copper-associated disease; not blanket organ exclusion.')
    if diseases&{'OSTEOARTHRITIS','JOINT_CHRONIC'}:add('JOINT_SUPPORT',None,'PREFERRED','Consider sourced nutritional support separately; do not auto-add oil.')
    if bcs>=6 and not growth:add('BODY_CONDITION','fat','SOFT_LIMIT','Body-conditioned energy and lower fat preference; not a treatment diet.')
    handled={'CKD','PLN','PANCREATITIS_DOG','PANCREATITIS_CAT','HYPERLIPIDEMIA','DIABETES_CAT','DIABETES_DOG','CIE_DOG','CIE_CAT','CHRONIC_DIARRHEA','EPI','PLE','FOOD_RESPONSIVE_ENTEROPATHY','MMVD','HCM','DCM','CHF','HYPERTENSION','COPPER_HEPATOPATHY','OSTEOARTHRITIS','JOINT_CHRONIC','OBESITY','FOOD_ALLERGY','ADVERSE_FOOD_REACTION'}
    for disease in sorted(diseases-handled):
        adjustments.append({'disease_id':disease,'rule_id':None,'nutrient':None,'rule_type':'INSUFFICIENT_EVIDENCE','reason':'No additional validated numerical Quick Meal rule; preserve clinical plan.','source_ids':[]})
    energy={'daily_kcal':daily,'selected_portion_kcal':target,'energy_target_is_estimate':True,
      'RER_kcal':rer,'baseline_kcal':base,'baseline_rule_id':rule_ids[1],
      'published_interval_kcal':interval,'interval_selection':'LOWER_PUBLISHED_ENDPOINT' if interval else None,
      'weight_basis_kg':basis_weight,'current_weight_kg':weight,'ideal_weight_kg':ideal,
      'ideal_weight_used':use_ideal,'body_condition':bcs,'weight_trend':trend,
      'activity':pet['_activity_level_v16'],'neutered':pet['neutered'] if pet.get('neuter_status_known',True) else None,
      'modifiers':{'activity':activity_factor,'body_condition_and_trend':body_factor,'classification':'ENGINEERING_HEURISTIC'},
      'growth_modifiers_applied':False,'breed_multiplier_applied':False,
      'why_this_energy_target':'Published species/life-stage baseline, then explicit monitored engineering modifiers; ideal weight is never inferred from BCS.',
      'rule_ids':list(dict.fromkeys(rule_ids)),'followup':'Monitor intake, weight, BCS/MCS and clinical response; recalculate whole selected set.'}
    return {'species':sp,'life_stage':stage,'reference_profile':reference,'growth':growth,'weight_kg':weight,
      'body_condition':bcs,'diseases':sorted(diseases),'energy':energy,'target':target,'meal_count':1 if p['meal_scope']=='MEAL' else count,'suggested_meal_count':count,
      'nutrient_targets':nutrient_targets,'fat_max':fat_max,'soft_nutrients':list(dict.fromkeys(soft)),
      'disease_adjustments':adjustments,'policy_hash':digest(repo.registry),'rule_ids':energy['rule_ids']}
