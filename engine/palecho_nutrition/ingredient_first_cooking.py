"""Cooking instructions follow the nutrient record's final edible state."""
from copy import deepcopy
from collections import Counter
from .practical_preparation import METHODS

def cooking_plan(components,m,repo,notes,health,disease):
    rules=repo.registry['rules'];temps=rules['COOKING_TEMPERATURE']['value'];storage=rules['COOKING_STORAGE']['value']
    methods={**METHODS,'MOIST_HEAT':'用清水充分湿热熟制，不额外加盐、油或酱料；只称熟制可食肉，不计汤重。',
      'COOKED':'按所列谷物或其他食品的具体身份用清水煮熟，不加盐或油，称最终可食熟重。',
      'BAKED':'不额外加油，按烘烤熟制数据制作，称最终可食熟重。',
      'PREPARED_FROZEN_EDAMAME':'按未调味冷冻毛豆包装说明充分熟制，去荚称可食豆重。'}
    total=sum(c['amount_g'] for c in components);meals=m['meal_count'];whole,remainder=divmod(int(total),meals)
    portions=[float(whole+(j<remainder)) for j in range(meals)]
    shopping=[];prep=[];steps=[]
    for c in components:
        f=repo.records[c['ingredient_id']];kind=f['preparation_kind'];tags=f['allergen_tags'];state=f['food_state']
        temperature=temps.get('RABBIT' if 'RABBIT' in tags else kind)
        rest=temps['rest_minutes_whole_meat'] if kind=='MEAT' and 'RABBIT' not in tags else None
        instruction=methods[state]
        if f['category']=='ORGAN' and kind!='POULTRY':temperature=temps['ORGAN']
        if temperature is not None:instruction+=f' 中心至少{temperature:g}°C；用食品温度计确认。'
        if rest:instruction+=f' 整块熟制后静置{rest:g}分钟，再切碎。'
        if f['category']=='EGG':instruction+=' 蛋黄和蛋白均须完全凝固。'
        if 'SHELLFISH' in tags:instruction+=' 只用可靠来源；贝壳煮后未打开的丢弃。去除壳和不可食部分。'
        shopping.append({k:c[k] for k in ['ingredient_id','display_name','amount_g','weight_basis','food_state']}|{'canonical_name':f['canonical_name'],'raw_purchase_amount_g':None,'raw_cooked_yield_unknown':True})
        prep.append({'ingredient_id':c['ingredient_id'],'instruction':'严格按食品身份处理皮、骨、刺、壳和沥水状态；充分熟制后切小块。不要以另一品种或烹调方法代替。',
                     'food_identity':{k:f[k] for k in ['canonical_name','skin','bone','drained','edible_portion']}})
        steps.append({'ingredient_ids':[c['ingredient_id']],'food_state':state,'instruction':instruction,'minimum_internal_temperature_c':temperature,
                      'rest_minutes':rest,'source_ids':rules['COOKING_TEMPERATURE']['source_ids'] if temperature else ['FOOD_SAFETY_TEMPERATURE']})
    hydrate=['已有饮水限制时沿用临床安排，不自行灌水。'] if 'CHF' in m['diseases'] else ['可以在按指定状态称重后另加清水，额外水不计入食材熟重。'] if set(m['diseases'])&{'CKD','PLN','FIC','CONSTIPATION'} else []
    return {'status':'READY','shopping_list':shopping,'preparation':prep,'cooking_steps':steps,
      'weighing_note':'所列克数为对应状态的最终可食重量；不推算未知生熟转换。食材、类别和克数改变时须整餐重算。',
      'mixing':{'ingredient_ids':[c['ingredient_id'] for c in components],'instruction':'将所列食材充分熟制、准确称量后混匀。无葱蒜、无盐、无额外油或调味。'},
      'feeding':{'total_g':total,'meal_count':meals,'portions_g':portions,'instruction':'替代相应主粮热量份额，不叠加原日量；已有药物餐时安排沿用原计划。'},
      'storage_limits':deepcopy(storage),'storage':['制作后及时分装冷藏，建议当天使用。',f"冷藏≤{storage['refrigerator_c']}°C；常温不超过{storage['ambient_hours']}小时，超过{storage['hot_ambient_c']}°C时不超过{storage['hot_ambient_hours']}小时。",f"需复热时中心至少{storage['reheat_c']}°C，再冷却至适口温度；保存条件不明或剩食丢弃。"],
      'hydration_notes':hydrate,'nutrition_reminders':[n['user_message'] for n in notes],
      'health_support_notes':[n['user_message'] for n in health],'disease_support_notes':[n['user_message'] for n in disease]+m.get('disease_cooking_notes',[]),
      'product_doses_included':False,'source_ids':['COOKING_TEMPERATURE','COOKING_STORAGE']}

def cooking_consistent(components,plan,m):
    if not plan or not components:return False
    ids=Counter(c['ingredient_id'] for c in components)
    if Counter(x['ingredient_id'] for x in plan['shopping_list'])!=ids or Counter(x['ingredient_id'] for x in plan['preparation'])!=ids:return False
    if Counter(i for x in plan['cooking_steps'] for i in x['ingredient_ids'])!=ids or Counter(plan['mixing']['ingredient_ids'])!=ids:return False
    byid={c['ingredient_id']:c for c in components}
    if any(any(row[k]!=byid[row['ingredient_id']][k] for k in ['amount_g','food_state','weight_basis']) for row in plan['shopping_list']):return False
    if any(row['food_state']!=byid[i]['food_state'] for row in plan['cooking_steps'] for i in row['ingredient_ids']):return False
    total=sum(c['amount_g'] for c in components)
    return total==plan['feeding']['total_g']==sum(plan['feeding']['portions_g']) and len(plan['feeding']['portions_g'])==m['meal_count']==plan['feeding']['meal_count'] and not plan['product_doses_included']
