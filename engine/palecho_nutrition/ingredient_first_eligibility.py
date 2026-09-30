"""Pre-selection and submission-time eligibility. Never silently remove food."""
from .ingredient_first_repository import CORE_ANIMAL

class IngredientEligibilityEngine:
    def __init__(self,repository):self.repo=repository

    def evaluate(self,profile,pet,advice,model=None):
        from .disease_ingredient_matrix import rows_for
        matrix=rows_for(profile,pet,advice,self.repo.registry)
        result=[];diseases=set(advice['diseases']);target=model['target'] if model else None
        for food in self.repo.records.values():
            reasons=[];values=food['nutrients_per_100g'];iid=food['ingredient_id']
            def reason(level,code,message,source,classification,**details):
                if classification=='HARD_CONTRAINDICATION':
                    sources=[self.repo.registry['sources'][sid] for sid in source]
                    details['evidence_matrix_row']={
                      'species':pet['species'],'disease':'DOCUMENTED_TRIGGER' if code=='DISEASE_CONTRAINDICATION' else sorted(diseases),
                      'stage_or_subtype':code,'life_stage':profile.get('life_stage'),'ingredient_id':iid,
                      'eligibility':level,'reason':message,'nutrient_basis':{'direction':'EXCLUDE_DOCUMENTED_TRIGGER' if code=='DISEASE_CONTRAINDICATION' else 'AUTOMATION_OR_FOOD_SAFETY_GATE'},
                      'minimum':None,'maximum':None,'target':None,'unit':'QUALITATIVE','basis':classification,
                      'source':[{'id':s['source_id'],'url':s['url']} for s in sources],
                      'version':{s['source_id']:s['version'] for s in sources},'year':{s['source_id']:s.get('publication_year') for s in sources},
                      'evidence_level':'DOCUMENTED_INDIVIDUAL_RESTRICTION' if code=='DISEASE_CONTRAINDICATION' else 'GUIDELINE_SAFETY',
                      'applicability':'RECORDED_ALLERGEN_FAMILY_OR_EXACT_VET_RESTRICTION' if code=='DISEASE_CONTRAINDICATION' else code}
                reasons.append({'eligibility':level,'reason_code':code,'display_reason':message,
                  'evidence_source':source,'classification':classification,**details})
            if advice['acute_red_flags']:
                reason('DISABLED','ACUTE_STATE_CONTRAINDICATION','当前急性状态不适合自动生成普通鲜食方案。',['AAHA_NUT2021'],'HARD_CONTRAINDICATION')
            if food['toxicity']:
                reason('DISABLED','GLOBAL_TOXICITY','已知有害食材。',['FEDIAF2025'],'HARD_CONTRAINDICATION')
            if pet['species'] not in food['species_allowed']:
                reason('DISABLED','SPECIES_CONTRAINDICATION','该食品记录不适用于当前物种。',food['safety_source_ids'],'HARD_CONTRAINDICATION')
            if iid in pet['_exclusions_v19']:
                restriction=pet['_exclusions_v19'][iid]
                reason('DISABLED','DISEASE_CONTRAINDICATION','与已记录的过敏、不耐受或兽医禁用食材冲突。',self.repo.registry['rules']['ALLERGEN']['source_ids'],'HARD_CONTRAINDICATION',restriction=restriction)
            errors=self.repo.provenance_errors(food);missing=self.repo.critical_missing(food)
            if 'COPPER_HEPATOPATHY' in diseases and values.get('copper') is None:missing=sorted(set(missing+['copper']))
            if errors or missing:
                reason('DISABLED','DATA_INSUFFICIENT','缺少当前求解所需的可靠营养值，或来源校验失败。',[food['authoritative_source_id']],'DATA_INSUFFICIENT',missing_nutrients=missing,provenance_errors=errors)
            elif food['missing_nutrients']:
                reason('CAUTION','LIMITED_DATA','核心数据可用于犬猫ME预测；未量化的微量营养仍保留未知，预测不等于实测。',[food['authoritative_source_id']],'DATA_QUALITY',missing_nutrients=food['missing_nutrients'])
            if food['raw_or_cooked'] not in {'COOKED','AS_SOLD'} or food['portion_basis']!='EDIBLE_WEIGHT':
                reason('DISABLED','FOOD_STATE_NOT_SUPPORTED','需提供同状态熟制可食部数据。',['FOOD_SAFETY_TEMPERATURE'],'DATA_INSUFFICIENT')
            if diseases&{'PANCREATITIS_DOG','PANCREATITIS_CAT','HYPERLIPIDEMIA'} and values.get('fat') is not None and values['fat']>self.repo.policy['high_fat_caution_g_per_100g']:
                reason('CAUTION','FAT_REQUIRES_COMBINATION_CHECK','脂肪较高；是否可用由整餐限制与实际用量共同决定。',['MERCK_PANC'],'SOFT_LIMIT')
            if diseases&{'CKD','PLN'}:
                reason('CAUTION','RENAL_COMBINATION_REVIEW','需要共同核算磷、蛋白、能量及已有肾病饮食安排。',['IRIS_DOG2026' if pet['species']=='DOG' else 'IRIS_CAT2026'],'SOFT_LIMIT')
            if food['category']=='ORGAN':
                reason('CAUTION','ORGAN_PORTION_LIMIT','内脏按整餐质量与能量上限限量；上限属于配方工程规则。',['PALECHO_INGREDIENT_FIRST'],'ENGINEERING_LIMIT')
            if 'DIABETES_CAT' in diseases and food['category'] in {'ENERGY_SOURCE','PLANT_ASSIST'}:
                reason('CAUTION','CARBOHYDRATE_PREFERENCE','猫糖尿病通常优先较低碳水组合；不因类别名称直接禁用。',['AAHA_DIABETES_CAT2026'],'PREFERRED')
            if diseases&{'CIE_DOG','CIE_CAT','EPI','PLE','CHRONIC_DIARRHEA'}:
                reason('CAUTION','GI_INDIVIDUAL_TOLERANCE','需结合既往耐受和饮食试验；数据库不提供个体消化率。',['ACVIM_CIE2026' if pet['species']=='DOG' else 'AAHA_NUT2021'],'MONITOR')
            if 'CALCIUM_OXALATE' in diseases and 'SPINACH' in food['allergen_tags']:
                reason('CAUTION','OXALATE_UNQUANTIFIED','该记录没有可计算的草酸数据；不将未知浓度写为零。',['USDA_SR2018'],'INSUFFICIENT_EVIDENCE')
            for row in matrix:
                if row['categories'] and food['category'] not in row['categories']:continue
                reason(row['eligibility'],row['reason_code'],row['message'],row['source_ids'],'CLINICAL_REVIEW',
                       evidence_matrix_row={**row,'ingredient_id':iid,'food_state':food['food_state'],
                         'ingredient_nutrient_values':{n:{'value':values.get(n),'unit':food['nutrient_units'].get(n),
                           'basis':'PER_100G_EDIBLE_SAME_STATE','provenance':food['nutrient_provenance'].get(n)} for n in row['nutrients']}})
            state='DISABLED' if any(r['eligibility']=='DISABLED' for r in reasons) else 'CAUTION' if any(r['eligibility']=='CAUTION' for r in reasons) else 'ENABLED'
            first=next((r for r in reasons if r['eligibility']==state),None)
            energy=self.repo.energy(food,pet['species'])['pet_me_kcal_per_100g']
            maximum=target*(1+self.repo.policy['energy_tolerance'])/(energy/100) if target and energy and state!='DISABLED' else None
            if maximum and food['category']=='ORGAN':maximum=min(maximum,target*self.repo.policy['category_energy_max'][pet['species']]['ORGAN']/(energy/100))
            result.append({'ingredient_id':iid,'eligibility':state,'selectable':state!='DISABLED',
              'reason_code':first['reason_code'] if first else 'ELIGIBLE',
              'display_reason':first['display_reason'] if first else '通过当前选择前检查，提交后仍需组合求解。',
              'evidence_source':sorted({s for r in reasons for s in r['evidence_source']}),
              'max_amount_g':maximum,'max_amount_basis':'INITIAL_ME_ESTIMATE_SEARCH_GUIDANCE_FINAL_MIXTURE_MAY_DIFFER',
              'conditions':reasons,'category':food['category'],'display_name_cn':food['display_name_cn']})
        for iid in ['TOX_ONION','TOX_GARLIC','TOX_GRAPE','TOX_CHOCOLATE']:
            result.append({'ingredient_id':iid,'eligibility':'DISABLED','selectable':False,'reason_code':'GLOBAL_TOXICITY',
              'display_reason':'已知毒性风险，不允许选择。','evidence_source':['FEDIAF2025'],
              'max_amount_g':0,'max_amount_basis':'GLOBAL_TOXICITY','conditions':[],
              'category':'OPTIONAL_OTHER','display_name_cn':{'TOX_ONION':'洋葱','TOX_GARLIC':'大蒜','TOX_GRAPE':'葡萄/葡萄干','TOX_CHOCOLATE':'巧克力'}[iid]})
        return result

def missing_categories(selected,eligibility,repo):
    if any(repo.records[i]['category'] in CORE_ANIMAL for i in selected if i in repo.records):return []
    return [{'required_category':['ANIMAL_MEAT','FISH','OTHER_SEAFOOD'],
      'reason':'本产品以可追溯动物性食材作为核心；蛋和受限内脏不能单独替代核心类别。这是物种导向的产品结构要求，不声称是每餐必需食品分类的权威标准。',
      'rule_id':'USER_SELECTED_SET','classification':'ENGINEERING_HEURISTIC',
      'recommended_options':[r['ingredient_id'] for r in eligibility if r['selectable'] and r['category'] in CORE_ANIMAL][:12]}]
