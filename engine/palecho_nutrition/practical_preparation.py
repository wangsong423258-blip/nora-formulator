"""Household preparation downstream of the V1 recommendation, not clinical release.

The caller supplies the *rechecked* daily food amounts and exact supplement doses.
This module never solves, rounds, substitutes, certifies nutritional adequacy, or
turns a failed complete diet into an auxiliary feeding plan.
"""
from copy import deepcopy
from decimal import Decimal
import math


SOURCES = {
    'PRACTICAL_FOOD_TEMP': 'https://www.foodsafety.gov/food-safety-charts/safe-minimum-internal-temperatures',
    'PRACTICAL_COLD_STORAGE': 'https://www.foodsafety.gov/food-safety-charts/cold-food-storage-charts',
    'PRACTICAL_FDA_STORAGE': 'https://www.fda.gov/consumers/consumer-updates/are-you-storing-food-safely',
    'PRACTICAL_FDA_HANDLING': 'https://www.fda.gov/animal-veterinary/animal-health-literacy/tips-safe-handling-pet-food-and-treats',
    'PRACTICAL_USDA_LEFTOVERS': 'https://www.fsis.usda.gov/food-safety/safe-food-handling-and-preparation/food-safety-basics/leftovers-and-food-safety',
    'PRACTICAL_AAHA_TRANSITION': 'https://www.aaha.org/resources/2021-aaha-nutrition-and-weight-management-guidelines/feeding-plans-for-healthy-appropriate-weight-cats-and-dogs/',
    'PRACTICAL_WSAVA_FEEDING': 'https://wsava.org/wp-content/uploads/2020/01/Frequently-Asked-Questions-and-Myths.pdf',
}

KINDS = {
    'FDC_168231': 'MEAT', 'FDC_168250': 'MEAT', 'FDC_170633': 'MEAT',
    'FDC_171061': 'POULTRY', 'FDC_171477': 'POULTRY', 'FDC_171478': 'POULTRY',
    'FDC_172389': 'POULTRY', 'FDC_172411': 'POULTRY',
    'FDC_171956': 'FISH', 'FDC_174185': 'FISH', 'FDC_175168': 'FISH', 'FDC_175177': 'FISH',
    'FDC_173424': 'EGG', 'FDC_169757': 'RICE', 'FDC_173905': 'OAT',
    'FDC_171411': 'OIL', 'FDC_172336': 'OIL',
    'FDC_168449': 'VEGETABLE', 'FDC_168484': 'VEGETABLE', 'FDC_169292': 'VEGETABLE',
    'FDC_169967': 'VEGETABLE', 'FDC_169976': 'VEGETABLE', 'FDC_170394': 'VEGETABLE',
    'FDC_170440': 'VEGETABLE',
}
METHODS = {
    'ROASTED': '按烤熟数据，用烤箱烤制；不自行改成水煮或蒸制。烹调时间依食材厚度和设备而变，以中心温度核查。',
    'DRY_HEAT': '按干热数据烤熟，不改成水煮；不另加未计入配方的油脂。',
    'STEWED': '加清水炖熟。称量熟肉可食部分；汤、浮油不计入该肉类熟重，不自行加入配方。',
    'BRAISED': '按焖炖熟制状态操作；不添加未计入的油或酱汁，称熟肉可食部分。',
    'SIMMERED': '清水小火煮熟，称熟制后的可食部分；不把汤重算成食材重量。',
    'BOILED': '清水煮软煮熟，按该食材指定的去皮及可食部分称熟重。',
    'BOILED_DRAINED': '清水煮软后沥去游离水，无盐；称沥水后的熟重。',
    'HARD_BOILED': '带壳水煮至蛋白、蛋黄完全凝固；去壳后称重，不用溏心蛋替代。',
    'COOKED': '米饭或燕麦加清水煮熟煮软，无盐；称最终熟制食品重量，不称干米或干燕麦重量。',
    'AS_SOLD': '这是配方中的食用油，按出售状态称量；混合时加入，不把油当作熟肉称重。',
}


def _positive_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _fail(status, reasons, recommendation=None):
    return {'preparation_status': status, 'reasons': reasons, 'shopping_list': [],
            'recipe_status': (recommendation or {}).get('recipe_status'),
            'advanced_validation_claim': False, 'complete_balanced_claim': False}


def _daily_g(row):
    for key in ('grams_cooked', 'gram_cooked', 'daily_grams', 'grams'):
        if key in row:
            return row[key]
    return None


def _amount(value, multiplier):
    """Avoid binary artefacts without rounding a prescribed dose."""
    return float(Decimal(str(value)) * Decimal(str(multiplier)))


def _cooking(food):
    iid = food['ingredient_id']
    state = food['food_state']
    kind = KINDS[iid]
    result = {'cooking_method': state, 'instruction': METHODS[state],
              'cooking_time_minutes': None,
              'time_note': '不预设统一分钟数；用熟制状态及食品温度计确认。',
              'minimum_internal_temperature_c': None, 'rest_minutes': None,
              'temperature_source_id': None,
              'nutrition_state_source_id': food.get('source_id')}
    if kind in {'POULTRY', 'MEAT', 'FISH'}:
        result['minimum_internal_temperature_c'] = 74 if kind == 'POULTRY' else 63
        result['temperature_source_id'] = 'PRACTICAL_FOOD_TEMP'
        result['rest_minutes'] = 3 if kind == 'MEAT' else None
        result['cutting'] = '按记录去皮、去骨；先以整块熟制，达到中心温度和静置要求后，用清洁刀具切成适合进食的小块或剁碎。'
        if kind == 'MEAT':
            result['ground_meat_caution'] = '本方案按整块肉熟制后切碎；若改用生绞肉，需至少71°C且重新匹配食材数据，不沿用整块肉数据。'
        if kind == 'FISH':
            result['cutting'] = '去鳞、内脏、骨及鱼刺，按原食品描述处理鱼皮；熟后再逐块检查细刺并分成适口小块。'
        if iid == 'FDC_171061':
            result['cutting'] = '使用新鲜鸡肝的可食部分，清水小火煮熟至中心至少74°C；熟后用清洁刀具切碎，称取规定熟肝重量，不用生肝重量或汤重替代。'
            result['portion_note'] = '仅使用推荐层已核算的小份量，不额外添肝；维生素A及其他营养约束在推荐层检查。'
    elif kind == 'EGG':
        result['cutting'] = '完全煮熟后去壳，称可食蛋重并切碎；蛋壳不计入配方。'
        result['temperature_source_id'] = 'PRACTICAL_FOOD_TEMP'
    elif kind == 'VEGETABLE':
        result['cutting'] = '洗净，按食品名称去皮或保留皮；去掉不食用部分，切小块后煮软，必要时压碎。'
    else:
        result['cutting'] = '按最终可食状态称量。'
    return result


def _purchase(food, row, cooked_batch_g):
    """A number without a matching yield source is not a purchasing conversion."""
    spec = row.get('purchase_yield') or {}
    if not isinstance(spec, dict):
        spec = {}
    if not spec and food.get('raw_purchase_yield_source_id'):
        spec = {'cooked_g_per_raw_edible_g': food.get('raw_purchase_yield'),
                'source_id': food['raw_purchase_yield_source_id'], 'food_state': food['food_state']}
    factor = spec.get('cooked_g_per_raw_edible_g')
    matched = (isinstance(spec, dict) and _positive_number(factor) and spec.get('source_id')
               and spec.get('food_state') == food['food_state'])
    edible = spec.get('edible_fraction')
    edible_ok = (_positive_number(edible) and edible <= 1 and spec.get('edible_fraction_source_id'))
    raw_g = cooked_batch_g / factor if matched else None
    gross = raw_g / edible if raw_g is not None and edible_ok else None
    if food['food_state'] == 'AS_SOLD':
        return {'raw_edible_purchase_g': None, 'gross_purchase_g': cooked_batch_g,
                'purchase_basis': 'AS_SOLD', 'yield_source_id': food.get('source_id'),
                'purchase_note': '按同一食用油的成品重量采购。'}
    return {'raw_edible_purchase_g': raw_g, 'gross_purchase_g': gross,
            'purchase_basis': 'SOURCE_MATCHED_YIELD' if matched else 'COOKED_TARGET_ONLY',
            'yield_source_id': spec.get('source_id') if matched else None,
            'purchase_note': ('生重按同身份、同熟制状态的产率估算；最终仍以实际熟重分装。' if matched else
                              '购入生重待实际出成测量；先以本行熟重目标备料，熟后称量，多余食物另存，不加入本日配方。')}


def _transition(species, supplemental):
    if supplemental:
        return {'scope': 'AUXILIARY_FOOD_ONLY', 'source_ids': ['PRACTICAL_AAHA_TRANSITION'],
                'instructions': ['从少量辅助食物逐步增至本方案规定份量，保留原完整主食。',
                                 '辅助食物与其他零食合计通常不超过全天热量的10%；不能逐步增加到替代全部主食。',
                                 '疾病或处方饮食应遵守既有兽医喂食安排；不自行叠加维矿。']}
    return {'scope': 'COMPLETE_PRACTICAL_RECOMMENDATION',
            'source_ids': ['PRACTICAL_AAHA_TRANSITION', 'PRACTICAL_WSAVA_FEEDING'],
            'instructions': ['健康宠物通常用4–7天逐步换食；按耐受情况延长，不强迫进食。',
                             '按热量比例逐步增加已配好的新日粮、减少旧日粮；补剂随新日粮份额同步，不能半份新食物配全天补剂。',
                             ('猫可将新旧食物分碗提供，转换可能需要更长；每天维持足够进食。' if species == 'CAT' else
                              '在保持全天总热量的前提下逐步换食，观察食欲和粪便。'),
                             '若明显呕吐、持续腹泻、不能进食或虚弱，停止自行调整并就医。疾病饮食遵循既有兽医安排。']}


def prepare_practical(recommendation, store, days=3, meals_per_day=2):
    """Return a household protocol after explicit confirmation of V1 quantities.

    ``daily_foods`` carries ingredient_id and grams_cooked (gram_cooked is an
    alias). ``supplements`` carries supplement_id, daily_amount, unit,
    product_name, source_id, practical_usable=True, and optional sourced addition
    instructions. Store needs keyed('ingredients', 'ingredient_id') only.
    Missing yield, laboratory analyses, COAs and expert signatures are not gates.
    """
    if not isinstance(recommendation, dict):
        return _fail('INVALID_INPUT', ['RECOMMENDATION_OBJECT_REQUIRED'])
    if type(days) is not int or not 1 <= days <= 14 or type(meals_per_day) is not int or not 1 <= meals_per_day <= 12:
        return _fail('INVALID_INPUT', ['BATCH_DAYS_1_TO_14_AND_MEALS_1_TO_12_REQUIRED'], recommendation)
    status = recommendation.get('recipe_status', recommendation.get('status'))
    if status not in {'RECOMMENDED', 'RECOMMENDED_WITH_SUPPLEMENTS', 'LIMITED_DATA'}:
        return _fail('NO_PREPARABLE_RECOMMENDATION', ['RECOMMENDATION_NOT_ELIGIBLE'], recommendation)
    supplemental = recommendation.get('use_case') in {'TOPPER', 'SUPPLEMENTAL'}
    if status == 'LIMITED_DATA' and not supplemental:
        return _fail('NO_PREPARABLE_RECOMMENDATION', ['LIMITED_DATA_REQUIRES_EXPLICIT_AUXILIARY_USE'], recommendation)
    if recommendation.get('confirmed') is not True:
        return _fail('AWAITING_CONFIRMATION', ['CONFIRM_RECOMMENDED_AMOUNTS_FIRST'], recommendation)
    if recommendation.get('practical_check_passed') is False:
        return _fail('NO_PREPARABLE_RECOMMENDATION', ['PRACTICAL_NUTRITION_CHECK_FAILED'], recommendation)
    rows = recommendation.get('daily_foods')
    supplements = recommendation.get('supplements', [])
    if not isinstance(rows, list) or not rows or not isinstance(supplements, list):
        return _fail('INVALID_INPUT', ['DAILY_FOODS_AND_SUPPLEMENT_LIST_REQUIRED'], recommendation)
    if status == 'RECOMMENDED_WITH_SUPPLEMENTS' and not supplements:
        return _fail('INVALID_INPUT', ['PRESCRIBED_SUPPLEMENT_DOSES_MISSING'], recommendation)
    foods = store.keyed('ingredients', 'ingredient_id')
    shopping = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return _fail('INVALID_INPUT', ['FOOD_ROW_MUST_BE_OBJECT'], recommendation)
        iid = row.get('ingredient_id')
        grams = _daily_g(row)
        if iid not in foods or iid in seen or not _positive_number(grams):
            return _fail('INVALID_INPUT', ['FOOD_ID_OR_DAILY_AMOUNT_INVALID'], recommendation)
        seen.add(iid)
        food = foods[iid]
        if iid not in KINDS or food.get('food_state') not in METHODS:
            return _fail('NO_PREPARABLE_RECOMMENDATION', [iid + ':COOKED_IDENTITY_OR_METHOD_UNSUPPORTED'], recommendation)
        if row.get('food_state', food['food_state']) != food['food_state'] or row.get('cooking_method', food['food_state']) != food['food_state']:
            return _fail('NO_PREPARABLE_RECOMMENDATION', [iid + ':DATA_METHOD_MISMATCH'], recommendation)
        if row.get('display_grams') is not None and row['display_grams'] != grams:
            return _fail('NEEDS_NUTRITION_RECHECK', [iid + ':ROUNDING_MUST_BE_RECHECKED_UPSTREAM'], recommendation)
        batch_g = _amount(grams, days)
        shopping.append({'ingredient_id': iid, 'name_zh': food['name_zh'],
                         'daily_consumed_g': grams, 'per_meal_food_g': grams / meals_per_day,
                         'batch_consumed_g': batch_g, 'weighing_state': food['food_state'],
                         'weighing_basis': 'AS_SOLD' if food['food_state'] == 'AS_SOLD' else 'COOKED_WEIGHT',
                         'edible_portion': food.get('edible_portion'),
                         'source_id': food.get('source_id'), 'cooking': _cooking(food),
                         **_purchase(food, row, batch_g)})
    supp_output = []
    supp_seen = set()
    for supplement in supplements:
        if not isinstance(supplement, dict):
            return _fail('INVALID_INPUT', ['SUPPLEMENT_ROW_MUST_BE_OBJECT'], recommendation)
        sid = supplement.get('supplement_id')
        dose = supplement.get('daily_amount')
        unit = supplement.get('unit')
        if (not sid or sid in supp_seen or supplement.get('practical_usable') is not True
                or not _positive_number(dose) or unit not in {'g', 'mg', 'mL', 'ml', 'capsule', 'tablet'}
                or not supplement.get('product_name') or not supplement.get('source_id')
                or supplement.get('evidence_acceptance') == 'REJECTED'):
            return _fail('NO_PREPARABLE_RECOMMENDATION', ['SUPPLEMENT_IDENTITY_SPEC_OR_EXACT_DOSE_MISSING'], recommendation)
        supp_seen.add(sid)
        if unit in {'capsule', 'tablet'} and not float(dose).is_integer() and not supplement.get('division_allowed'):
            return _fail('NO_PREPARABLE_RECOMMENDATION', [sid + ':FRACTIONAL_UNIT_NOT_SUPPORTED_BY_LABEL'], recommendation)
        official_instruction = supplement.get('addition_instruction')
        official_source = supplement.get('addition_source_id')
        product_specific_instruction = bool(official_source and official_source != 'PRACTICAL_PROCESS_POLICY')
        if official_instruction and not official_source:
            return _fail('INVALID_INPUT', [sid + ':ADDITION_INSTRUCTION_SOURCE_MISSING'], recommendation)
        # Only a explicitly sourced product instruction may authorize cooking,
        # freezing or reheating the supplement. Default is a process precaution.
        instruction = official_instruction or '按当天明确剂量单独称取，食物复热后冷至可进食时，临喂前充分拌匀；不随整批烹煮或冷冻。'
        per_meal = dose / meals_per_day
        divisible = unit not in {'capsule', 'tablet'} or per_meal.is_integer() or supplement.get('division_allowed')
        schedule = [per_meal] * meals_per_day if divisible else None
        scale_g = supplement.get('required_scale_resolution_g')
        if scale_g is not None and unit in {'g', 'mg'}:
            if not _positive_number(scale_g):
                return _fail('INVALID_INPUT', [sid + ':INVALID_SCALE_RESOLUTION'], recommendation)
            increment = Decimal(str(scale_g)) * (1000 if unit == 'mg' else 1)
            count = Decimal(str(dose)) / increment
            if count != count.to_integral_value():
                return _fail('NEEDS_NUTRITION_RECHECK', [sid + ':DAILY_DOSE_NOT_MEASURABLE_AT_REQUIRED_SCALE_RESOLUTION'], recommendation)
            base_count, extra_count = divmod(int(count), meals_per_day)
            schedule = [float(increment * (base_count + (m < extra_count))) for m in range(meals_per_day)]
            per_meal = schedule[0] if len(set(schedule)) == 1 else None
        if supplement.get('required_measurement_increment') is not None:
            increment=Decimal(str(supplement['required_measurement_increment']))
            if increment<=0:return _fail('INVALID_INPUT',[sid+':INVALID_MEASUREMENT_INCREMENT'],recommendation)
            count=Decimal(str(dose))/increment
            if count!=count.to_integral_value():return _fail('NEEDS_NUTRITION_RECHECK',[sid+':DOSE_NOT_EXECUTABLE'],recommendation)
            base_count,extra_count=divmod(int(count),meals_per_day)
            schedule=[float(increment*(base_count+(m<extra_count))) for m in range(meals_per_day)]
            per_meal=schedule[0] if len(set(schedule))==1 else None
            divisible=True
        supp_output.append({'supplement_id': sid, 'product_name': supplement['product_name'],
                            'daily_amount': dose, 'batch_total_to_have': _amount(dose, days),
                            'per_meal_amount': per_meal if divisible else None,
                            'per_meal_schedule': schedule,
                            'required_scale_resolution_g': scale_g,
                            'unit': unit, 'source_id': supplement['source_id'],
                            'addition_instruction': instruction,
                            'addition_source_id': official_source or 'PRACTICAL_PROCESS_POLICY',
                            'thermal_stability': ('FOLLOW_PRODUCT_INSTRUCTION_ONLY' if product_specific_instruction else 'NOT_ESTABLISHED'),
                            'label_check': None if product_specific_instruction else '未确立产品耐热、冷冻稳定性；默认临喂前加入是保守制作安排，不是稳定性证明。',
                            'division_note': ('按每餐用量表称取；若每日量不能完全均分，按秤分辨率分配，全天总剂量不变。不得用“少许”或无刻度家用勺。' if divisible else
                                              '不可自动均分该整粒剂量；按标签的给药餐次给足每日量，不切分未允许拆分的片/胶囊。')})
    total = sum(item['daily_consumed_g'] for item in shopping)
    mass_supplement = sum(item['daily_amount'] * (0.001 if item['unit'] == 'mg' else 1)
                          for item in supp_output if item['unit'] in {'g', 'mg'})
    unknown_mass = any(item['unit'] not in {'g', 'mg'} for item in supp_output)
    egg_ids = [item['ingredient_id'] for item in shopping if KINDS[item['ingredient_id']] == 'EGG']
    pet = recommendation.get('pet') or {}
    species = str(recommendation.get('species') or pet.get('species') or '').upper()
    egg_g = sum(item['daily_consumed_g'] for item in shopping if item['ingredient_id'] in egg_ids)
    result = {'preparation_status': 'READY_AUXILIARY' if supplemental else 'READY',
              'recipe_status': status, 'use_case': recommendation.get('use_case'),
              'complete_balanced_claim': False, 'advanced_validation_claim': False,
              'scope_note': ('这是辅助食物制作单，不能作为完整主食。' if supplemental else
                             '这是已确认V1建议的家庭制作单；不新增实验室或商业全价粮验证声明。'),
              'shopping_list': shopping, 'supplements': supp_output,
              'batch_days': days, 'meals_per_day': meals_per_day,
              'daily_food_total_g': total, 'per_meal_food_g': total / meals_per_day,
              'batch_food_total_g': _amount(total, days),
              'daily_supplement_mass_g': None if unknown_mass else mass_supplement,
              'daily_total_with_supplements_g': None if unknown_mass else total + mass_supplement,
              'mass_note': '食物克数与补剂单独列示；毫升或整粒补剂没有可靠质量换算时，不伪造合计克数。',
              'mixing_order': ['洗手至少20秒；清洗器具，生熟分开。',
                               '各食材按自身记录的熟制方法处理，去除骨、刺、蛋壳等，称取指定熟重。',
                               '混合已称重的熟食和配方食用油，均匀拌合；不添加未计入的盐、调味料、汤或额外油脂。',
                               '分入浅容器及时冷却；无需在室温放到完全凉透才冷藏。',
                               '按每餐分装、标注制作日期及份量；补剂按各产品说明单独处理，默认临喂前加入。'],
              'portions': {'food_packages': days * meals_per_day,
                           'food_g_per_package': total / meals_per_day,
                           'frozen_base_food_g_per_package': (total - egg_g) / meals_per_day if days > 3 else None,
                           'egg_g_to_add_per_meal': egg_g / meals_per_day if days > 3 and egg_ids else None,
                           'refrigerated_days': min(days, 3),
                           'frozen_days': max(days - 3, 0),
                           'freeze_instruction': '超过3天才食用的部分在制作当天冷却后立即冷冻，不能先冷藏3天再入冻。',
                           'separate_hard_boiled_eggs': egg_ids if days > 3 else [],
                           'egg_instruction': ('硬煮蛋不安排冷冻；与其他食材分开冷藏，后续份量每隔不超过3天重新煮制，喂前按原量补齐。' if days > 3 and egg_ids else None)},
              'storage': {'refrigerator_max_c': 4, 'freezer_max_c': -18,
                          'ambient_max_hours': 2, 'hot_ambient_threshold_c': 32,
                          'hot_ambient_max_hours': 1,
                          'refrigerator_planning_days': 3,
                          'batch_planning_limit_days': 14,
                          'planning_basis': '3天取官方熟食3–4天范围的保守端；14天是家庭小批制作计划上限，不是测得保质期。',
                          'thawing': '提前在≤4°C冰箱内解冻，不在室温台面解冻；只取本餐食物。',
                          'reheating': '需复热时将不含补剂的食物中心加热至74°C，再冷至可安全进食；按产品说明加入本餐补剂，不给烫食。',
                          'discard': '超过室温时限、温控不明或变质的食品丢弃；每次喂后清洁食碗，口水接触的剩余食物不倒回储存盒。',
                          'source_ids': ['PRACTICAL_COLD_STORAGE', 'PRACTICAL_FDA_STORAGE', 'PRACTICAL_FDA_HANDLING', 'PRACTICAL_USDA_LEFTOVERS']},
              'transition': _transition(species, supplemental),
              'feeding_notes': ['普通食物允许家庭称量误差，但不自行删掉食材、换品种或扩大份量区间；改变配比需重新计算。',
                                '每日清洁饮水常备。观察食欲、体重趋势、呕吐及粪便；必要时重新评估建议。',
                                '每日餐数是分装参数；幼龄、疾病或已有兽医餐次安排时，以推荐层确定的合适餐次为准。'],
              'sources': deepcopy(SOURCES)}
    if days > 3 and egg_ids:
        for item in result['shopping_list']:
            if item['ingredient_id'] in egg_ids:
                item['first_cook_batch_g'] = _amount(item['daily_consumed_g'], 3)
                item['repeat_cook_every_days'] = 3
    return result
