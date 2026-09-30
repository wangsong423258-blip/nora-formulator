"""Version 1.6 input and starting-energy policy, separate from frozen adapters."""
from copy import deepcopy
from .daily_profile_v13 import normalize_daily_profile as legacy_normalize
from .freshfood_contract import require
from .profile import energy_start as legacy_energy

CATEGORIES = {'ANIMAL_PROTEIN': {'MEAT', 'POULTRY', 'FISH'},
              'ENERGY_SOURCE': {'STARCH'}, 'FIBER_SOURCE': {'VEGETABLE'},
              'FAT_SOURCE': {'OIL'}, 'OPTIONAL_EGG': {'EGG'}, 'OPTIONAL_ORGAN': {'ORGAN'}}
ACTIVITIES = {'LOW', 'NORMAL', 'HIGH', 'VERY_HIGH'}
ACTIVITY_ALIASES = {'MODERATE_LOW_IMPACT': 'NORMAL', 'MODERATE_HIGH_IMPACT': 'HIGH', 'ACTIVE': 'HIGH'}


def policy(store):
    data = store.config.get('scientific_model_v16')
    require(isinstance(data, dict) and data.get('version') == '1.6', 'SCIENTIFIC_POLICY_UNAVAILABLE')
    return data


def normalize_selection(value, store):
    if value is None:
        value = {'mode': 'CANDIDATE_POOL', 'categories': {}}
    require(isinstance(value, dict) and set(value) <= {'mode', 'categories'}, 'INGREDIENT_SELECTION_INVALID')
    require(value.get('mode', 'CANDIDATE_POOL') == 'CANDIDATE_POOL', 'SELECTION_MODE_UNSUPPORTED')
    categories = value.get('categories', {})
    require(isinstance(categories, dict) and set(categories) <= set(CATEGORIES), 'SELECTION_CATEGORY_INVALID')
    definitions = store.keyed('ingredients', 'ingredient_id')
    premium = {r['ingredient_id']: r for r in policy(store)['premium_candidates']}
    result = {}
    for cat, ids in categories.items():
        require(isinstance(ids, list) and all(isinstance(i, str) for i in ids), 'SELECTION_ARRAY_REQUIRED', cat)
        require(len(ids) == len(set(ids)), 'DUPLICATE_INGREDIENT_SELECTION', cat)
        for iid in ids:
            require(iid in definitions or iid in premium, 'UNKNOWN_INGREDIENT_ID', iid)
            if iid in premium:
                require(cat == 'ANIMAL_PROTEIN', 'SELECTION_CATEGORY_MISMATCH', iid)
            else:
                require(definitions[iid]['food_category'] in CATEGORIES[cat], 'SELECTION_CATEGORY_MISMATCH', iid)
        result[cat] = sorted(ids)
    # Absent category = unrestricted; explicit [] = no food from this category.
    return {'mode': 'CANDIDATE_POOL', 'categories': result}


def normalize_profile(profile, store):
    require(isinstance(profile, dict), 'PROFILE_OBJECT_REQUIRED')
    incoming = deepcopy(profile)
    selection = normalize_selection(incoming.pop('ingredient_selection', None), store)
    activity = ACTIVITY_ALIASES.get(incoming.get('activity_level'), incoming.get('activity_level'))
    require(activity in ACTIVITIES, 'ACTIVITY_INVALID', 'activity_level')
    species = incoming.get('species')
    legacy_activity = ({'LOW': 'LOW', 'NORMAL': 'MODERATE_LOW_IMPACT', 'HIGH': 'MODERATE_HIGH_IMPACT',
                        'VERY_HIGH': 'HIGH'} if species == 'DOG' else
                       {'LOW': 'LOW', 'NORMAL': 'LOW', 'HIGH': 'ACTIVE', 'VERY_HIGH': 'ACTIVE'})
    incoming['activity_level'] = legacy_activity[activity]
    stage = incoming.get('life_stage')
    if stage == 'LARGE_BREED_GROWTH': incoming['life_stage'] = 'LATE_GROWTH_LARGE'
    if stage == 'LATE_GROWTH':
        adult = incoming.get('expected_adult_weight_kg')
        require(type(adult) in (int, float) and adult > 0, 'MISSING_GROWTH_INFORMATION', 'expected_adult_weight_kg')
        incoming['life_stage'] = 'LATE_GROWTH_LARGE' if adult > 15 else 'LATE_GROWTH_SMALL_MEDIUM'
    normalized, check, warnings = legacy_normalize(incoming, store)
    normalized.update(activity_level=activity, ingredient_selection=selection)
    pet = check['engine_pet']
    pet['_activity_level_v16'] = activity
    pet['_ingredient_selection_v16'] = selection
    return normalized, check, warnings


def energy_start(pet, requirement_profile, store):
    previous = legacy_energy(pet, requirement_profile, store)
    if 'GROWTH' in requirement_profile:
        previous['scientific_energy'] = {'model': 'SPECIES_GROWTH_MODEL',
            'activity_multiplier_applied': False, 'neuter_multiplier_applied': False,
            'reason': '生长模型按年龄和预计成年体型计算，不叠加未经验证的成年活动系数。',
            'nutrient_floor_energy': previous['DER_start_kcal'] or (previous.get('interval_kcal') or [None])[0]}
        return previous
    p = policy(store)['energy_policy']; sp = pet['species']; activity = pet['_activity_level_v16']
    coefficients = p['dog_coefficients' if sp == 'DOG' else 'cat_coefficients']
    coefficient = coefficients[activity]
    reference_coefficient = coefficient
    # Coefficient selection, explicitly a monitored product starting policy.
    # No automatic caloric reduction for a thin or actively losing animal.
    if sp == 'CAT':
        if not pet['neutered'] and pet.get('neuter_status_known', True):
            coefficient += p['cat_intact_increment'][activity]
        if pet['bcs'] <= 3 or pet['weight_trend'] == 'LOSING': coefficient = max(75, coefficient)
    elif pet['neutered'] and pet['bcs'] >= 4 and pet['weight_trend'] != 'LOSING':
        risk = 2 if pet['bcs'] >= 6 and pet['weight_trend'] == 'GAINING' else 1
        coefficient -= p['dog_neuter_increment'][activity] * risk
    exponent = .75 if sp == 'DOG' else .67
    value = coefficient * pet['weight_kg'] ** exponent
    original = previous['DER_start_kcal'] or previous['interval_kcal'][0]
    previous.update(DER_start_kcal=value, interval_kcal=[value, value],
        rule_id=sp+'_ACTIVITY_NEUTER_V16', source_id='PALECHO_SCIENTIFIC_POLICY',
        scientific_energy={'model':'MONITORED_STARTING_COEFFICIENT', 'activity':activity,
            'reference_coefficient':reference_coefficient, 'selected_coefficient':coefficient,
            'exponent':exponent, 'activity_multiplier_applied':False,
            'neuter_multiplier_applied':False, 'source_ids':p['source_ids'],
            'scope':p['scope'], 'nutrient_floor_energy':max(original, value),
            'neuter_coefficient_delta':coefficient-reference_coefficient})
    return previous
