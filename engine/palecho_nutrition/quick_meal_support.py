"""Consumer nutrition reminders: no product dose or meal-completion obligation."""
from copy import deepcopy
from .scientific_supplements_v17 import evidence_matrix, applies, TITLES
from .freshfood_contract import ContractError

SCOPE_NOTE = '供偶尔制作这一餐或当天使用，不是长期完整全价日粮。鲜食热量应替代相应主粮份额，不在原有日量外叠加。'


def nutrition_support(state, store):
    if not state['raw']['daily_foods']:
        return [], [], [], []
    try:
        document = evidence_matrix(store)
    except ContractError:
        # Bad evidence cannot authorize advice; it is not a food-safety failure.
        return [], [], [], ['营养建议依据暂未通过校验，本次不输出补充成分建议。']
    pet = state['raw']['pet']
    stage = state['raw']['life_stage']
    diseases = set(state['raw']['disease_advice']['diseases'])
    facts = state['facts']
    context = pet.get('_clinical_nutrition_v17', {})
    conditions = diseases | ({'COGNITIVE_DYSFUNCTION'} if context.get('cognitive_dysfunction_report') else set())
    rows = {r['evidence_id']: r for r in document['rows']}
    notes, health, disease = [], [], []

    def make(row, purpose, why):
        recommendation = {
            'title': TITLES.get(row['supplement'], '评估相关营养支持'),
            'active_nutrient': row['active_nutrient'], 'purpose': purpose,
            'evidence_goal': row['goal'], 'why_recommended': why,
            'physiologic_role': row['physiologic_role'],
            'evidence_level': row['evidence_level'], 'evidence_source_ids': row['source'],
            'evidence_sources': [deepcopy(document['sources'][sid]) for sid in row['source']],
            'target_amount': None, 'target_min': None, 'target_max': None,
            'target_basis': 'QUICK_MEAL_INFORMATION_NOT_A_SUPPLEMENT_DOSE',
            'label_should_show': (['EPA、DHA各自每份含量，不只看鱼油总重量'] if row['active_nutrient']=='EPA_DHA'
                                 else ['元素钙每份含量，不是碳酸钙总重量'] if row['active_nutrient']=='ELEMENTAL_CALCIUM'
                                 else ['有效成分名称、每份含量、适用物种和全部载体']),
            'conditional_requirements': deepcopy(row['conditional_requirements']),
            'contraindications': deepcopy(row['contraindications']),
            'clinical_outcome_supported': row['clinical_outcome_supported'],
            'recipe_context': {'species':pet['species'],'life_stage':stage,'bcs':pet['bcs'],
                'diseases':sorted(diseases),'ca_p_ratio':facts.get('ca_p_ratio'),
                'known_nutrient_amounts':{n:facts.get(n,{}).get('amount') for n in ['calcium','phosphorus','epa','dha','taurine','fat']},
                'unknowns_are_not_deficiencies':True},
            'safety_status': 'CONDITIONAL', 'interaction_status': 'UNKNOWN',
            'required_for_this_meal': False, 'automatic_dose_allowed': False,
            'user_message': '', 'indications': [],
        }
        if '_ingredient_selection_v19' not in pet:recommendation.pop('recipe_context')
        return recommendation

    ids = ['COMP_MICRO']
    if facts['ca_p_ratio'] is None or facts['ca_p_ratio'] < 1:
        ids.insert(0, 'COMP_CA')
    if pet['species']=='CAT':
        ids.append('COMP_TAU')
    if 'GROWTH' in stage:
        ids.append('COMP_OMEGA')
    for rid in ids:
        row = rows[rid]
        rec = make(row, 'NUTRIENT_REMINDER', '这份常见食材组合未承诺长期营养完整；如果以后经常自制，需要稳定落实相应营养来源。')
        rec['conditional_requirements'] = ['FREQUENT_HOMEMADE_FEEDING_REQUIRES_WHOLE_DIET_PLAN']
        rec['user_message'] = '偶尔这一餐不要求逐项加齐；如果以后经常这样制作，请关注：' + row['physiologic_role']
        if rid=='COMP_TAU':
            rec['why_recommended'] = '猫需要稳定的牛磺酸来源，当前家用熟制食物的贡献不能可靠确定。'
        if 'COPPER_HEPATOPATHY' in diseases and rid=='COMP_MICRO':
            rec['user_message'] += '当前限铜，不自行添加含铜维矿产品。'
        if diseases & {'CKD','PLN'} and rid=='COMP_CA':
            rec['user_message'] += '肾病不要自行加钙或磷，矿物补充另按临床安排。'
        notes.append(rec)

    for row in document['rows']:
        if row['goal'] not in {'HEALTH_RISK_SUPPORT','DISEASE_SUPPORT'}:
            continue
        if not (set(row['condition']) & conditions) or row['evidence_level'] not in {'EVIDENCE_A','EVIDENCE_B'}:
            continue
        if not applies(row, pet, stage):
            continue
        matching = sorted(set(row['condition']) & conditions)
        names = store.keyed('diseases','disease_id')
        labels = [names[d]['name_zh'] if d in names else '已记录状态' for d in matching]
        rec = make(row, 'DISEASE_SUPPORT' if row['goal']=='DISEASE_SUPPORT' else 'HEALTH_SUPPORT',
                   '当前记录涉及'+'、'.join(labels)+'；可在整体管理中评估此项营养支持，先核对使用条件。')
        if row['evidence_id']=='MMVD_OMEGA' and context.get('mmvd_stage')!='C':
            rec['conditional_requirements'].append('MMVD_STAGE_C_NOT_CONFIRMED')
        if row['active_nutrient']=='EPA_DHA' and diseases & {'PANCREATITIS_DOG','PANCREATITIS_CAT','HYPERLIPIDEMIA'}:
            rec['conditional_requirements'].append('WHOLE_RECIPE_FAT_AND_ENERGY_RECALCULATION')
        if row['active_nutrient']=='EPA_DHA' and pet['bcs']>=6:
            rec['conditional_requirements'].append('INCLUDE_SUPPLEMENT_FAT_IN_TOTAL_ENERGY_NO_EXTRA_CALORIES')
        rec['user_message'] = '可作为疾病整体管理中的营养支持。'+row['physiologic_role']+' 暂无可靠条件确定具体剂量，不自行替代处方饮食或药物。'
        destination = disease if rec['purpose']=='DISEASE_SUPPORT' else health
        existing = next((r for r in destination if r['active_nutrient']==rec['active_nutrient']), None)
        if existing:
            existing['indications'].append({'conditions':matching,'evidence_level':rec['evidence_level'],'evidence_source_ids':rec['evidence_source_ids']})
            existing['conditional_requirements'] = sorted(set(existing['conditional_requirements']+rec['conditional_requirements']))
        else:
            rec['indications'] = [{'conditions':matching,'evidence_level':rec['evidence_level'],'evidence_source_ids':rec['evidence_source_ids']}]
            destination.append(rec)
    # One active ingredient can have both a future nutrition reminder and a
    # clinical indication. Present it once, with the clinical conditions intact.
    supported = {r['active_nutrient'] for r in health+disease}
    notes = [r for r in notes if r['active_nutrient'] not in supported]
    return notes, health, disease, []
