"""Diagnosis-based household nutrition directions, separate from precise prescriptions.

PRACTICAL_CLEAR authorizes showing advice, never certifies a solved recipe. The
recipe engine must implement and check every recipe_constraint_requirement.
This module neither reads clinical laboratory prerequisites nor writes to Store.
"""
from itertools import combinations


CLASSIFICATIONS = {
    'A': 'A_NUTRITION_ACTIVE', 'B': 'B_PARTIAL_ADJUSTMENT',
    'C': 'C_LIFESTYLE_ONLY', 'D': 'D_PROFESSIONAL_REVIEW',
}
CARE_FIELDS = (
    'foods_to_limit', 'foods_or_patterns_preferred', 'foods_to_avoid',
    'hydration_notes', 'weight_monitoring', 'appetite_monitoring',
    'stool_vomiting_monitoring', 'stop_self_adjustment',
)
CARE_LABELS = dict(zip(CARE_FIELDS, (
    '平时少吃什么', '什么类型食物更合适', '哪些东西尽量避免', '饮水注意',
    '体重注意', '食欲注意', '排便/呕吐注意', '什么时候不适合继续自行调整饮食',
)))

# These are product-level actions, not invented nutrient concentrations. Each
# action remains traceable to the existing disease source and a precise recipe
# engine must explicitly acknowledge its implementation before recommending.
DIRECTIONS = {
    'CKD': ('A', ['CONTROL_PHOSPHORUS', 'MAINTAIN_ENERGY_AND_MUSCLE', 'SUPPORT_WATER_INTAKE'],
            '优先磷受控、能量适足并能稳定吃下的食物组合；不把肾病一概处理为大量减肉或低蛋白。'),
    'PLN': ('A', ['INDIVIDUALIZE_PROTEIN_AND_PHOSPHORUS', 'MAINTAIN_ENERGY_AND_MUSCLE'],
            '蛋白尿需要兼顾蛋白摄入和肌肉维持；不自行使用极低蛋白食谱。'),
    'FIC': ('B', ['SUPPORT_WATER_INTAKE', 'MOIST_FOOD', 'REDUCE_FEEDING_STRESS'],
            '选择可接受的含水食物，改善饮水和进食环境；不自行添加尿液酸化剂。'),
    'STRUVITE': ('A', ['SUPPORT_WATER_INTAKE', 'STONE_SPECIFIC_MINERAL_CHECK'],
                 '按已知鸟粪石类型选择饮食；溶石和复发预防不同，鲜食不能被宣称具有溶石作用。'),
    'CALCIUM_OXALATE': ('A', ['SUPPORT_WATER_INTAKE', 'AVOID_HIGH_OXALATE', 'AVOID_EXTRA_VITAMIN_C', 'CHECK_CALCIUM_PHOSPHORUS'],
                         '关注饮水、草酸来源和适当钙磷；不自行把钙减为零，不自行酸化尿液。'),
    'URATE': ('A', ['SUPPORT_WATER_INTAKE', 'AVOID_HIGH_PURINE_ORGANS'],
              '减少高嘌呤内脏等来源；低嘌呤不等于任意降低全部蛋白质。'),
    'CYSTINE': ('A', ['SUPPORT_WATER_INTAKE', 'STONE_SPECIFIC_AMINO_ACID_CHECK'],
                '选择经核对的胱氨酸结石饮食方向；不擅自减少必需氨基酸或加碱化剂。'),
    'UROLITH_UNKNOWN': ('D', [], '结石成分未知时不能决定酸化、碱化或矿物质限制方向。'),
    'CHRONIC_DIARRHEA': ('B', ['CONSISTENT_SIMPLE_DIET', 'FIBER_BY_TOLERANCE'],
                         '保持食物组合稳定，按耐受调整纤维；不把所有慢性腹泻都当作需要低脂或高纤维。'),
    'CIE_DOG': ('B', ['CONSISTENT_SIMPLE_DIET', 'PRESERVE_DIET_TRIAL'],
                 '遵循既有食物试验方案，使用稳定且可追踪的蛋白来源；避免频繁换肉。'),
    'CIE_CAT': ('B', ['CONSISTENT_SIMPLE_DIET', 'PRESERVE_DIET_TRIAL'],
                 '结合猫实际食欲和耐受维持稳定饮食；不把犬慢性肠病的脂肪限制直接套用。'),
    'FOOD_RESPONSIVE_ENTEROPATHY': ('B', ['PRESERVE_DIET_TRIAL', 'EXCLUDE_CONFIRMED_ALLERGENS'],
                                    '保留已有效的食物排除或水解蛋白方案，避免零食及补剂载体破坏试验。'),
    'CONSTIPATION': ('B', ['SUPPORT_WATER_INTAKE', 'FIBER_BY_TOLERANCE'],
                     '重视水分；纤维是否增加取决于耐受和已有诊疗建议，不一律堆南瓜。'),
    'PANCREATITIS_DOG': ('A', ['EXCLUDE_HIGH_FAT', 'COUNT_ALL_ADDED_OILS', 'CONSISTENT_SIMPLE_DIET'],
                          '避开肥肉、带皮肉和额外油脂堆叠；油类补剂也计入总脂肪。'),
    'PANCREATITIS_CAT': ('B', ['MAINTAIN_ENERGY_AND_MUSCLE', 'CONSISTENT_SIMPLE_DIET'],
                          '优先稳定进食和耐受性；猫胰腺炎没有可通用套用的犬低脂上限。'),
    'EPI': ('B', ['CONSISTENT_SIMPLE_DIET', 'PRESERVE_PRESCRIBED_ENZYME_PLAN'],
             '保持可消化、可耐受的食物组合，按既有医嘱配合酶制剂；不自动严重限制脂肪。'),
    'DIABETES_DOG': ('B', ['CONSISTENT_MEALS', 'COUNT_TREATS', 'PRESERVE_MEDICATION_FEEDING_PLAN'],
                      '保持进食时间、分量和组成稳定；肥胖与消瘦分别处理，不套用猫的低碳水规则。'),
    'DIABETES_CAT': ('A', ['PREFER_LOWER_CARBOHYDRATE_CAT', 'MAINTAIN_ENERGY_AND_MUSCLE', 'PRESERVE_MEDICATION_FEEDING_PLAN'],
                      '优先碳水较低且蛋白适足、能稳定吃下的组合；改变饮食时关注既有降糖治疗配合。'),
    'OBESITY': ('A', ['WEIGHT_MANAGEMENT', 'COUNT_TREATS', 'PRESERVE_NUTRIENT_DENSITY'],
                 '控制总能量和零食，保留蛋白质与必需营养密度；按体重和体况趋势逐步调整。'),
    'HYPERLIPIDEMIA': ('A', ['EXCLUDE_HIGH_FAT', 'COUNT_ALL_ADDED_OILS'],
                         '选择较瘦的肉类，避免肥肉与额外加油；鱼油不能替代总脂肪控制。'),
    'MMVD': ('B', ['AVOID_SALTY_EXTRAS', 'MAINTAIN_ENERGY_AND_MUSCLE'],
               '减少盐腌肉、调味肉汤等额外钠来源，维持蛋白和能量；不自动采用极低钠。'),
    'HCM': ('B', ['AVOID_SALTY_EXTRAS', 'MAINTAIN_ENERGY_AND_MUSCLE'],
              '维持体重和肌肉，减少额外高盐食物；不凭心肌病名称自行补钾。'),
    'DCM': ('B', ['AVOID_SALTY_EXTRAS', 'MAINTAIN_ENERGY_AND_MUSCLE', 'CHECK_SPECIES_TAURINE'],
              '核对整体营养和牛磺酸来源，维持进食与肌肉；不把补牛磺酸当作所有心肌病的治疗。'),
    'CHF': ('D', ['AVOID_SALTY_EXTRAS', 'MAINTAIN_ENERGY_AND_MUSCLE'],
              '心衰的钠、水分及其他电解质管理与用药相关，保留日常提醒并转专业配方复核。'),
    'HYPERTENSION': ('B', ['AVOID_SALTY_EXTRAS'],
                       '避免额外高盐食物，继续既有诊疗；不声称仅靠低盐鲜食能控制血压。'),
    'LIVER_CHRONIC': ('B', ['MAINTAIN_ENERGY_AND_MUSCLE', 'AVOID_EXCESS_ORGANS'],
                        '保持足够进食和适当蛋白，避免用大量肝脏补营养；不一律低蛋白。'),
    'COPPER_HEPATOPATHY': ('D', ['AVOID_COPPER_RICH_ORGANS', 'REVIEW_PREMIX_COPPER'],
                             '铜相关肝病需核对肝脏等高铜来源及维矿产品；治疗目标可能与健康最低铜需求冲突。'),
    'HEPATIC_ENCEPHALOPATHY': ('D', ['INDIVIDUALIZE_PROTEIN'],
                                '蛋白耐受与临床状态需要个体处理；本模块不自动给出治疗性蛋白限制。'),
    'BILIARY': ('B', ['CONSISTENT_SIMPLE_DIET', 'AVOID_EXCESS_ORGANS'],
                  '维持稳定、可耐受的食物组合；不把所有胆道疾病都等同于同一低脂处方。'),
    'FOOD_ALLERGY': ('A', ['EXCLUDE_CONFIRMED_ALLERGENS', 'CHECK_SUPPLEMENT_CARRIERS', 'PRESERVE_DIET_TRIAL'],
                       '排除已确认的致敏食物及补剂载体，防止交叉接触；更换肉名不等于完成排除试验。'),
    'ADVERSE_FOOD_REACTION': ('A', ['EXCLUDE_CONFIRMED_ALLERGENS', 'CHECK_SUPPLEMENT_CARRIERS', 'PRESERVE_DIET_TRIAL'],
                                '排除已经明确引起不耐受或不良反应的来源，并保留既有食物试验安排。'),
    'OSTEOARTHRITIS': ('B', ['MAINTAIN_HEALTHY_WEIGHT', 'ACCESSIBLE_FEEDING'],
                         '维持合适体重，改善食盆可及性；鱼油需按可靠规格核算，不能随意叠加。'),
    'HYPERTHYROID_CAT': ('B', ['MAINTAIN_ENERGY_AND_MUSCLE', 'NO_UNSUPERVISED_IODINE_RESTRICTION'],
                            '关注体重、肌肉和足够进食；正在使用限碘治疗饮食时，额外鲜食会破坏专一性。'),
    'PLE': ('D', ['INDIVIDUALIZE_FAT_AND_PROTEIN'],
              '蛋白丢失性肠病涉及营养吸收及脂肪、蛋白的个体目标，需专业复核。'),
}

LIFESTYLE_ONLY = {
    'ATOPIC_DERMATITIS', 'SKIN_CHRONIC', 'CUSHING', 'HYPOTHYROID_DOG',
    'COGNITIVE_DYSFUNCTION', 'EPILEPSY', 'JOINT_CHRONIC', 'UTI',
}
ORAL = {'CHEWING_DIFFICULTY', 'FCGS', 'MISSING_TEETH', 'PERIODONTAL'}
STONE_TYPES = {'STRUVITE', 'CALCIUM_OXALATE', 'URATE', 'CYSTINE'}
CARDIAC = {'MMVD', 'HCM', 'DCM', 'CHF'}

ALIASES = {
    'FOOD_INTOLERANCE': 'ADVERSE_FOOD_REACTION', '食物不耐受': 'ADVERSE_FOOD_REACTION',
    'OA': 'OSTEOARTHRITIS', '慢性肾病': 'CKD',
    '结石': 'UROLITH_UNKNOWN', 'UROLITHIASIS': 'UROLITH_UNKNOWN',
    '鸟粪石': 'STRUVITE', '草酸钙结石': 'CALCIUM_OXALATE',
    '肥胖': 'OBESITY', '食物过敏': 'FOOD_ALLERGY',
}
SPECIES_ALIASES = {
    'DIABETES': ('DIABETES_DOG', 'DIABETES_CAT'), '糖尿病': ('DIABETES_DOG', 'DIABETES_CAT'),
    'PANCREATITIS': ('PANCREATITIS_DOG', 'PANCREATITIS_CAT'), '胰腺炎': ('PANCREATITIS_DOG', 'PANCREATITIS_CAT'),
    'CHRONIC_ENTEROPATHY': ('CIE_DOG', 'CIE_CAT'), '慢性肠病': ('CIE_DOG', 'CIE_CAT'),
}
ACUTE_FLAGS = {
    'PERSISTENT_FREQUENT_VOMITING', 'PERSISTENT_SEVERE_VOMITING', 'SEVERE_VOMITING', 'PROFUSE_VOMITING',
    'UNABLE_TO_EAT', 'CANNOT_EAT', 'NOT_EATING', 'SEVERE_DIARRHEA', 'DEHYDRATION',
    'URINARY_OBSTRUCTION', 'UNABLE_TO_URINATE', 'MARKED_WEAKNESS', 'SEVERE_WEAKNESS',
    'ACUTE_SEVERE_ILLNESS', 'RESPIRATORY_DISTRESS', 'ALTERED_MENTATION', 'ALTERED_CONSCIOUSNESS', 'UNABLE_TO_SWALLOW',
    'COLLAPSE', '持续频繁呕吐', '严重呕吐', '无法进食', '严重腹泻', '脱水', '尿闭', '明显虚弱', '急性重症',
}
BENIGN_STATUS = {'STABLE', 'NORMAL', 'NONE', 'HEALTHY', '无', '稳定', '正常'}


def _normal_id(value):
    return value.strip().upper() if isinstance(value, str) else None


def _flags(pet):
    """Accept explicit owner-observable flags; strings such as 'false' are invalid."""
    result, invalid = set(), []
    for field in ('symptoms', 'recent_abnormalities', 'current_abnormalities', 'abnormal_states', 'red_flags', 'current_status'):
        value = pet.get(field, [])
        if value is None:
            continue
        if isinstance(value, str):
            value = [value]
        if isinstance(value, dict):
            for key, enabled in value.items():
                if type(enabled) is not bool:
                    invalid.append(field + ':' + str(key))
                elif enabled:
                    result.add(_normal_id(key))
        elif isinstance(value, (list, tuple)):
            for item in value:
                flag = _normal_id(item)
                if flag:
                    result.add(flag)
                else:
                    invalid.append(field)
        else:
            invalid.append(field)
    for key, value in pet.items():
        flag = _normal_id(key)
        if flag in ACUTE_FLAGS:
            if type(value) is not bool:
                invalid.append(str(key))
            elif value:
                result.add(flag)
    return result - BENIGN_STATUS, invalid


def _source_rows(ids, store):
    sources = store.keyed('sources', 'source_id')
    return [{'source_id': sid, 'title': sources[sid]['title'], 'url': sources[sid]['URL'],
             'version': sources[sid]['version']} for sid in sorted(ids) if sid in sources]


def disease_advice(pet, store):
    """Return practical directions using diagnosed IDs, without lab-result inputs.

    ``pet['diseases']`` accepts IDs or {disease_id, confirmed?, status?} objects.
    String IDs mean the caller selected already diagnosed conditions. An explicit
    ``confirmed=False`` never becomes a diagnosis. Input is never mutated.
    """
    species = _normal_id(pet.get('species'))
    disease_rows = store.keyed('diseases', 'disease_id')
    by_name = {d['name_zh']: d['disease_id'] for d in disease_rows.values()}
    flags, malformed = _flags(pet)
    reasons, details, ids, source_ids = [], [], [], set()
    invalid = list(malformed)
    raw = pet.get('diseases', [])
    if not isinstance(raw, (list, tuple)):
        raw, invalid = [], invalid + ['DISEASES_MUST_BE_A_LIST']
    if species not in {'DOG', 'CAT'}:
        invalid.append('SPECIES_REQUIRED_DOG_OR_CAT')
    confirmed_allergens = pet.get('allergies', pet.get('confirmed_allergens', [])) or []
    if not isinstance(confirmed_allergens, (list, tuple)):
        confirmed_allergens = []
        invalid.append('ALLERGENS_MUST_BE_A_LIST')
    medications = pet.get('medications', []) or []
    if not isinstance(medications, (list, tuple)):
        medications = []
        invalid.append('MEDICATIONS_MUST_BE_A_LIST')
    for item in raw:
        obj = item if isinstance(item, dict) else {'disease_id': item}
        raw_id = obj.get('disease_id', obj.get('id'))
        did = _normal_id(raw_id)
        if did in SPECIES_ALIASES and species in {'DOG', 'CAT'}:
            did = SPECIES_ALIASES[did][species == 'CAT']
        did = ALIASES.get(did, by_name.get(did, did))
        confirmed = obj.get('confirmed', obj.get('diagnosed', True))
        if confirmed is not True:
            invalid.append('DIAGNOSIS_NOT_CONFIRMED:' + str(raw_id))
            continue
        if did not in disease_rows:
            invalid.append('UNKNOWN_DISEASE:' + str(raw_id))
            continue
        row = disease_rows[did]
        if row['species'] not in {'BOTH', species}:
            invalid.append('DISEASE_SPECIES_MISMATCH:' + did)
            continue
        if did in ids:
            continue
        ids.append(did)
        direction_source = row['source_id']
        if did in {'CKD', 'PLN'}:
            direction_source = 'IRIS_DOG2026' if species == 'DOG' else 'IRIS_CAT2026'
        source_ids.add(direction_source)
        illness = _normal_id(obj.get('status', obj.get('clinical_status', 'STABLE')))
        if illness in {'ACUTE', 'SEVERE', 'ACUTE_SEVERE', 'UNSTABLE'}:
            flags.add('ACUTE_SEVERE_ILLNESS')
        if did in DIRECTIONS:
            category, changes, direction = DIRECTIONS[did]
        elif did in ORAL:
            category, changes, direction = ('B', ['SOFT_TEXTURE', 'SMALL_SAFE_PIECES'],
                                           '使用柔软、易咀嚼的熟食；吞咽困难或无法进食时停止自动建议。')
        elif did in LIFESTYLE_ONLY:
            category, changes, direction = ('C', [], '保留物种与生命阶段的正常营养重点，提供观察与日常照护，不仅凭此诊断强行改动配方。')
        else:
            category, changes, direction = ('D', [], '当前未建立足够具体的该病家庭鲜食规则，保留通用照护并转专业复核。')
        if did in {'FOOD_ALLERGY', 'ADVERSE_FOOD_REACTION'} and not confirmed_allergens:
            category = 'D'
            reasons.append('ALLERGEN_IDENTITY_OR_EXISTING_TRIAL_PLAN_REQUIRED:' + did)
        if did == 'EPILEPSY' and any('bromide' in str(m).lower() or '溴' in str(m)
                                      for m in medications):
            category = 'D'
            reasons.append('BROMIDE_AND_DIET_CHLORIDE_CHANGE_REVIEW')
        if did == 'HYPERTHYROID_CAT' and pet.get('iodine_restricted_diet') is True:
            category = 'D'
            reasons.append('EXCLUSIVE_IODINE_RESTRICTED_DIET_MUST_NOT_BE_DILUTED')
        if category == 'D':
            reasons.append('DISEASE_REQUIRES_INDIVIDUAL_PLAN:' + did)
        details.append({'disease_id': did, 'name_zh': row['name_zh'],
                        'classification': CLASSIFICATIONS[category], 'food_direction': direction,
                        'adjustments': list(changes), 'source_id': direction_source,
                        'diagnosis_assumption': 'USER_SELECTED_ALREADY_DIAGNOSED',
                        'alias_used': raw_id if raw_id != did else None})
    conflicts = []
    for a, b in combinations(sorted(ids), 2):
        pair = {a, b}
        if ('CKD' in pair and pair & CARDIAC):
            conflicts.append({'diseases': [a, b], 'reason': 'RENAL_CARDIAC_NUTRIENT_AND_FLUID_PRIORITIES',
                              'source_ids': ['AAHA_THER2021', 'IRIS_DOG2026' if species == 'DOG' else 'IRIS_CAT2026'],
                              'policy': 'CONSERVATIVE_V1_REVIEW_NOT_CLAIM_OF_INEVITABLE_CONTRADICTION'})
        elif pair & {'DIABETES_DOG', 'DIABETES_CAT'} and pair & {'PANCREATITIS_DOG', 'PANCREATITIS_CAT'}:
            conflicts.append({'diseases': [a, b], 'reason': 'DIABETES_PANCREATITIS_COMORBIDITY_REVIEW',
                              'source_ids': ['AAHA_DM_DOG2026' if species == 'DOG' else 'AAHA_DM_CAT2026'],
                              'policy': 'CONSERVATIVE_V1_REVIEW_NOT_CLAIM_OF_INEVITABLE_CONTRADICTION'})
        elif pair <= STONE_TYPES:
            conflicts.append({'diseases': [a, b], 'reason': 'MULTIPLE_STONE_TARGETS_REQUIRE_REVIEW',
                              'source_ids': ['ACVIM_STONE2016'], 'policy': 'CONSERVATIVE_V1_REVIEW'})
        elif 'CKD' in pair and pair & {'DIABETES_DOG', 'DIABETES_CAT', 'PANCREATITIS_DOG', 'PANCREATITIS_CAT'}:
            conflicts.append({'diseases': [a, b], 'reason': 'RENAL_METABOLIC_COMORBIDITY_REVIEW',
                              'source_ids': ['AAHA_THER2021'], 'policy': 'CONSERVATIVE_V1_REVIEW'})
    for row in store.rows('disease_conflicts'):
        if row['kind'] == 'DISEASE_PAIR' and row['status'] == 'REVIEW_REQUIRED' and {row['disease_A'], row['disease_B']} <= set(ids):
            if not any(set(c['diseases']) == {row['disease_A'], row['disease_B']} for c in conflicts):
                conflicts.append({'diseases': [row['disease_A'], row['disease_B']], 'reason': row['conflict_id'],
                                  'source_ids': [row['source_id']], 'policy': 'EXISTING_VERIFIED_CONFLICT'})
    life_stage = str(pet.get('life_stage', '')).upper()
    if 'PANCREATITIS_DOG' in ids and ('GROWTH' in life_stage or 'PUPPY' in life_stage):
        conflicts.append({'diseases': ['PANCREATITIS_DOG'], 'reason': 'GROWTH_FAT_MINIMUM_VS_PANCREATITIS_LIMIT',
                          'source_ids': ['FEDIAF2025', 'MERCK_PANC'], 'policy': 'EXISTING_LIFE_STAGE_CONFLICT'})
    for conflict in conflicts:
        source_ids.update(conflict['source_ids'])
        reasons.append(conflict['reason'])
    reasons.extend(invalid)
    acute_codes = ACUTE_FLAGS | set(store.config.get('red_flags', []))
    nonurgent_codes = set(store.config.get('recognized_nonurgent_signs', []))
    acute = sorted(flags & acute_codes)
    unhandled_flags = sorted(flags - acute_codes - nonurgent_codes)
    if flags & nonurgent_codes:
        reasons.append('OBSERVE_AND_REASSESS:' + ','.join(sorted(flags & nonurgent_codes)))
    if unhandled_flags:
        reasons.append('UNASSESSED_CURRENT_ABNORMALITY:' + ','.join(unhandled_flags))
    if acute:
        status, classification = 'BLOCKED', CLASSIFICATIONS['D']
        reasons.extend('ACUTE_RED_FLAG:' + a for a in acute)
        source_ids.add('MERCK_TRIAGE2026')
    elif invalid or conflicts or unhandled_flags or any(d['classification'] == CLASSIFICATIONS['D'] for d in details):
        status, classification = 'PROFESSIONAL_REVIEW', CLASSIFICATIONS['D']
    else:
        status = 'PRACTICAL_CLEAR'
        classification = next((CLASSIFICATIONS[c] for c in ('A', 'B', 'C')
                               if any(d['classification'] == CLASSIFICATIONS[c] for d in details)), CLASSIFICATIONS['C'])

    care = {field: [] for field in CARE_FIELDS}
    field_map = {'stool_monitoring': 'stool_vomiting_monitoring', 'vomiting_monitoring': 'stool_vomiting_monitoring',
                 'red_flags': 'stop_self_adjustment', 'reassessment_note': 'stop_self_adjustment'}
    feeding = []
    for row in store.rows('disease_lifestyle'):
        if row['disease_id'] not in ids or row['status'] != 'SOURCE_VERIFIED' or not row['text_zh']:
            continue
        field = field_map.get(row['field'], row['field'])
        care_source = row['source_id']
        if row['disease_id'] in {'CKD', 'PLN'} and care_source in {'IRIS_DOG2026', 'IRIS_CAT2026'}:
            care_source = 'IRIS_DOG2026' if species == 'DOG' else 'IRIS_CAT2026'
        entry = {'text': row['text_zh'], 'source_ids': [care_source], 'disease_id': row['disease_id']}
        if row.get('additional_source_id'):
            entry['source_ids'].append(row['additional_source_id'])
        source_ids.update(entry['source_ids'])
        if field in care and not any(e['text'] == entry['text'] for e in care[field]):
            care[field].append(entry)
        elif field == 'feeding_frequency_notes':
            feeding.append(entry)
    for detail in details:
        entry = {'text': detail['food_direction'], 'source_ids': [detail['source_id']], 'disease_id': detail['disease_id']}
        care['foods_or_patterns_preferred'].insert(0, entry)
    if acute:
        care['stop_self_adjustment'].insert(0, {
            'text': '当前异常不适合继续自行调整鲜食。停止自动配方并及时就医；尿闭、呼吸困难、意识异常或明显虚弱应立即急诊。',
            'source_ids': ['MERCK_TRIAGE2026', 'PALECHO_SPEC'], 'disease_id': None,
            'scope': 'ACUTE_TRIAGE',
        })
        source_ids.update({'MERCK_TRIAGE2026', 'PALECHO_SPEC'})
    # A blank category means no established disease-specific restriction, not an
    # invitation to invent one. All eight categories remain explicit in the API.
    for field in care:
        if not care[field]:
            care[field].append({'text': '当前没有需额外增加的疾病专属限制；继续执行该物种的基础食品安全与营养方案。',
                                'source_ids': ['PALECHO_SPEC'], 'disease_id': None,
                                'scope': 'NO_ADDITIONAL_VERIFIED_DISEASE_RULE'})
            source_ids.add('PALECHO_SPEC')
    actions = sorted({a for d in details for a in d['adjustments']})
    return {
        'version': 'PRACTICAL_DISEASE_V1', 'classification': classification, 'status': status,
        'diseases': sorted(ids), 'disease_details': details,
        'food_direction': [d['food_direction'] for d in details], 'adjustments': actions,
        'recipe_constraint_requirements': actions, 'daily_care': care, 'daily_care_labels': CARE_LABELS.copy(),
        'feeding_notes': feeding, 'conflicts': conflicts, 'acute_red_flags': acute,
        'immediate_action': 'STOP_AUTOMATIC_RECIPE_AND_SEEK_VETERINARY_CARE' if acute else None,
        'sources': _source_rows(source_ids, store), 'reasons': sorted(set(reasons)),
        'professional_measurements_required_for_advice': [], 'numerical_prescription': False,
        'recipe_verified_for_disease': False,
        'scope': 'DIAGNOSIS_BASED_HOUSEHOLD_DIRECTIONS_RECIPE_ENGINE_MUST_CHECK_REQUIREMENTS',
        'advanced_validation_modified': False,
    }
