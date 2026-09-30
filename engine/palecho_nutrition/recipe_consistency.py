"""Machine-readable constraints shared by recipe, care and frozen preparation."""
from collections import Counter


def check_recipe(state, result, store):
    policy=state['target']['design_policy'] if state['target'] else {}
    selected={r['ingredient_id'] for r in result['recipe_components']}
    foods=store.keyed('ingredients','ingredient_id');violations=[]
    excluded_categories=set(policy.get('excluded_categories',[]))
    for iid in selected:
        tags=set((foods[iid]['allergen_tags'] or '').split(';'))|{iid,foods[iid]['food_category']}
        if tags&set(state['raw']['pet']['allergies']):violations.append('ALLERGEN:'+iid)
        if foods[iid]['food_category'] in excluded_categories or iid in policy.get('exclude_ids',[]):violations.append('DISEASE_EXCLUSION:'+iid)
    for adaptation in result['disease_adaptations']:
        for note in adaptation.get('foods_to_avoid',[]):
            if not isinstance(note,dict):continue
            forbidden=set(note.get('ingredient_ids',[]))
            forbidden.update(i for i in selected if foods[i]['food_category'] in note.get('food_categories',[]))
            violations += ['CARE_AVOID_CONFLICT:'+i for i in selected&forbidden]
    for row in result.get('nutrient_matrix',[]):
        if row['target_conflict']:violations.append('NUTRIENT_TARGET_CONFLICT:'+row['nutrient_id'])
        if row['additional_amount_needed'] is not None and row['additional_upper_headroom'] is not None and row['additional_amount_needed']>row['additional_upper_headroom']+1e-6:
            violations.append('ADDITIONAL_TARGET_OVER_UPPER:'+row['nutrient_id'])
    return {'status':'FAIL' if violations else 'PASS','violations':sorted(set(violations)),
            'checks':['FOOD_RESTRICTIONS','DISEASE_EXCLUSIONS','STRUCTURED_CARE','ACTIVE_NUTRIENT_TARGETS'],
            'scope':'STRUCTURED_RULES_NOT_ARBITRARY_FREE_TEXT_NLP',
            'constraint_contract':{'excluded_categories':sorted(excluded_categories),
                                   'excluded_ingredient_ids':policy.get('exclude_ids',[]),
                                   'allergen_tags':state['raw']['pet']['allergies']}}


def check_cooking(recipe, plan):
    rows=recipe['recipe_components'];ids=Counter(r['ingredient_id'] for r in rows);issues=[]
    if Counter(r['ingredient_id'] for r in plan['shopping_list'])!=ids:issues.append('SHOPPING_COMPONENT_MISMATCH')
    if Counter(r['ingredient_id'] for r in plan['ingredient_preparation'])!=ids:issues.append('PREPARATION_COMPONENT_MISMATCH')
    cooked={i for s in plan['cooking_steps'] for i in s['ingredients']}
    if cooked!=set(ids):issues.append('COOKING_COMPONENT_MISMATCH')
    mixed=Counter(i for s in plan.get('mixing_steps',[]) for i in s['ingredient_ids'])
    if mixed!=ids:issues.append('MIXING_COMPONENT_MISMATCH')
    amounts={r['ingredient_id']:r['amount_g'] for r in rows}
    for row in plan['shopping_list']:
        if row['ingredient_id'] not in amounts:continue
        amount=amounts[row['ingredient_id']]
        if abs(row['daily_amount']-amount)>1e-6 or abs(row['batch_amount']-amount*plan['batch_days'])>1e-6:issues.append('SHOPPING_AMOUNT_MISMATCH')
    if plan['supplement_recommendations']!=recipe['supplement_recommendations']:issues.append('SUPPLEMENT_RECOMMENDATION_MISMATCH')
    if plan['disease_lifestyle_notes']!=recipe['disease_adaptations']:issues.append('DISEASE_CARE_MISMATCH')
    if 'supplement_steps' in plan:issues.append('UNBOUND_PRODUCT_DOSE')
    feeding=plan['daily_feeding_plan']
    if abs(sum(amounts.values())-feeding['daily_total_food_g'])>1e-6:issues.append('DAILY_MASS_MISMATCH')
    if abs(feeding['food_g_per_meal']*feeding['meals_per_day']-sum(amounts.values()))>.11:issues.append('MEAL_MASS_MISMATCH')
    return {'status':'FAIL' if issues else 'PASS','violations':sorted(set(issues)),
            'checks':['ALL_COMPONENTS','PURCHASE_MASS','PREPARATION','COOKING','MIXING','MEAL_MASS','SUPPLEMENT_TARGETS','DISEASE_CARE','NO_UNBOUND_PRODUCT_DOSE']}


def check_scientific_cooking(recipe, plan):
    """Version 1.6 extension: verify state/method, targets and immutable support."""
    result=check_cooking(recipe,plan)
    issues=list(result['violations'])
    shopping={r['ingredient_id']:r for r in plan['shopping_list']}
    preparation={r['ingredient_id']:r for r in plan['ingredient_preparation']}
    methods={iid:step['method'] for step in plan['cooking_steps'] for iid in step['ingredients']}
    for component in recipe['recipe_components']:
        iid=component['ingredient_id']
        if iid in shopping and shopping[iid]['amount_basis']!=component['weight_basis']:issues.append('SHOPPING_WEIGHT_BASIS:'+iid)
        if iid in preparation and preparation[iid]['weight_basis']!=component['weight_basis']:issues.append('PREPARATION_WEIGHT_BASIS:'+iid)
        if methods.get(iid)!=component['preparation_hint']:issues.append('COOKING_METHOD:'+iid)
    for key in ['nutrient_matrix','energy_audit','nutrition_design_target','supplement_decision','ingredient_selection_audit']:
        if plan.get(key)!=recipe.get(key):issues.append(key.upper()+'_MISMATCH')
    for key in ['daily_total_food_g','meals_per_day','food_g_per_meal']:
        if plan['daily_feeding_plan'][key]!=recipe['daily_feeding_plan'][key]:issues.append('FEEDING_PLAN:'+key)
    return {'status':'FAIL' if issues else 'PASS','violations':sorted(set(issues)),
        'checks':result['checks']+['WEIGHT_BASIS','FOOD_STATE_METHOD','SCIENTIFIC_TARGET_SNAPSHOT','SELECTION_SNAPSHOT','SUPPLEMENT_SAFETY_SNAPSHOT','DAILY_MEALS']}
