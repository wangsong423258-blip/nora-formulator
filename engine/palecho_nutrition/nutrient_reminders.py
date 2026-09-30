"""Recipe-scoped reminders, never a diagnosis or a supplement prescription."""
from dataclasses import replace
from .recipe_design_guidance import COVERED

REMINDER_NUTRIENTS = COVERED | {'epa_dha', 'ca_p_ratio'}
SCOPE_NOTE = '这是食物部分的家庭鲜食建议，不代表营养已经完整。长期作为主要饮食时，还需落实下列营养来源，并结合个体情况核对整体营养。'


def reminder_food_bounds(bounds):
    """Explicit food-advice scope, using the existing solver unchanged.

    Preserve every original upper bound (including Ca:P), all protein/amino
    acid/essential-fat food-core minima, and all disease safety constraints.
    Removed completion minima are audited separately and become reminders.
    This is not equivalent to a complete-diet audit pass.
    """
    return [replace(b, minimum=None, dependency={}) if b.nutrient in REMINDER_NUTRIENTS else b for b in bounds]


def nutrient_reminders(state):
    raw = state['raw']
    if not raw['daily_foods']:
        return []
    rows = state.get('food_reference_audit', {}).get('rows', [])
    pet = raw['pet']; species = pet['species']; diseases = set(raw['disease_advice']['diseases'])
    policy = state['target']['design_policy']
    def needs(names):
        return any(r['nutrient_id'] in names and r.get('minimum') is not None
                   and r['minimum_check'] == 'FAIL' for r in rows)
    result = []
    def add(nutrient, title, reason, order, importance='HIGH', disease_note='', key=None):
        result.append({'reminder_id': key or nutrient, 'nutrient_id': nutrient,
                       'title': title, 'reason': reason, 'importance': importance,
                       'applies_to': {'species': species, 'scope': 'THIS_FOOD_RECIPE'},
                       'long_term_note': '这是配方设计提醒，不是对宠物营养缺乏的诊断；长期使用需落实相应营养来源。',
                       'disease_note': disease_note, 'display_order': order})
    if needs({'calcium', 'ca_p', 'ca_p_ratio'}):
        add('CALCIUM', '注意钙和钙磷平衡',
            '肉类通常含磷较多、钙较少，长期家庭鲜食需要注意稳定的钙来源及整体钙磷平衡。', 10,
            disease_note='肾脏或泌尿疾病需同时兼顾磷和矿物质平衡，不自行大量添加骨、内脏或矿物来源。' if diseases & {'CKD','PLN','STRUVITE','CALCIUM_OXALATE','UROLITH_UNKNOWN'} else '')
    if needs(COVERED - {'calcium', 'ca_p', 'taurine'}):
        add('VITAMIN_MINERAL', '注意维生素和矿物质',
            '仅依靠常见肉、蛋、主食和蔬菜，长期可能难以稳定覆盖全部微量营养，需要关注适合'+('猫' if species=='CAT' else '犬')+'的完整营养补充来源。', 20,
            disease_note='有疾病时，完整营养来源也需与当前饮食限制相容。' if diseases else '')
    if species == 'CAT' and needs({'taurine'}):
        add('TAURINE', '注意牛磺酸的稳定来源',
            '猫对牛磺酸有明确营养需求，长期家庭鲜食应确保有稳定、可靠的牛磺酸来源。', 30)
    if needs({'epa_dha'}):
        add('OMEGA3_EPA_DHA', '可以关注 Omega-3',
            '这份食物组合还需要关注 Omega-3 脂肪酸的稳定来源。', 40,
            importance='HIGH' if 'GROWTH' in raw.get('life_stage','') or diseases else 'MEDIUM',
            disease_note='存在脂肪控制要求时，还需把额外油脂计入整体饮食。' if diseases & {'PANCREATITIS_DOG','HYPERLIPIDEMIA'} else '')
    if diseases & {'CKD', 'PLN'}:
        add('OTHER', '注意高磷食材', '食材选择已采用较低磷方向；不要在这份方案外额外叠加内脏或其他高磷食物。', 50,
            disease_note='肾脏疾病的具体饮食安排仍需结合个体状态。', key='RENAL_PHOSPHORUS')
    if diseases & {'PANCREATITIS_DOG', 'HYPERLIPIDEMIA'}:
        add('OTHER', '注意高脂食材', '这份方案已控制脂肪来源，避免额外加入肥肉、肉皮或大量油脂。', 60,
            disease_note='保持食物组成和份量稳定，观察进食耐受。', key='FAT_CONTROL')
    if policy.get('retain_cooking_water') and diseases:
        add('OTHER', '注意饮食含水量', '可按进食耐受保持食物湿润，日常提供清洁饮水，不额外加入未核算的浓肉汤。', 70,
            importance='MEDIUM', disease_note='已有饮水管理要求时遵循原有安排。', key='HYDRATION')
    stone = diseases & {'STRUVITE','CALCIUM_OXALATE','URATE','CYSTINE','UROLITH_UNKNOWN'}
    if stone:
        add('OTHER', '保留适合结石类型的饮食安排',
            '结石类型尚不清楚，方案未推定酸化或碱化方向。' if 'UROLITH_UNKNOWN' in stone else '这份方案已结合已知结石类型选择食材，不自行改变矿物质或酸碱方向。',
            80, disease_note='不把家庭鲜食建议当作溶石方案。', key='URINARY_DIET')
    return sorted(result, key=lambda item: (item['display_order'], item['reminder_id']))
