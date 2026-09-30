"""Normalize qualitative intake without pretending it is an ingredient vector."""
from copy import deepcopy
from .freshfood_contract import require, numeric, warning, PetNutritionProfileValidator
from .user_supplements import validate_spec

GOALS={'COMPLETE_DIET':'FULL_DAILY_DIET','PARTIAL_WITH_MAIN_DIET':'PARTIAL_DIET','OCCASIONAL_MEAL':'OCCASIONAL_MEAL'}
FREQUENCIES={'OCCASIONAL','WEEKLY','DAILY_SMALL','DAILY_MODERATE','DAILY_LARGE'}
PORTIONS={'TASTE','SMALL','MEDIUM','LARGE','UNKNOWN'}
BUCKETS=('extra_foods','snacks','freeze_dried','human_foods','commercial_extras')

def normalize_context(raw,store):
    from .recipe_design_schema import validate_design_model
    validate_design_model('FreshFoodDesignContext',raw)
    require(isinstance(raw,dict),'DESIGN_CONTEXT_REQUIRED','context')
    require(set(raw)<= {'pet_profile','feeding_goal','current_diet_context','current_intake','food_preferences','food_restrictions','available_supplements'},'UNKNOWN_DESIGN_FIELD','context')
    c=deepcopy(raw);goal=c.get('feeding_goal');require(isinstance(goal,str) and goal in GOALS,'FEEDING_GOAL_INVALID','feeding_goal')
    p=c.get('pet_profile');require(isinstance(p,dict),'PROFILE_OBJECT_REQUIRED','pet_profile')
    if 'feeding_goal' in p:require(p['feeding_goal']==goal,'FEEDING_GOAL_CONFLICT','pet_profile.feeding_goal')
    # Old dietary fields belong to the explicit 1.0 adapter, not the 1.1 pet.
    require(not {'extra_foods','current_diet_type'} & set(p),'DIET_FIELDS_BELONG_IN_CONTEXT','pet_profile')
    prefs=c.get('food_preferences',{});require(isinstance(prefs,dict) and set(prefs)<= {'disliked_foods','preferred_ingredient_ids'},'FOOD_PREFERENCES_INVALID')
    require(isinstance(prefs.get('disliked_foods',[]),list),'FOOD_PREFERENCES_INVALID')
    p['disliked_foods']=list(dict.fromkeys(p.get('disliked_foods',[])+prefs.get('disliked_foods',[])))
    restrictions=c.get('food_restrictions',[]);require(isinstance(restrictions,list),'RESTRICTIONS_ARRAY_REQUIRED')
    p['food_restrictions']=p.get('food_restrictions',[])+restrictions
    p['feeding_goal']=GOALS[goal]
    diet=c.get('current_diet_context',{})
    require(isinstance(diet,dict),'CURRENT_DIET_CONTEXT_INVALID')
    require(set(diet)<=set(BUCKETS)|{'main_diet','current_supplements'},'UNKNOWN_CURRENT_DIET_FIELD')
    intake=c.get('current_intake')
    if intake is not None:
        require(not diet,'DUPLICATE_CURRENT_INTAKE_CONTEXT')
        require(isinstance(intake,dict) and set(intake)<=set(BUCKETS)|{'main_diet','supplements'},'CURRENT_INTAKE_INVALID')
        diet={('current_supplements' if k=='supplements' else k):v for k,v in intake.items()}
    diet=deepcopy(diet);main=diet.setdefault('main_diet',{'type':'UNKNOWN','is_complete':None})
    require(isinstance(main,dict) and set(main)<= {'intake_class','type','is_complete','display_name','amount_g','energy_kcal_per_day','energy_kcal_per_100g'},'MAIN_DIET_INVALID')
    require(main.get('intake_class','CURRENT_MAIN_DIET')=='CURRENT_MAIN_DIET','INTAKE_CLASS_CONFLICT','main_diet')
    main['intake_class']='CURRENT_MAIN_DIET'
    require(main.get('type','UNKNOWN') in {'DRY_FOOD','WET_FOOD','COMPLETE_COMMERCIAL','HOMEMADE','MIXED','UNKNOWN'},'MAIN_DIET_TYPE_INVALID')
    require(main.get('is_complete') is None or type(main['is_complete']) is bool,'MAIN_DIET_COMPLETENESS_INVALID')
    for k in ('amount_g','energy_kcal_per_day','energy_kcal_per_100g'):
        if k in main:require(numeric(main[k]) and main[k]>=0,'MAIN_DIET_AMOUNT_INVALID',k)
    p['current_diet_type']='COMPLETE_COMMERCIAL' if main.get('is_complete') is True else 'UNKNOWN'
    check=PetNutritionProfileValidator(store).validate(p)
    if check['status']=='INVALID':
        from .freshfood_contract import ContractError
        d=check['errors'][0];raise ContractError(d['code'],d['field'],d['message'])
    warnings=[w for w in check['warnings'] if w['code']!='BODY_CONDITION_REQUIRED_FOR_RECIPE'];defs=store.keyed('ingredients','ingredient_id')
    preferred=prefs.get('preferred_ingredient_ids',[])
    require(isinstance(preferred,list) and all(isinstance(i,str) and i in defs for i in preferred),'UNKNOWN_PREFERRED_INGREDIENT')
    for bucket in BUCKETS:
        items=diet.setdefault(bucket,[]);require(isinstance(items,list),'INTAKE_ARRAY_REQUIRED',bucket)
        for item in items:
            require(isinstance(item,dict) and set(item)<= {'intake_class','type','subtype','display_name','frequency','portion_level','food_pattern','amount_g','energy_kcal','energy_kcal_per_100g','ingredient_id'},'EXTRA_INTAKE_INVALID',bucket)
            expected='COMMERCIAL_EXTRA' if bucket in {'snacks','freeze_dried','commercial_extras'} else 'CURRENT_EXTRA_FOOD'
            require(item.get('intake_class',expected)==expected,'INTAKE_CLASS_CONFLICT',bucket)
            item['intake_class']=expected
            item.setdefault('frequency','OCCASIONAL');item.setdefault('portion_level','UNKNOWN')
            require(isinstance(item['frequency'],str) and item['frequency'] in FREQUENCIES,'FREQUENCY_INVALID',bucket)
            require(isinstance(item['portion_level'],str) and item['portion_level'] in PORTIONS,'PORTION_LEVEL_INVALID',bucket)
            for k in ('amount_g','energy_kcal','energy_kcal_per_100g'):
                if k in item:require(numeric(item[k]) and item[k]>=0,'INTAKE_AMOUNT_INVALID',bucket+'.'+k)
            if 'ingredient_id' in item:require(isinstance(item['ingredient_id'],str) and item['ingredient_id'] in defs,'UNKNOWN_INGREDIENT_ID',bucket)
            for k in ('type','subtype','display_name','food_pattern'):
                if k in item:require(isinstance(item[k],str),'INTAKE_TEXT_REQUIRED',bucket+'.'+k)
    current=diet.setdefault('current_supplements',[]);require(isinstance(current,list),'SUPPLEMENTS_ARRAY_REQUIRED')
    available=c.get('available_supplements',[]);require(isinstance(available,list),'SUPPLEMENTS_ARRAY_REQUIRED')
    ids=set();types=set();specs=[]
    for item in current:
        require(isinstance(item,dict) and set(item)<= {'intake_class','spec','supplement_type','daily_amount','adjustment_allowed','display_name','frequency'},'CURRENT_SUPPLEMENT_INVALID')
        require(item.get('intake_class','CURRENT_SUPPLEMENT')=='CURRENT_SUPPLEMENT','INTAKE_CLASS_CONFLICT')
        item['intake_class']='CURRENT_SUPPLEMENT'
        require(type(item.get('adjustment_allowed',False)) is bool,'SUPPLEMENT_ADJUSTMENT_INVALID')
        if 'daily_amount' in item:require(numeric(item['daily_amount']) and item['daily_amount']>=0,'CURRENT_SUPPLEMENT_DOSE_INVALID')
        require(item.get('frequency','DAILY_SMALL') in FREQUENCIES,'FREQUENCY_INVALID')
        spec=item.get('spec')
        if spec is None:
            require(item.get('supplement_type') in {'TAURINE','CALCIUM','OMEGA3_FISH_OIL','DOG_VITAMIN_MINERAL','CAT_VITAMIN_MINERAL','OTHER'},'SUPPLEMENT_TYPE_INVALID')
            warnings.append(warning('CURRENT_SUPPLEMENT_LIMITED_CONTEXT','当前补剂缺少标签，保留上下文并避免新增同类；不推测成分或剂量。','current_supplements'))
            continue
        require(isinstance(spec,dict),'INVALID_PRODUCT_SPEC')
        require(item.get('supplement_type',spec.get('supplement_type'))==spec.get('supplement_type'),'SUPPLEMENT_TYPE_CONFLICT')
        item['supplement_type']=spec.get('supplement_type');specs.append(spec)
    current_types={i['supplement_type'] for i in current}
    for spec in available:
        require(isinstance(spec,dict),'INVALID_PRODUCT_SPEC')
        if spec.get('supplement_type') in current_types:
            warnings.append(warning('CURRENT_SUPPLEMENT_REUSED','已有同类补剂优先参与重算，不新增第二份。','available_supplements'))
        else:specs.append(spec)
    for spec in specs:
        normalized=validate_spec(spec,store,check['normalized']['species'])
        require(normalized['status']!='INVALID','INVALID_PRODUCT_SPEC','supplements',','.join(normalized['errors']))
        require(spec['id'] not in ids and spec['supplement_type'] not in types,'DUPLICATE_SUPPLEMENT_TYPE_OR_ID')
        ids.add(spec['id']);types.add(spec['supplement_type'])
    for typ in current_types:
        require(sum(i['supplement_type']==typ for i in current)<=1,'DUPLICATE_CURRENT_SUPPLEMENT_TYPE')
    normalized_pet=deepcopy(check['normalized'])
    for key in ('extra_foods','current_diet_type','feeding_goal'):normalized_pet.pop(key,None)
    c={'pet_profile':normalized_pet,'feeding_goal':goal,'current_diet_context':diet,'food_preferences':prefs,'available_supplements':deepcopy(available)}
    return c,check,specs,warnings


def estimate_current_intake(diet,daily_energy,store):
    """Internal planning allowance, never a nutrient deficiency diagnosis.

    Qualitative figures are explicit conservative product allowances, not measured
    intake. The portion is reserved on feeding days (weekly is NOT divided by 7).
    """
    total=0.;unknown=False;details=[]
    for bucket in BUCKETS:
        for item in diet[bucket]:
            kcal=item.get('energy_kcal');method='USER_REPORTED_ENERGY'
            if kcal is None and 'amount_g' in item:
                density=item.get('energy_kcal_per_100g')
                if density is None and item.get('ingredient_id'):
                    density=next((r['value'] for r in store.rows('ingredient_nutrients') if r['ingredient_id']==item['ingredient_id'] and r['nutrient_id']=='energy_human'),None)
                if density is not None:kcal=item['amount_g']*density/100;method='REPORTED_MASS_REFERENCE_ENERGY'
            if kcal is None:
                unknown=True;method='QUALITATIVE_FEEDING_DAY_ALLOWANCE_NOT_MEASURED'
                fraction=max({'OCCASIONAL':.02,'WEEKLY':.025,'DAILY_SMALL':.03,'DAILY_MODERATE':.06,'DAILY_LARGE':.1}[item['frequency']],{'TASTE':.01,'SMALL':.03,'MEDIUM':.06,'LARGE':.1,'UNKNOWN':.03}[item['portion_level']])
                kcal=daily_energy*fraction
            total+=kcal;details.append({'intake_class':item['intake_class'],'reserved_energy_kcal':kcal,'method':method})
    return {'extra_energy_allowance_kcal':total,'limited_context':unknown,'items':details}
