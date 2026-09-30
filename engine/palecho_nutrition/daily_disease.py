"""Diagnosis-based daily recipe rules and explicit merge decisions for API 1.2.

Existing sourced household directions are reused without changing the frozen
clinical solver or API 1.0/1.1. Directional adaptation does not assert a precise
treatment diet or manufacture concentration targets from laboratory values.
"""
from copy import deepcopy
from .practical import NUMERICAL_DISEASE_ACTIONS
from .practical_disease import CLASSIFICATIONS, STONE_TYPES, disease_advice
from .solver import NutrientBound


DISEASE_CATEGORIES = (
    'RENAL_URINARY', 'GI_DIGESTIVE', 'PANCREAS', 'HEPATOBILIARY',
    'CARDIOVASCULAR', 'ENDOCRINE', 'METABOLIC', 'DERMATOLOGY_ALLERGY',
    'MUSCULOSKELETAL', 'ORAL_DENTAL', 'NEUROLOGICAL', 'RESPIRATORY',
    'INFECTIOUS_PARASITIC', 'OTHER',
)
DAILY_CARE_FIELDS = (
    'foods_to_limit', 'foods_to_avoid', 'foods_preferred', 'hydration_notes',
    'feeding_notes', 'weight_monitoring', 'appetite_monitoring',
    'stool_monitoring', 'red_flags',
)
CARE_MAP = {
    'foods_preferred': 'foods_or_patterns_preferred',
    'stool_monitoring': 'stool_vomiting_monitoring',
    'red_flags': 'stop_self_adjustment',
}
HANDLED_NUMERICAL_DIRECTIONS = {
    'CONTROL_PHOSPHORUS', 'EXCLUDE_HIGH_FAT', 'WEIGHT_MANAGEMENT',
    'AVOID_HIGH_PURINE_ORGANS', 'AVOID_HIGH_OXALATE',
    'PREFER_LOWER_CARBOHYDRATE_CAT',
}


def disease_category(disease_id, legacy_category):
    if disease_id in {'PANCREATITIS_DOG', 'PANCREATITIS_CAT', 'EPI'}:
        return 'PANCREAS'
    if disease_id in {'OBESITY', 'HYPERLIPIDEMIA'}:
        return 'METABOLIC'
    if disease_id in {'EPILEPSY', 'COGNITIVE_DYSFUNCTION'}:
        return 'NEUROLOGICAL'
    if disease_id == 'RESPIRATORY_OTHER':
        return 'RESPIRATORY'
    if disease_id in {'INFECTION_OTHER', 'PARASITES_OTHER'}:
        return 'INFECTIOUS_PARASITIC'
    return {'GI_PANCREAS': 'GI_DIGESTIVE', 'ENDOCRINE_METABOLIC': 'ENDOCRINE',
            'ORAL': 'ORAL_DENTAL'}.get(legacy_category, legacy_category)


def _fallback(disease_id):
    return {'text': '该项没有已验证的额外疾病专属规则；按本次完整配方和该物种的基础照护执行。',
            'source_ids': ['PALECHO_SPEC'], 'disease_id': disease_id,
            'scope': 'NO_ADDITIONAL_VERIFIED_DISEASE_RULE'}


def daily_disease_advice(pet, store):
    """Merge compatible practical directions, retaining explicit risk routes.

    A diagnosis-only diabetes/pancreatitis pair need not be an automatic
    contradiction: merge its species-specific goals then ask the whole recipe
    solver. Acute flags, growth conflicts, unknown stones, CHF, and verified
    conflicting targets still prevent ordinary recipe production.
    """
    advice = deepcopy(disease_advice(pet, store))
    decisions, pending = [], []
    for conflict in advice['conflicts']:
        pair = set(conflict['diseases'])
        resolvable = conflict['reason'] == 'DIABETES_PANCREATITIS_COMORBIDITY_REVIEW'
        if conflict['reason'] == 'RENAL_CARDIAC_NUTRIENT_AND_FLUID_PRIORITIES':
            resolvable = 'CHF' not in pair
        if resolvable:
            decisions.append({**conflict, 'policy': 'MERGE_DIRECTIONS_THEN_WHOLE_RECIPE_SOLVE',
                              'status': 'PENDING_SOLVER', 'clinical_treatment_targets_claimed': False})
        else:
            pending.append(conflict)
    removed_reasons = {d['reason'] for d in decisions}
    advice['conflicts'] = pending
    advice['reasons'] = [r for r in advice['reasons'] if r not in removed_reasons]
    if advice['status'] == 'PROFESSIONAL_REVIEW' and not pending:
        remaining = [r for r in advice['reasons'] if not r.startswith('OBSERVE_AND_REASSESS:')]
        if not remaining and all(d['classification'] != CLASSIFICATIONS['D'] for d in advice['disease_details']):
            advice['status'] = 'PRACTICAL_CLEAR'
            advice['classification'] = next((CLASSIFICATIONS[c] for c in ('A', 'B', 'C')
                                            if any(d['classification'] == CLASSIFICATIONS[c]
                                                   for d in advice['disease_details'])), CLASSIFICATIONS['C'])
    advice['rule_merge'] = {
        'status': ('BLOCKED' if advice['status'] == 'BLOCKED' else
                   'PROFESSIONAL_REVIEW' if advice['status'] == 'PROFESSIONAL_REVIEW' else 'PENDING_SOLVER'),
        'compatible_combinations': decisions,
        'conflicts': deepcopy(pending),
        'preserve_species_and_life_stage_nutrient_minima': True,
        'solver_required_before_recommendation': True,
    }
    catalog = store.keyed('diseases', 'disease_id')
    adaptations = []
    for detail in advice['disease_details']:
        did = detail['disease_id']
        row = {**deepcopy(detail), 'category': disease_category(did, catalog[did]['category']),
               'legacy_category': catalog[did]['category']}
        for field in DAILY_CARE_FIELDS:
            entries = advice['feeding_notes'] if field == 'feeding_notes' else advice['daily_care'].get(CARE_MAP.get(field, field), [])
            row[field] = [deepcopy(entry) for entry in entries if entry.get('disease_id') == did]
            if not row[field]:
                row[field] = [_fallback(did)]
        adaptations.append(row)
    advice['disease_adaptations'] = adaptations
    advice['version'] = 'DAILY_DISEASE_1.2'
    advice['recipe_scope'] = 'DISEASE_ADAPTED_RECIPE' if advice['diseases'] else 'DAILY_FRESH_FOOD_RECIPE'
    # Carry the same nine fields in an aggregate form for CookingPlan adapters.
    advice['daily_lifestyle_notes'] = {
        field: [deepcopy(note) for adaptation in adaptations for note in adaptation[field]]
        for field in DAILY_CARE_FIELDS
    }
    return advice


def daily_disease_design(pet, advice, bounds, energy, stage):
    """Return bounds, daily energy, executable selection policy and review codes.

    The canine fat limit is the existing Merck rule. 19.9 represents the strict
    ``<20`` boundary at the established one-decimal policy precision. The 10%
    obesity adjustment remains an explicitly labelled product starting estimate,
    retaining the full nutrient floor; neither is a new clinical target.
    """
    ids = set(advice['diseases'])
    bounds = list(bounds)
    policy = {
        'version': 'CN_DAILY_DISEASE_DESIGN_1.2', 'minimize_nutrients': [],
        'excluded_categories': [], 'exclude_ids': [],
        'ingredient_priority_rules': [], 'supplement_strategy': [],
        'prefer_moist_food': False, 'retain_cooking_water': False,
        'scope': 'DIAGNOSIS_ADAPTED_NOT_PRECISE_THERAPEUTIC_PRESCRIPTION',
        'clinical_measurements_required': [],
        'rule_merge': deepcopy(advice.get('rule_merge', {})),
        'disease_adaptations': deepcopy(advice.get('disease_adaptations', [])),
    }
    reasons, excluded = [], set()
    daily = energy
    if 'CKD' in ids:
        policy['minimize_nutrients'].append('phosphorus')
        excluded.add('ORGAN')
        policy['ckd_scope'] = 'LOWER_PHOSPHORUS_SELECTION_WITH_HEALTHY_MINIMA_PRESERVED_NOT_RENAL_TREATMENT_TARGET'
        policy['ingredient_priority_rules'].append({
            'rule': 'PREFER_LOWER_PHOSPHORUS_PROTEIN_SOURCES', 'nutrient_id': 'phosphorus',
            'source_id': 'IRIS_DOG2026' if pet['species'] == 'DOG' else 'IRIS_CAT2026',
        })
        policy['supplement_strategy'].append('PREFER_CALCIUM_WITHOUT_ADDITIONAL_PHOSPHATE_WHEN_WHOLE_RECIPE_ALLOWS')
    # A diagnosis alone does not establish an individualized proteinuria target.
    # Keep PLN visible with care notes and route the unsupported direction.
    if ids & {'PANCREATITIS_DOG', 'HYPERLIPIDEMIA'}:
        if pet['species'] == 'DOG':
            bounds.append(NutrientBound(
                'DAILY_DOG_LOW_FAT', 'fat', 'g', 'PER_1000_KCAL_ME', maximum=19.9,
                source_id='MERCK_PANC', source_locator='Treatment; <20g fat/1000kcal; strict boundary represented at 0.1g precision',
            ))
            policy['exclude_high_fat_animal_sources'] = True
        policy['minimize_nutrients'].append('fat')
        policy['supplement_strategy'].append('COUNT_FISH_OIL_AND_ALL_CARRIERS_IN_TOTAL_FAT')
    if 'DIABETES_DOG' in ids:
        # Consistent meals are core; a soft lean-source preference does not
        # transplant feline low-carbohydrate targets into a canine formula.
        policy['minimize_nutrients'].append('fat')
        policy['consistent_meal_composition'] = True
    if 'DIABETES_CAT' in ids:
        excluded.add('STARCH')
        policy['consistent_meal_composition'] = True
    if ids & {'DIABETES_DOG', 'DIABETES_CAT'}:
        policy['feeding_schedule_policy'] = 'PRESERVE_EXISTING_VETERINARY_MEDICATION_MEAL_TIMING'
    if 'OBESITY' in ids or pet['bcs'] >= 6:
        daily = energy * .9
        policy['energy_adjustment'] = 'INITIAL_10_PERCENT_REDUCTION_REASSESS_WEEKLY'
        policy['energy_adjustment_scope'] = 'PRODUCT_STARTING_ESTIMATE_NOT_IDEAL_WEIGHT_PRESCRIPTION'
        policy['minimize_nutrients'].append('fat')
        policy['prefer_moist_food'] = True
        policy['retain_cooking_water'] = True
        policy['preserve_original_absolute_nutrient_floor'] = True
    if ids & {'URATE', 'LIVER_CHRONIC', 'BILIARY'}:
        excluded.add('ORGAN')
    if 'URATE' in ids:
        policy['ingredient_priority_rules'].append({
            'rule': 'EXCLUDE_HIGH_PURINE_ORGANS', 'excluded_category': 'ORGAN',
            'source_id': 'ACVIM_STONE2016',
        })
    if 'CALCIUM_OXALATE' in ids:
        # FDC_169967 is broccoli, not spinach. Do not copy the 1.1 mislabeled
        # exclusion or invent oxalate concentrations for the reference foods.
        policy['oxalate_policy'] = 'NO_UNVERIFIED_HIGH_OXALATE_FOODS_ADDED_TO_REFERENCE_CANDIDATES'
        policy['supplement_strategy'].extend([
            'DO_NOT_ADD_VITAMIN_C_OR_URINARY_ACIDIFIERS', 'PRESERVE_CALCIUM_PHOSPHORUS_BOUNDS',
        ])
    if ids & ({'CKD', 'FIC', 'CONSTIPATION'} | STONE_TYPES):
        policy['prefer_moist_food'] = True
        policy['retain_cooking_water'] = True
        policy['hydration_policy'] = 'MOISTEN_TO_TOLERANCE_KEEP_FRESH_WATER_AVAILABLE_NO_UNIVERSAL_FLUID_DOSE'
    if ids & {'MMVD', 'DCM', 'HCM', 'HYPERTENSION'}:
        policy['ingredient_priority_rules'].append({
            'rule': 'UNSEASONED_FOODS_NO_SALTY_EXTRAS', 'source_id': 'AAHA_THER2021',
        })
        policy['supplement_strategy'].append('NO_UNSUPERVISED_ELECTROLYTE_ADDITION')
    if ids & {'FOOD_ALLERGY', 'ADVERSE_FOOD_REACTION', 'FOOD_RESPONSIVE_ENTEROPATHY'}:
        policy['supplement_strategy'].append('EXCLUDE_CONFIRMED_ALLERGENS_AND_CHECK_ALL_CARRIERS')
        policy['protein_source_policy'] = 'TRACEABLE_EXCLUDED_ALLERGEN_FREE_SOURCES'
    if ids & {'CHEWING_DIFFICULTY', 'FCGS', 'MISSING_TEETH', 'PERIODONTAL'}:
        policy['texture_policy'] = 'SOFT_COOKED_SMALL_SAFE_PIECES'
    if 'GROWTH' in stage and ids & {'CKD', 'OBESITY', 'PANCREATITIS_DOG', 'HYPERLIPIDEMIA'}:
        reasons.append('GROWTH_DISEASE_TARGET_CONFLICT')
    if pet['muscle_condition'] not in {'NORMAL', 'UNKNOWN'} or pet['weight_trend'] == 'LOSING' or pet['bcs'] < 4:
        reasons.append('WEIGHT_OR_MUSCLE_LOSS_NEEDS_INDIVIDUAL_PLAN')
    unsupported = (set(advice['recipe_constraint_requirements']) & NUMERICAL_DISEASE_ACTIONS) - HANDLED_NUMERICAL_DIRECTIONS
    reasons.extend('DISEASE_SPECIFIC_PLAN_REQUIRED:' + action for action in sorted(unsupported))
    # Detect a true numeric contradiction before candidates are optimized.
    for lower in bounds:
        if lower.minimum is None:
            continue
        for upper in bounds:
            if upper.maximum is None:
                continue
            if (lower.nutrient, lower.unit, lower.basis) == (upper.nutrient, upper.unit, upper.basis) and lower.minimum > upper.maximum:
                reasons.append('MERGED_NUTRIENT_BOUNDS_CONFLICT:' + lower.nutrient)
    policy['minimize_nutrients'] = list(dict.fromkeys(policy['minimize_nutrients']))
    policy['excluded_categories'] = sorted(excluded)
    policy['implemented_directions'] = sorted(set(advice['recipe_constraint_requirements']) - unsupported)
    policy['unimplemented_directions'] = sorted(unsupported)
    return bounds, daily, policy, sorted(set(reasons))
