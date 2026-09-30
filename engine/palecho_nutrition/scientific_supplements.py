"""Three-layer candidates, applicability, duplicate and safety decisions.

Conditional disease support is not an applied dose. Missing product, laboratory,
medication, or cooked-food data stays explicit through preparation and snapshots.
"""
from copy import deepcopy
from .scientific_profile import policy
from .supplement_recommendations import nutrient_matrix, recommendations

LAYERS = ['NUTRIENT_COMPLETION', 'HEALTH_RISK_SUPPORT', 'DISEASE_SUPPORT']
PIPELINE = ['CANDIDATE_GENERATOR', 'EVIDENCE_FILTER', 'SAFETY_FILTER',
            'CONTRAINDICATION_CHECK', 'INTERACTION_CHECK', 'TARGET_CALCULATION', 'NUTRIENT_DEDUPLICATION']


class ReviewedStore:
    def __init__(self, store): self.store = store
    def rows(self, name): return self.store.rows(name)
    def keyed(self, name, key):
        result = self.store.keyed(name, key)
        if name == 'sources':
            result = deepcopy(result)
            for sid, source in policy(self.store)['reviewed_sources'].items():
                if sid not in result: continue
                # Directions with unconfirmed metadata never become verified
                # quantitative requirements merely by passing through this view.
                if source['evidence_status'] == 'VERIFIED':
                    result[sid].update(year=source['year'], version=source['version'])
        return result


def evidence(store, sid, basis=None):
    row = policy(store)['reviewed_sources'].get(sid)
    if row:
        row = deepcopy(row)
        if basis: row['basis'] = basis
        return row
    source = store.keyed('sources','source_id').get(sid)
    return {'source_id':sid, 'organization':source['organization'] if source else None,
        'document':source['title'] if source else None, 'year':source['year'] if source else None,
        'version':source['version'] if source else None, 'URL':source['URL'] if source else None,
        'basis':basis, 'evidence_level':'INSUFFICIENT', 'evidence_status':'NEEDS_EVIDENCE'}


def support_candidates(state, store):
    pet = state['raw']['pet']; ids = set(state['raw']['disease_advice']['diseases'])
    candidates = []
    def add(kind, nutrient, diseases, level, sources, role, needs, reason, goal='DISEASE_SUPPORT'):
        candidates.append({'supplement_type':kind, 'active_nutrient':nutrient,
            'supplement_goal':goal, 'disease_ids':sorted(diseases), 'evidence_level':level,
            'source_ids':sources, 'physiologic_role':role, 'conditional_requirements':needs,
            'reason':reason, 'target_amount':None})
    if ids & {'OSTEOARTHRITIS','JOINT_CHRONIC'}:
        add('OMEGA3_EPA_DHA','EPA_DHA',ids & {'OSTEOARTHRITIS','JOINT_CHRONIC'},
            'EVIDENCE_A' if pet['species']=='DOG' else 'EVIDENCE_C', ['AAHA_PAIN2022'],
            'EPA/DHA参与脂质介质和细胞膜代谢；在犬OA可作为关节舒适与活动能力的辅助营养管理。',
            ['INDIVIDUAL_EPA_DHA_TARGET','PRODUCT_FAT_AND_ENERGY','MEDICATION_AND_BLEEDING_REVIEW'],
            '已确诊关节疾病触发证据筛选；不能把总鱼油当作EPA/DHA。')
        add('GLUCOSAMINE_CHONDROITIN','GLUCOSAMINE_CHONDROITIN',ids & {'OSTEOARTHRITIS','JOINT_CHRONIC'},
            'INSUFFICIENT',['AAHA_PAIN2022'],'拟作为软骨基质相关营养支持，但临床获益证据不稳定。',
            ['PRODUCT_SPECIFIC_CLINICAL_EVIDENCE'],'证据不足，不与Omega-3同级自动推荐。')
    elif 'SENIOR' in state['raw'].get('life_stage',''):
        add('OMEGA3_EPA_DHA','EPA_DHA',set(),'INSUFFICIENT',['AAHA_PAIN2022'],
            'EPA/DHA参与细胞膜与脂质介质代谢。',['IDENTIFIED_JOINT_RISK_OR_DIAGNOSIS'],
            '年龄本身不足以建立补充指征，风险支持层不自动发套餐。','HEALTH_RISK_SUPPORT')
    if ids & {'CKD','PLN'}:
        source = 'IRIS_CAT2026' if pet['species']=='CAT' else 'IRIS_DOG2026'
        for kind, nutrient, role, needs in [
            ('POTASSIUM','POTASSIUM','维持膜电位和神经肌肉功能；肾病补充取决于血钾与用药。',
             ['SERUM_POTASSIUM','RENAL_STAGE','MEDICATION_REVIEW']),
            ('VITAMIN_D','VITAMIN_D','参与钙磷代谢；营养维D与活性维D治疗不是同一种干预。',
             ['IONIZED_CALCIUM','PHOSPHORUS','PTH_WHEN_INDICATED','RENAL_STAGE','VETERINARY_PLAN']),
            ('OMEGA3_EPA_DHA','EPA_DHA','作为肾病整体营养管理的候选，不能替代肾病处方饮食。',
             ['INDIVIDUAL_EPA_DHA_TARGET','PRODUCT_FAT_AND_ENERGY','MEDICATION_REVIEW'])]:
            add(kind,nutrient,ids & {'CKD','PLN'},'EVIDENCE_B',[source],role,needs,
                '确诊肾病仅触发评估；缺少个体检查与适用定量依据时目标保持null。')
    if pet['species']=='DOG' and ids & {'MMVD','CHF'}:
        add('OMEGA3_EPA_DHA','EPA_DHA',ids & {'MMVD','CHF'},'EVIDENCE_B',['ACVIM_MMVD2019'],
            '对适用的Stage C二尖瓣疾病犬，可考虑EPA/DHA辅助营养支持。',
            ['CONFIRMED_MMVD_STAGE_C','APPETITE_MUSCLE_ARRHYTHMIA_REVIEW','INDIVIDUAL_EPA_DHA_TARGET','MEDICATION_REVIEW'],
            '共识的疾病类型与阶段适用性需要核对，不外推至所有心脏病。')
    if 'DCM' in ids and pet['species']=='DOG':
        add('TAURINE','TAURINE',{'DCM'},'EVIDENCE_B',['DCM_KAPLAN2018','FEDIAF2025'],
            '参与心肌功能；缺乏相关DCM需要检测与个体营养纠正评估。',
            ['BLOOD_TAURINE','DIET_HISTORY','CARDIOLOGY_PLAN'],
            'DCM需要鉴别是否与营养缺乏有关，不按疾病名称给治疗剂量。')
        add('L_CARNITINE','L_CARNITINE',{'DCM'},'EVIDENCE_C',['DCM_KAPLAN2018'],
            '参与长链脂肪酸进入线粒体的转运；部分DCM情境可评估辅助价值。',
            ['SPECIFIC_DCM_ETIOLOGY','CARDIOLOGY_PLAN'],
            '现有病例多为联合干预，不能证明肉碱对所有DCM有独立获益。')
    gi = ids & {'CIE_DOG','CIE_CAT','CHRONIC_DIARRHEA','FOOD_RESPONSIVE_ENTEROPATHY','EPI','PLE'}
    if gi:
        add('COBALAMIN_B12','COBALAMIN',gi,'EVIDENCE_B',['MERCK_EPI'],
            '钴胺素参与细胞代谢；吸收不良伴低钴胺素时需评估补充。',
            ['SERUM_COBALAMIN','DIAGNOSIS_AND_ABSORPTION_REVIEW','VETERINARY_ROUTE_AND_DOSE'],
            '食品已有B12不证明吸收正常，也不能由GI标签推断缺乏。')
        add('PROBIOTIC','STRAIN_SPECIFIC_PROBIOTIC',gi,'EVIDENCE_C',['MERCK_EPI'],
            '特定菌株可能支持肠道微生态；效果不能跨菌株或疾病外推。',
            ['IDENTIFIED_STRAIN','STRAIN_SPECIFIC_TRIAL','IMMUNE_STATUS_REVIEW'],
            '缺菌株与适用试验证据，不自动推荐通用益生菌。')
    if ids & {'CONSTIPATION','DIABETES_DOG'}:
        add('FIBER','DIETARY_FIBER',ids & {'CONSTIPATION','DIABETES_DOG'},
            'EVIDENCE_B' if 'DIABETES_DOG' in ids else 'EVIDENCE_C',
            ['AAHA_DM_DOG2026'] if 'DIABETES_DOG' in ids else [],
            '膳食纤维可影响粪便与餐后营养吸收，应结合体况、现有食物与耐受选择。',
            ['FIBER_TYPE','FOOD_FIBER_CONTRIBUTION','HYDRATION_AND_TOLERANCE'],
            '先评估食物来源；不把膳食纤维总量当作任意纤维产品剂量。')
    return candidates


def run_supplements(state, store):
    view = ReviewedStore(store)
    matrix = nutrient_matrix(state, view)
    base = recommendations(state, view, matrix)
    pet=state['raw']['pet']; diseases=set(state['raw']['disease_advice']['diseases'])
    audits=[]; output=[]
    for rec in base:
        rec=deepcopy(rec); unknown=any(r['calculation_status']!='REFERENCE_ESTIMATE' for r in rec['nutrient_matrix'])
        rec.update(recommendation_id=rec['supplement_type'], supplement_goal='NUTRIENT_COMPLETION',
            supplement_goals=['NUTRIENT_COMPLETION'], evidence_level='EVIDENCE_A',
            evidence_sources=[evidence(store,sid,'NUTRIENT_REQUIREMENT') for sid in rec['evidence_source_ids'] if sid!='MSD_NUTRITION2024'],
            basis=rec['target_basis'], food_contribution=rec['food_contribution_estimate'],
            additional_needed=rec['additional_amount_needed'], confidence=rec['confidence_level'],
            contraindications=[], conditional_requirements=['PRODUCT_QUANTITATIVE_PANEL','ALL_OTHER_SUPPLEMENTS'],
            safety_status='CONDITIONAL', auto_recommend=True, automatic_dose_allowed=False,
            recommended_action='VERIFY_NUTRIENT_COMPLETION', support_indications=[])
        if not rec['evidence_sources'] or any(e['evidence_status']!='VERIFIED' for e in rec['evidence_sources']):
            rec.update(evidence_level='INSUFFICIENT',auto_recommend=False)
            rec['conditional_requirements'].append('SOURCE_APPLICABILITY_VERIFICATION')
        if unknown:rec['conditional_requirements'].append('COOKED_FOOD_BACKGROUND_OR_APPLICABILITY')
        nutrients={r['nutrient_id'] for r in rec['nutrient_matrix']}
        if diseases & {'CKD','PLN','CHF','MMVD','HCM','DCM','HYPERTENSION'} and nutrients & {'potassium','sodium','vitamin_d','phosphorus','calcium'}:
            rec['conditional_requirements'] += ['DISEASE_MINERAL_AND_MEDICATION_REVIEW']
            rec['contraindications'].append('不得将基础营养补足量作为肾病电解质、活性维D或磷结合剂处方。')
        if 'COPPER_HEPATOPATHY' in diseases and 'copper' in nutrients:
            rec['conditional_requirements'].append('HEPATIC_COPPER_PLAN')
        if pet['allergies']:
            rec['conditional_requirements'].append('ALLERGEN_FREE_ACTIVE_AND_CARRIER_DECLARATION')
        audits.append({'candidate_id':rec['recommendation_id'],'supplement_goal':'NUTRIENT_COMPLETION',
            'decision':'INCLUDED','evidence_level':rec['evidence_level'],'safety_status':rec['safety_status']})
        output.append(rec)
    for candidate in support_candidates(state, store) if state['raw']['daily_foods'] else []:
        decision='CONDITIONAL' if candidate['evidence_level'] in {'EVIDENCE_A','EVIDENCE_B'} else 'NOT_AUTOMATICALLY_RECOMMENDED'
        audit={**deepcopy(candidate),'candidate_id':candidate['supplement_type']+':'+','.join(candidate['disease_ids']),
               'decision':decision,'safety_status':'CONDITIONAL' if decision=='CONDITIONAL' else 'UNKNOWN'}
        if candidate['active_nutrient']=='EPA_DHA' and diseases & {'PANCREATITIS_DOG','HYPERLIPIDEMIA'}:
            audit['conditional_requirements'] += ['WHOLE_RECIPE_FAT_CEILING_RECALCULATION']
        audits.append(audit)
        if decision!='CONDITIONAL':continue
        same=next((r for r in output if r['active_nutrient']==candidate['active_nutrient']),None)
        # Keep one nutritional target. Pending disease support never adds a
        # second dose or silently raises an already-computed completion target.
        indication={'disease_ids':candidate['disease_ids'],'reason':candidate['reason'],
            'evidence_level':candidate['evidence_level'],'target_amount':None,
            'conditional_requirements':audit['conditional_requirements']}
        if same:
            same['supplement_goals']=sorted(set(same['supplement_goals'])|{candidate['supplement_goal']})
            same['support_indications'].append(indication)
            same['conditional_requirements']=sorted(set(same['conditional_requirements']+audit['conditional_requirements']))
            same['evidence_sources'] += [evidence(store,sid) for sid in candidate['source_ids']]
            audit['merged_into']=same['recommendation_id']
            continue
        row=next((r for r in matrix if r['nutrient_id']=={'EPA_DHA':'epa_dha','POTASSIUM':'potassium','VITAMIN_D':'vitamin_d','COBALAMIN':'b12','TAURINE':'taurine'}.get(candidate['active_nutrient'])),None)
        contribution=row['food_contribution_estimate'] if row else None
        output.append({'recommendation_id':candidate['supplement_type'],
            'supplement_type':candidate['supplement_type'], 'active_nutrient':candidate['active_nutrient'],
            'supplement_goal':candidate['supplement_goal'],'supplement_goals':[candidate['supplement_goal']],
            'title':'条件评估：'+candidate['supplement_type'], 'why_recommended':candidate['reason'],
            'physiologic_role':candidate['physiologic_role'],
            'recipe_reason':{'ingredient_ids':[r['ingredient_id'] for r in state['raw']['daily_foods']],
                'trigger_conditions':candidate['disease_ids'],'nutrients':[]},
            'target_amount':None,'target_min':None,'target_max':None,'additional_amount_needed':None,
            'food_contribution_estimate':contribution,'food_contribution':contribution,'additional_needed':None,
            'unit':row['unit'] if row else None,'target_basis':'INDIVIDUAL_CLINICAL_CONTEXT_REQUIRED',
            'basis':'INDIVIDUAL_CLINICAL_CONTEXT_REQUIRED','target_scope':'CONDITIONAL_SUPPORT_NOT_A_DOSE',
            'label_should_show':['准确有效成分及每份含量、单位、全部载体和其他营养成分'],
            'quality_indicators':[], 'disease_relevance':indication['disease_ids'],
            'evidence_source_ids':candidate['source_ids'],
            'evidence_sources':[evidence(store,sid) for sid in candidate['source_ids']],
            'evidence_level':candidate['evidence_level'],'confidence_level':'CONDITIONAL','confidence':'CONDITIONAL',
            'calculation_status':'CONDITIONAL_NO_NUMERIC_TARGET','user_message':'完成所列检查并确定适用性后，再核对整份配方；目前没有添加剂量。',
            'mineral_pair_note':None,'not_recommended_when':['未满足适用疾病类型、阶段或检查条件','与现有药物、营养上限或食物禁忌冲突'],
            'nutrient_matrix':[],'commercial_product_dose':None,'contraindications':[],
            'conditional_requirements':audit['conditional_requirements'],'safety_status':'CONDITIONAL',
            'auto_recommend':False,'automatic_dose_allowed':False,'recommended_action':'ASSESS_CONDITIONS',
            'support_indications':[indication]})
    safety=safety_check(output,matrix,pet,diseases)
    return matrix,output,{'layers':LAYERS,'pipeline':PIPELINE,'candidates':audits,
        'no_age_only_package':True,'no_brand_recommendation':True,'safety':safety}


def safety_check(recs, matrix, pet, diseases):
    seen=set();duplicates=[];conflicts=[]
    for rec in recs:
        # A pending conditional action carries no second active nutrient dose.
        for row in rec['nutrient_matrix']:
            nutrient=row['nutrient_id']
            if nutrient in seen:duplicates.append(nutrient)
            seen.add(nutrient)
        if rec['active_nutrient'] in {'URINARY_ACIDIFIER','VITAMIN_C'} and diseases & {'CALCIUM_OXALATE','UROLITH_UNKNOWN'}:
            rec['safety_status']='AVOID';rec['auto_recommend']=False;conflicts.append(rec['active_nutrient'])
    above=[r['nutrient_id'] for r in matrix if r['target_conflict'] or
        (r['additional_amount_needed'] is not None and r['additional_upper_headroom'] is not None and
         r['additional_amount_needed']>r['additional_upper_headroom']+1e-6)]
    return {'status':'AVOID' if duplicates or above or conflicts else 'CONDITIONAL',
        'duplicate_active_nutrients':duplicates,'upper_conflicts':above,'disease_conflicts':conflicts,
        'checks':{'species':'CHECKED','life_stage':'CHECKED','disease':'CHECKED',
            'food_contribution':'KNOWN_SUBTOTAL_WITH_UNKNOWNS','nutrient_upper_limits':'REFERENCE_SCREENED',
            'multiple_supplement_overlap':'UNKNOWN_WITHOUT_PRODUCT_PANELS',
            'contraindications':'STRUCTURED_DISEASE_SCREENED','medication_interactions':'UNKNOWN_NO_MEDICATION_INPUT'},
        'product_verification_complete':False,'unknown_is_safe':False}
