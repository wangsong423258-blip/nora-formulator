"""Pet-only input adapter for API 1.3; older contracts remain unchanged.

The legacy biological validator is reused behind this boundary. Its diet and
purpose placeholders are internal adapter values, never daily design inputs.
"""
from copy import deepcopy
from datetime import date

from .freshfood_contract import (
    PROFILE_FIELDS, SYMPTOMS, ContractError, PetNutritionProfileValidator,
    require, warning,
)
from .practical import digest
from .practical_disease import ALIASES, SPECIES_ALIASES, STONE_TYPES
from .profile import lifecycle


DEPRECATED_PROFILE_FIELDS = {
    'feeding_goal', 'current_diet_type', 'extra_foods', 'current_diet_context',
    'main_diet', 'commercial_extras', 'current_supplements', 'current_main_diet', 'current_intake',
}
DAILY_PROFILE_FIELDS = (PROFILE_FIELDS - DEPRECATED_PROFILE_FIELDS) | {
    'disease_subtypes',
}

# These are the existing Step 1 IDs from backend_bridge.py, moved into an
# additive API boundary. No UI or older API mapping is changed.
DISEASE_ID_ALIASES = {
    'CHRONIC_PANCREATITIS': 'PANCREATITIS',
    'CHRONIC_CONSTIPATION': 'CONSTIPATION', 'MEGACOLON': 'CONSTIPATION',
    'CHRONIC_LIVER_DISEASE': 'LIVER_CHRONIC', 'BILIARY_DISEASE': 'BILIARY',
    'MITRAL_VALVE_DISEASE': 'MMVD', 'CANINE_HYPOTHYROIDISM': 'HYPOTHYROID_DOG',
    'FELINE_HYPERTHYROIDISM': 'HYPERTHYROID_CAT',
    'CHRONIC_SKIN_DISEASE': 'SKIN_CHRONIC', 'HIP_DISEASE': 'JOINT_CHRONIC',
    'CHRONIC_JOINT_DISEASE': 'JOINT_CHRONIC', 'PERIODONTAL_DISEASE': 'PERIODONTAL',
    'CHEWING_DISORDER': 'CHEWING_DIFFICULTY', 'FELINE_GINGIVOSTOMATITIS': 'FCGS',
    'FELINE_ASTHMA': 'RESPIRATORY_OTHER', 'CHRONIC_BRONCHITIS': 'RESPIRATORY_OTHER',
    'TRACHEAL_COLLAPSE': 'RESPIRATORY_OTHER', 'INTESTINAL_PARASITES': 'PARASITES_OTHER',
    'GIARDIASIS': 'PARASITES_OTHER', 'HEARTWORM': 'PARASITES_OTHER',
    'FIV': 'INFECTION_OTHER', 'FELV': 'INFECTION_OTHER', 'FIP': 'INFECTION_OTHER',
    'LYMPHOMA': 'NEOPLASIA', 'MAST_CELL_TUMOR': 'NEOPLASIA',
    'MAMMARY_TUMOR': 'NEOPLASIA', 'OTHER_TUMOR': 'NEOPLASIA',
}
SYMPTOM_ALIASES = {
    'POOR_APPETITE': 'REDUCED_APPETITE', 'APPETITE_VARIATION': 'REDUCED_APPETITE', 'OCCASIONAL_SOFT_STOOL': 'SOFT_STOOL', 'FREQUENT_VOMITING': 'PERSISTENT_VOMITING',
    'DIARRHEA': 'SOFT_STOOL', 'WEIGHT_LOSS': 'WEIGHT_CHANGE',
    'WEIGHT_GAIN': 'WEIGHT_CHANGE', 'SEVERE_DEHYDRATION': 'DEHYDRATION',
    '持续频繁呕吐': 'PERSISTENT_SEVERE_VOMITING', '无法进食': 'UNABLE_TO_EAT',
    '尿闭风险': 'UNABLE_TO_URINATE', '严重脱水': 'DEHYDRATION',
    '严重腹泻/脱水': 'DEHYDRATION', '明显虚弱': 'MARKED_WEAKNESS',
    '急性严重状态': 'ACUTE_SEVERE_ILLNESS',
}
BODY_CONDITIONS = {'SEVERE_UNDERWEIGHT': 2, 'MILD_UNDERWEIGHT': 3, 'MILD_OVERWEIGHT': 7, 'VERY_THIN': 2, 'THIN': 3, 'IDEAL': 5, 'NORMAL': 5,
                   'OVERWEIGHT': 7, 'OBESE': 9}
GROUP_TAGS = {'GRAINS': {'RICE', 'OAT'}}
RESTRICTION_REASONS = {'CONFIRMED_ALLERGY': 'ALLERGY', 'VET_AVOID': 'VET_RESTRICTED'}


def _code(value, field):
    require(isinstance(value, str) and bool(value.strip()), 'CODE_REQUIRED', field)
    return value.strip().upper()


def canonical_disease_id(value, species, store):
    did = _code(value, 'diseases')
    did = did.removeprefix('STONE_')
    did = DISEASE_ID_ALIASES.get(did, did)
    if did in SPECIES_ALIASES:
        did = SPECIES_ALIASES[did][species == 'CAT']
    names = {row['name_zh']: row['disease_id'] for row in store.rows('diseases')}
    return ALIASES.get(did, names.get(did, did))


def _diseases(profile, store):
    species = profile.get('species')
    raw = profile.get('diseases', [])
    subtypes = profile.get('disease_subtypes', [])
    require(isinstance(raw, list), 'DISEASES_ARRAY_REQUIRED', 'diseases')
    require(isinstance(subtypes, list), 'DISEASE_SUBTYPES_ARRAY_REQUIRED', 'disease_subtypes')
    by_id = {}
    for item in subtypes:
        if isinstance(item, str):
            item = {'disease_id': 'UROLITHIASIS', 'subtype': item}
        require(isinstance(item, dict) and set(item) == {'disease_id', 'subtype'},
                'DISEASE_SUBTYPE_OBJECT_INVALID', 'disease_subtypes')
        did = canonical_disease_id(item['disease_id'], species, store)
        subtype = _code(item['subtype'], 'disease_subtypes').removeprefix('STONE_')
        require(did not in by_id or by_id[did] == subtype,
                'DISEASE_SUBTYPE_CONFLICT', 'disease_subtypes')
        by_id[did] = subtype
    out, used, translations = [], set(), []
    for item in raw:
        if isinstance(item, str):
            item = {'disease_id': item}
        require(isinstance(item, dict) and set(item) <= {
            'disease_id', 'id', 'confirmed', 'stage', 'subtype', 'clinical_status',
        }, 'DISEASE_OBJECT_INVALID', 'diseases')
        require(not ('id' in item and 'disease_id' in item and item['id'] != item['disease_id']),
                'DISEASE_ID_CONFLICT', 'diseases')
        original = item.get('disease_id', item.get('id'))
        did = canonical_disease_id(original, species, store)
        subtype = item.get('subtype')
        if subtype is not None:
            subtype = _code(subtype, 'diseases.subtype').removeprefix('STONE_')
        if did in by_id:
            require(subtype is None or subtype == by_id[did],
                    'DISEASE_SUBTYPE_CONFLICT', 'disease_subtypes')
            subtype = by_id[did]
            used.add(did)
        if did == 'UROLITH_UNKNOWN' and subtype is not None:
            require(subtype in STONE_TYPES | {'OTHER', 'UNKNOWN'},
                    'UNKNOWN_STONE_SUBTYPE', 'disease_subtypes')
            if subtype in STONE_TYPES:
                did = subtype
        elif did in STONE_TYPES and subtype is not None:
            require(subtype == did, 'DISEASE_SUBTYPE_CONFLICT', 'disease_subtypes')
        entry = {'disease_id': did, **{k: deepcopy(v) for k, v in item.items()
                                     if k not in {'id', 'disease_id', 'subtype'}}}
        if subtype is not None:
            entry['subtype'] = subtype
            if subtype in {'ACUTE', 'ACUTE_SEVERE', 'UNSTABLE'}:
                # Explicit acute diagnoses are owner-supplied safety facts,
                # regardless of which supported disease field carried them.
                entry['clinical_status'] = 'UNSTABLE' if subtype == 'UNSTABLE' else 'ACUTE'
        # Alias selections may refer to the same diagnosis. An exact duplicate
        # is collapsed; contradictory diagnosis metadata must never disappear.
        previous = next((d for d in out if d['disease_id'] == did), None)
        require(previous is None or previous == entry, 'DUPLICATE_DISEASE_CONFLICT', 'diseases')
        if previous is None:
            out.append(entry)
        if did != original:
            translations.append({'input_id': original, 'disease_id': did})
    require(set(by_id) <= used, 'SUBTYPE_WITHOUT_DIAGNOSIS', 'disease_subtypes')
    return out, translations


def _food_matches(value, ingredients):
    if value in ingredients:
        return [value]
    tags = GROUP_TAGS.get(value, {value})
    return [iid for iid, item in ingredients.items()
            if tags & set((item['allergen_tags'] or '').split(';'))
            or item['food_category'] in tags]


def normalize_daily_profile(profile, store):
    """Return ``(normalized_profile, legacy_compatible_check, warnings)``.

    Validation failures raise the same structured ContractError used by API 1.1.
    Deprecated dietary fields are discarded before biological validation and
    identity generation, so even old records cannot alter the core daily solve.
    """
    from .daily_recipe_v13_schema import validate_daily_model
    validate_daily_model('PetNutritionProfile', profile)
    require(isinstance(profile, dict), 'PROFILE_OBJECT_REQUIRED', 'profile')
    unknown = set(profile) - DAILY_PROFILE_FIELDS - DEPRECATED_PROFILE_FIELDS
    require(not unknown, 'UNKNOWN_PROFILE_FIELD', sorted(unknown)[0] if unknown else None)
    p = {k: deepcopy(v) for k, v in profile.items() if k not in DEPRECATED_PROFILE_FIELDS}
    generated_id = 'profile_id' not in p
    p.setdefault('profile_id', 'DAILY_PROFILE')
    require(p.get('species') in {'DOG', 'CAT'}, 'SPECIES_REQUIRED', 'species')
    original_stage = p.get('life_stage')
    if isinstance(original_stage, str):
        original_stage = original_stage.removeprefix(p['species'] + '_')
        original_stage = {'LATE_GROWTH_SMALL': 'LATE_GROWTH_SMALL_MEDIUM'}.get(original_stage, original_stage)
        p['life_stage'] = original_stage
    require(original_stage is None or original_stage in {
        'GROWTH', 'ADULT', 'MATURE', 'SENIOR', 'EARLY_GROWTH',
        'LATE_GROWTH_SMALL_MEDIUM', 'LATE_GROWTH_LARGE', 'UNWEANED',
    }, 'LIFE_STAGE_INVALID', 'life_stage')
    if p['species'] == 'CAT':
        require(original_stage not in {'EARLY_GROWTH', 'LATE_GROWTH_SMALL_MEDIUM', 'LATE_GROWTH_LARGE'},
                'SPECIES_SPECIFIC_FIELD_CONFLICT', 'life_stage')
    p['diseases'], translations = _diseases(p, store)
    p.pop('disease_subtypes', None)
    body = p.get('body_condition')
    if isinstance(body, str):
        p['body_condition'] = BODY_CONDITIONS.get(body, body)
    if p.get('activity_level') == 'NORMAL':
        p['activity_level'] = 'MODERATE_LOW_IMPACT' if p['species'] == 'DOG' else 'LOW'
    if p.get('weight_trend') in {'LOSS', 'GAIN'}:
        p['weight_trend'] = {'LOSS': 'LOSING', 'GAIN': 'GAINING'}[p['weight_trend']]
    signs = p.get('recent_symptoms', [])
    require(isinstance(signs, list), 'ARRAY_REQUIRED', 'recent_symptoms')
    normalized_signs = [_code(s, 'recent_symptoms') for s in signs]
    p['recent_symptoms'] = list(dict.fromkeys(SYMPTOM_ALIASES.get(s, s) for s in normalized_signs))

    ingredients = store.keyed('ingredients', 'ingredient_id')
    restrictions = p.get('food_restrictions', [])
    require(isinstance(restrictions, list), 'ARRAY_REQUIRED', 'food_restrictions')
    expanded, public_restrictions, hard_groups = [], [], set()
    for item in restrictions:
        require(isinstance(item, dict) and set(item) in (
            {'ingredient_id', 'reason'}, {'ingredient', 'reason'},
        ), 'RESTRICTION_OBJECT_INVALID', 'food_restrictions')
        value = _code(item.get('ingredient_id', item.get('ingredient')), 'food_restrictions')
        matches = _food_matches(value, ingredients)
        require(bool(matches), 'UNKNOWN_INGREDIENT_ID', 'food_restrictions')
        reason = RESTRICTION_REASONS.get(item['reason'], item['reason'])
        require(reason in {'ALLERGY', 'INTOLERANCE', 'VET_RESTRICTED'},
                'RESTRICTION_REASON_INVALID', 'food_restrictions')
        public = {'ingredient_id' if value in ingredients else 'ingredient': value, 'reason': reason}
        if public not in public_restrictions:
            public_restrictions.append(public)
        if value not in ingredients:
            hard_groups.update(GROUP_TAGS.get(value, {value}))
        for iid in matches:
            row = {'ingredient_id': iid, 'reason': reason}
            if row not in expanded:
                expanded.append(row)
    p['food_restrictions'] = expanded
    dislikes = p.get('disliked_foods', [])
    require(isinstance(dislikes, list), 'ARRAY_REQUIRED', 'disliked_foods')
    normalized_dislikes = []
    for item in dislikes:
        value = _code(item, 'disliked_foods')
        matches = _food_matches(value, ingredients)
        require(bool(matches), 'UNKNOWN_DISLIKED_FOOD', 'disliked_foods')
        values = GROUP_TAGS.get(value, {value})
        if value in ingredients:
            values = set((ingredients[value]['allergen_tags'] or '').split(';')) - {''} or {value}
        normalized_dislikes.extend(sorted(values))
    p['disliked_foods'] = list(dict.fromkeys(normalized_dislikes))

    from .life_stage_resolver import LifeStageResolver
    if p.get('birth_date'):
        # Freeze the legacy transport default before the shared resolver runs.
        p.setdefault('as_of_date', date.today().isoformat())
    try:
        age = LifeStageResolver.profile_age(p)
    except ValueError as exc:
        raise ContractError(str(exc), 'birth_date' if p.get('birth_date') else 'age_years') from exc
    actual_days = age['age_days']
    if p.get('birth_date'):
        for key in ('age_years', 'age_months'):
            require(p.get(key) is None or p[key] == age[key], 'AGE_DATE_CONFLICT', key)
    p.update(age_years=age['age_years'], age_months=age['age_months'])
    if p['species']=='DOG' and age['age_months_completed']>=24 and original_stage not in {'GROWTH','EARLY_GROWTH','LATE_GROWTH_SMALL_MEDIUM','LATE_GROWTH_LARGE'} and not p.get('expected_adult_weight_kg'):
        p.setdefault('growth_complete', True)
    # Lifecycle hints are checked below against corrected calendar age.
    adapter = deepcopy(p)
    adapter['life_stage'] = None
    if p['species'] == 'DOG' and original_stage in {'ADULT', 'MATURE', 'SENIOR'}:
        adapter.setdefault('growth_complete', True)
    adapter.update(feeding_goal='FULL_DAILY_DIET', current_diet_type='UNKNOWN', extra_foods=[])
    check = PetNutritionProfileValidator(store).validate(adapter)
    if check['status'] == 'INVALID':
        detail = check['errors'][0]
        raise ContractError(detail['code'], detail['field'], detail['message'])
    normalized, pet = check['normalized'], check['engine_pet']
    pet['neuter_status_known'] = normalized['neutered'] is not None
    pet['age_months_completed'] = normalized['age_years'] * 12 + normalized['age_months']
    pet['age_years_completed'] = normalized['age_years']
    if actual_days is not None:
        pet['age_days'] = actual_days
    if original_stage in {'MATURE', 'SENIOR'} and p['species'] == 'DOG':
        pet['life_stage_hint'] = original_stage
    try:
        stage, _ = lifecycle(pet, store)
    except ValueError:
        stage = None
    if original_stage is not None and stage is not None:
        actual = stage.removeprefix(p['species'] + '_').replace('LATE_GROWTH_SMALL', 'LATE_GROWTH_SMALL_MEDIUM')
        require(original_stage == actual or original_stage == 'GROWTH' and 'GROWTH' in actual,
                'LIFE_STAGE_AGE_CONFLICT', 'life_stage')
    if stage:
        normalized['life_stage'] = stage.removeprefix(p['species'] + '_').replace('LATE_GROWTH_SMALL', 'LATE_GROWTH_SMALL_MEDIUM')
        pet['life_stage'] = normalized['life_stage']
        check['warnings'] = [w for w in check['warnings'] if w['code'] != 'GROWTH_CONTEXT_REQUIRED']
    else:
        normalized['life_stage'] = original_stage
    for key in ('growth_complete', 'weaned'):
        if key in pet:
            normalized[key] = pet[key]
    for key in DEPRECATED_PROFILE_FIELDS:
        normalized.pop(key, None)
    normalized['disease_subtypes'] = [{'disease_id': d['disease_id'], 'subtype': d['subtype']}
                                      for d in normalized['diseases'] if d.get('subtype')]
    # Preserve owner-selected group identity for normalized profile replay.
    # Expanding FISH to COD/CARP/... alone loses the FISH carrier restriction.
    normalized['food_restrictions'] = public_restrictions
    if generated_id:
        normalized['profile_id'] = 'DAILY_' + digest({k: v for k, v in normalized.items()
                                                    if k != 'profile_id'})[:24]
    # All hard restrictions cover the same identified food across preparations.
    # Egg is its own tag, so chicken avoidance does not imply an egg diagnosis.
    hard_tags = set()
    for item in expanded:
        hard_tags.update(t for t in (ingredients[item['ingredient_id']]['allergen_tags'] or '').split(';') if t)
    check['excluded_ingredients'] = sorted(set(check['excluded_ingredients']) | {
        iid for iid, item in ingredients.items()
        if hard_tags & set((item['allergen_tags'] or '').split(';'))
    })
    # Carries restrictions into supplement carrier screening as well as foods.
    pet['allergies'] = sorted(set(pet['allergies']) | hard_tags | hard_groups)
    check['disease_id_translations'] = translations
    nonurgent = set(store.config.get('recognized_nonurgent_signs', []))
    if set(pet['recent_abnormalities']) & nonurgent:
        check['warnings'].append(warning('RECENT_SYMPTOMS_OBSERVE',
                                        '轻微异常需继续观察；加重或无法正常进食时停止自动鲜食并就医。',
                                        'recent_symptoms'))
    if set(profile) & DEPRECATED_PROFILE_FIELDS:
        check['warnings'].append(warning('DEPRECATED_DIET_CONTEXT_IGNORED',
                                        'API 1.3 仅依据宠物状况设计每日鲜食；旧饮食和当前补剂信息未参与本次计算。',
                                        'profile'))
    check['status'] = 'WARNING' if check['warnings'] else 'VALID'
    return normalized, check, check['warnings']
