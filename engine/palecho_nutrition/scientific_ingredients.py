"""Household candidate metadata and evidence-gated category selections."""
from copy import deepcopy
from .scientific_profile import CATEGORIES, policy
from .practical_sources import source_candidates, food_vector


def category(food):
    return next((name for name, kinds in CATEGORIES.items() if food['food_category'] in kinds), None)


def catalog(store):
    config = policy(store)
    records = {}
    for row in store.rows('ingredient_nutrients'):
        records.setdefault(row['ingredient_id'], {})[row['nutrient_id']] = row
    units={r['nutrient_id']:r['canonical_unit'] for r in store.rows('nutrients')}
    output = []
    for food in store.rows('ingredients'):
        if food['toxicity_flag'] or food['raw_or_cooked'] == 'RAW': continue
        values, _, provenance = food_vector(food, records.get(food['ingredient_id'], {}), 'CAT')
        kind = food['food_category']; fish = kind == 'FISH'
        output.append({'ingredient_id':food['ingredient_id'], 'display_name':food['name_zh'],
            'category':category(food), 'food_identity':config['fish_identities'].get(food['ingredient_id'], food['name_en']),
            'china_availability':food['china_availability'], 'cost_level':food['cost_level'],
            'preparation_difficulty':'MEDIUM' if kind in {'MEAT','POULTRY','FISH','ORGAN'} else 'LOW',
            'preparation_difficulty_basis':'HOUSEHOLD_PROCESS_ESTIMATE',
            'species_allowed':[s for s in ['DOG','CAT'] if food[s.lower()+'_allowed']],
            'life_stage_allowed':food['life_stage_allowed'], 'disease_constraints':food['contraindications'],
            'cooking_state':food['food_state'], 'weight_basis':food['weight_basis'],
            'source_id':food['source_id'], 'nutrient_density':{
                'basis':'PER_100G_AS_FED', 'units':units, 'values':{n:values.get(n) for n in ['energy_human','protein','fat','epa','dha','epa_dha','sodium','iodine','vitamin_d','calcium','phosphorus','copper','vitamin_a']},
                'source_records':{n:provenance.get(n) for n in ['epa','dha','iodine','vitamin_d']}},
            'max_ratio':({'basis':'FOOD_MASS','value':.05} if kind == 'ORGAN' else
                         {'basis':'DAILY_REFERENCE_ENERGY','value':{'FISH':.15,'OIL':.1,'EGG':.25}[kind]} if kind in {'FISH','OIL','EGG'} else None),
            'max_ratio_basis':'HOUSEHOLD_ENGINEERING_LIMIT_NOT_TOXICOLOGICAL_UL',
            'contaminant_risk':deepcopy(config['fish_contaminant_policy']) if fish else None,
            'classification':'IDENTIFIED_FISH' if fish else 'COMMON_HOUSEHOLD_INGREDIENT',
            'default_priority':False if fish else True})
    return output + deepcopy(config['premium_candidates'])


def candidates(pet, stage, store, target, excluded):
    foods, rejected = source_candidates(pet, stage, store, target, excluded, include_supplements=False)
    categories = pet['_ingredient_selection_v16']['categories']
    retained = []
    for food in foods:
        identity=policy(store)['fish_identities'].get(food['id'])
        if food['category']=='FISH' and (not identity or identity in policy(store)['fish_contaminant_policy']['excluded_identities']):
            rejected.append({'id':food['id'],'reasons':['FISH_IDENTITY_OR_CONTAMINANT_HAZARD']})
            continue
        group = category(food['definition'])
        if group in categories and food['id'] not in categories[group]:
            rejected.append({'id':food['id'], 'reasons':['OUTSIDE_USER_CATEGORY_POOL']})
        else: retained.append(food)
    for row in policy(store)['premium_candidates']:
        if any(row['ingredient_id'] in ids for ids in categories.values()):
            rejected.append({'id':row['ingredient_id'], 'reasons':row['missing_requirements']})
    return retained, rejected


def selection_audit(state, result, store):
    request = state['profile']['ingredient_selection']
    chosen = {r['ingredient_id']:r['amount_g'] for r in result['recipe_components']}
    definitions = store.keyed('ingredients','ingredient_id')
    violations = [iid for iid in chosen if category(definitions[iid]) in request['categories']
                  and iid not in request['categories'][category(definitions[iid])]]
    eligible = {r['id'] for r in state['eligible_foods']}
    pool = {i for ids in request['categories'].values() for i in ids}
    single = len(request['categories'].get('ANIMAL_PROTEIN', [])) == 1
    return {'request':deepcopy(request), 'status':'FAIL' if violations else 'PASS',
        'selected_grams':chosen, 'unselected_candidates':sorted(pool-set(chosen)),
        'unavailable_candidates':sorted(pool-eligible), 'violations':violations,
        'whole_recipe_recalculated':True, 'allocation_method':'WHOLE_RECIPE_INTEGER_OPTIMIZATION',
        'equal_split_used':False, 'all_selected_are_required':False,
        'single_protein_choice':single,
        'suggestions':(['可增加一种不同脂肪或微量营养组成的可接受蛋白候选，再重算比较；不自动加入未选择的肉类。']
                       if single and result.get('whole_recipe_nutrition_check',{}).get('unresolved_nutrients') else [])}
