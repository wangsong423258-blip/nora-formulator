"""Integrated, diagnosis-only recipe policy. No BCS or chronic-disease gate.

Sourced selection directions are inherited; individual clinical targets are
never inferred from a diagnosis. All quantitative nutrient limits remain in
the actual solver. Body adjustments are explicit product starting heuristics,
not guideline-prescribed multipliers or a refeeding/treatment protocol.
"""
from copy import deepcopy
from .daily_disease import (
    DISEASE_CATEGORIES, DAILY_CARE_FIELDS, disease_category,
    daily_disease_advice as legacy_advice, daily_disease_design as legacy_design,
)


def daily_disease_advice(pet, store):
    advice = legacy_advice(pet, store)
    # Severe diarrhoea alone is not evidence of dehydration. Explicit
    # dehydration, inability to eat/urinate and other acute signs remain hard.
    acute = [a for a in advice['acute_red_flags'] if a not in {'SEVERE_DIARRHEA', '严重腹泻'}]
    conflicts = advice['conflicts'] + advice['rule_merge']['compatible_combinations']
    advice.update(version='DAILY_DISEASE_1.3',
                  status='BLOCKED_ACUTE_CONDITION' if acute else 'PRACTICAL_CLEAR',
                  classification='GENERAL_DISEASE_ADAPTED_RECIPE',
                  recipe_scope='GENERAL_DISEASE_ADAPTED_RECIPE' if advice['diseases'] else 'DAILY_FRESH_FOOD_RECIPE',
                  acute_red_flags=acute,
                  reasons=['ACUTE_RED_FLAG:' + a for a in acute],
                  conflicts=[], immediate_action='STOP_AUTOMATIC_RECIPE_AND_SEEK_VETERINARY_CARE' if acute else None)
    advice['rule_merge'] = {
        'policy': 'CONSERVATIVE_RECIPE_MERGE',
        'status': 'BLOCKED_ACUTE_CONDITION' if acute else 'PENDING_SOLVER',
        'compatible_combinations': [{**c, 'policy': 'CONSERVATIVE_RECIPE_MERGE',
            'status': 'PENDING_SOLVER', 'clinical_treatment_targets_claimed': False} for c in conflicts],
        'conflicts': [], 'preserve_species_and_life_stage_nutrient_minima': True,
        'solver_required_before_recommendation': True,
    }
    for detail in advice['disease_adaptations']:
        detail['classification'] = detail['nutrition_action_level'] = 'GENERAL_DISEASE_ADAPTED_RECIPE'
        if detail['disease_id'] == 'CHF':
            detail['food_direction'] = '不加盐腌食物，保留能量和必需营养；水分与电解质沿用已有医嘱，不生成极低钠或统一补水量。'
        elif detail['disease_id'] == 'PLE':
            detail['food_direction'] = '选择稳定、较瘦的食物组合并保留必需蛋白；不按疾病名称推定个体治疗性脂肪或蛋白目标。'
        elif detail['disease_id'] == 'UROLITH_UNKNOWN':
            detail['food_direction'] = '保留未知结石类型，采用湿润、无额外盐和内脏的保守组合；不指定酸化、碱化或溶石目标。'
    return advice


def body_strategy(pet, energy, stage, diseases):
    bcs, trend = pet['bcs'], pet['weight_trend']
    category = ('SEVERE_UNDERWEIGHT' if bcs <= 2 else 'MILD_UNDERWEIGHT' if bcs == 3
                else 'IDEAL' if bcs <= 5 else 'MILD_OVERWEIGHT' if bcs <= 7 else 'OBESE')
    factor = {'SEVERE_UNDERWEIGHT': 1.05, 'MILD_UNDERWEIGHT': 1.10,
              'IDEAL': 1., 'MILD_OVERWEIGHT': .95, 'OBESE': .90}[category]
    if 'OBESITY' in diseases and bcs >= 4:
        factor = min(factor, .90)
    if trend == 'LOSING' and bcs >= 3:
        factor = min(1.15, factor + .05)
    if trend == 'GAINING' and bcs >= 6:
        factor -= .05
    # The established base already incorporates activity and (for cats)
    # neuter status. A small additional adult-dog weight-control adjustment is
    # explicitly a product heuristic; it never acts on growth or thin dogs.
    neuter_factor = .95 if (pet['species'] == 'DOG' and pet['neutered'] and bcs >= 6
                           and 'GROWTH' not in stage) else 1.
    factor *= neuter_factor
    if 'GROWTH' in stage:
        factor = max(1., factor)  # never prescribe a puppy/kitten weight-loss diet
    mode = 'CONSERVATIVE_RECOVERY' if bcs <= 2 else 'GRADUAL_WEIGHT_GAIN' if bcs == 3 else 'WEIGHT_MANAGEMENT' if factor < 1 else 'MAINTENANCE_AND_TREND_MONITORING'
    return {
        'body_condition': category, 'bcs': bcs, 'weight_trend': trend,
        'strategy': mode, 'base_energy_kcal': energy, 'energy_factor': factor,
        'daily_energy_kcal': energy * factor,
        'activity': pet['activity'], 'neutered': pet['neutered'] if pet.get('neuter_status_known', True) else None, 'life_stage': stage,
        'neuter_weight_management_factor': neuter_factor,
        'scope': 'PRODUCT_STARTING_HEURISTIC_NOT_CLINICAL_REFEEDING_OR_IDEAL_WEIGHT_PRESCRIPTION',
        'monitoring': ['记录实际食量、体重趋势、体况和肌肉状态；按复查结果重算整份配方。',
                       '明显消瘦或持续下降需同时查明原因；本配方不等于营养恢复治疗方案。'] if bcs < 4 or trend == 'LOSING' else
                      ['每周在相同条件下记录体重、食欲和体况趋势，调整后重新核算全部营养。'],
    }


def daily_disease_design(pet, advice, bounds, energy, stage):
    bounds, _, policy, legacy_reasons = legacy_design(pet, advice, bounds, energy, stage)
    ids = set(advice['diseases'])
    body = body_strategy(pet, energy, stage, ids)
    policy.update(version='CN_DAILY_DISEASE_DESIGN_1.3', scope='GENERAL_DISEASE_ADAPTED_RECIPE',
                  objective_priority='SAFETY_NUTRITION_AVAILABILITY_COST_PREPARATION_PREFERENCE',
                  body_condition_strategy=body, energy_adjustment=body['strategy'],
                  energy_adjustment_scope=body['scope'],
                  preserve_original_absolute_nutrient_floor=True)
    exclude = set(policy['excluded_categories'])
    minimize = policy['minimize_nutrients']
    if body['daily_energy_kcal'] < energy:
        minimize.append('fat')
        policy.update(prefer_moist_food=True, retain_cooking_water=True)
    elif pet['bcs'] < 4:
        # Compact portions aid acceptance without blindly selecting fattier
        # foods; a pancreatitis fat ceiling always wins this soft objective.
        policy['prefer_compact_food_portion'] = True
    if 'PLN' in ids:
        minimize.append('phosphorus'); exclude.add('ORGAN')
        policy['pln_scope'] = 'LOWER_PHOSPHORUS_WITH_ESSENTIAL_PROTEIN_PRESERVED_NO_PROTEINURIA_TARGET'
    if ids & {'MMVD', 'HCM', 'DCM', 'CHF', 'HYPERTENSION'}:
        minimize.append('sodium')
        policy['cardiac_scope'] = 'LOWER_EXCESS_SODIUM_WITH_SPECIES_MINIMUM_PRESERVED_NO_EXTREME_RESTRICTION'
    if 'CHF' in ids:
        policy.update(prefer_moist_food=False, retain_cooking_water=False,
                      hydration_policy='PRESERVE_EXISTING_FLUID_AND_MEDICATION_PLAN_NO_AUTOMATIC_EXTRA_WATER')
    if 'COPPER_HEPATOPATHY' in ids:
        exclude.add('ORGAN'); minimize.append('copper')
        policy['copper_scope'] = 'AVOID_COPPER_RICH_ORGANS_COUNT_PREMIX_COPPER_PRESERVE_MINIMUM_NO_TREATMENT_TARGET'
    if 'HEPATIC_ENCEPHALOPATHY' in ids:
        exclude.add('ORGAN')
        policy['protein_policy'] = 'PRESERVE_ESSENTIAL_PROTEIN_NO_DIAGNOSIS_ONLY_THERAPEUTIC_RESTRICTION'
    if 'PLE' in ids and pet['species'] == 'DOG':
        minimize.append('fat')
    if ids & {'UROLITH_UNKNOWN', 'STRUVITE', 'CYSTINE'}:
        policy.update(prefer_moist_food='CHF' not in ids, retain_cooking_water='CHF' not in ids,
                      urinary_policy='NO_INFERRED_PH_TARGET_OR_DISSOLUTION_CLAIM_PRESERVE_MINERAL_AND_AMINO_ACID_BOUNDS')
        policy['supplement_strategy'].append('NO_URINARY_ACIDIFIER_OR_ALKALIZER')
    if 'UROLITH_UNKNOWN' in ids:
        exclude.add('ORGAN')
        policy['unknown_stone_subtype_preserved'] = True
    if ids & {'CHRONIC_DIARRHEA', 'CIE_DOG', 'CIE_CAT', 'FOOD_RESPONSIVE_ENTEROPATHY', 'EPI', 'PLE'}:
        policy.update(consistent_meal_composition=True, simple_digestive_recipe=True)
    # Earlier targets requiring clinical measurements are deliberately not
    # claimed implemented. Their safe general counterparts above are executable.
    policy['clinical_targets_not_inferred'] = policy.pop('unimplemented_directions', [])
    policy['general_directions'] = sorted(set(advice['recipe_constraint_requirements']))
    policy['excluded_categories'] = sorted(exclude)
    policy['minimize_nutrients'] = list(dict.fromkeys(minimize))
    policy['rule_merge']['policy'] = 'CONSERVATIVE_RECIPE_MERGE'
    contradictions = [r for r in legacy_reasons if r.startswith('MERGED_NUTRIENT_BOUNDS_CONFLICT:')]
    return bounds, body['daily_energy_kcal'], policy, contradictions
