"""Indication-specific four-purpose recommendations. Unknown is never zero/safe."""
from copy import deepcopy
from collections import Counter
from pathlib import Path
import hashlib,json
from .scientific_supplements import ReviewedStore
from .supplement_recommendations import nutrient_matrix, recommendations
from .freshfood_contract import require

GOALS=['NUTRIENT_COMPLETION','HEALTH_RISK_SUPPORT','DISEASE_SUPPORT','DEFICIENCY_CORRECTION']
PIPELINE=['PURPOSE_AND_CANDIDATE','INDICATION_EVIDENCE_CHECK','SPECIES_STAGE_SAFETY_CHECK',
          'RECIPE_AND_ACTIVE_INGREDIENT_RECONCILIATION','TARGET_CALCULATION','RECOMMENDATION']
ACTIVE={'ELEMENTAL_CALCIUM':'calcium','TAURINE':'taurine','EPA_DHA':'epa_dha','COBALAMIN':'b12','POTASSIUM':'potassium','VITAMIN_D':'vitamin_d','ZINC':'zinc'}
TITLES={'CALCIUM':'关注元素钙和钙磷平衡','TAURINE':'确保稳定可靠的牛磺酸来源','OMEGA3_EPA_DHA':'评估EPA和DHA营养支持',
 'VITAMIN_MINERAL':'逐项核对维生素和矿物质','POTASSIUM':'先核对血钾，再评估补钾','COBALAMIN_B12':'核对维生素B12状态与吸收情况','MCT':'评估认知支持饮食','FIBER':'先核对食物中的纤维'}

def evidence_matrix(store):
    data=Path(__file__).with_name('supplement_evidence_matrix.json').read_bytes()
    pin=store.config.get('scientific_model_v17',{})
    require(pin.get('evidence_sha256')==hashlib.sha256(data).hexdigest(),'SUPPLEMENT_EVIDENCE_PIN_MISMATCH')
    return json.loads(data)

def applicable_stage(pet,stage):
    label=stage.removeprefix(pet['species']+'_')
    return {'MATURE':'ADULT','LATE_GROWTH_SMALL':'LATE_GROWTH_SMALL_MEDIUM'}.get(label,label)

def applies(row,pet,stage):
    stage=applicable_stage(pet,stage)
    return pet['species'] in row['species'] and (stage in row['life_stage'] or 'ADULT' in row['life_stage'] and stage.endswith('ADULT'))

def base_row(rec):
    return {'CALCIUM':'COMP_CA','TAURINE':'COMP_TAU','OMEGA3_EPA_DHA':'COMP_OMEGA','VITAMINERAL':'COMP_MICRO','VITAMIN_MINERAL':'COMP_MICRO'}[rec['supplement_type']]

def block_nutrients(diseases):
    blocked=set()
    if 'COPPER_HEPATOPATHY' in diseases:blocked.add('copper')
    if diseases & {'CKD','PLN'}:blocked |= {'phosphorus','potassium','sodium','vitamin_d'}
    if diseases & {'MMVD','DCM','HCM','CHF','HYPERTENSION'}:blocked |= {'potassium','sodium'}
    return blocked

def refresh_completion(rec):
    rows=rec['nutrient_matrix'];bundle=rec['active_nutrient']=='MICRONUTRIENT_MATRIX'
    def val(key):return {r['nutrient_id']:r.get(key) for r in rows} if bundle else rows[0].get(key)
    rec['reference_target']={k:val(k) for k in ['target_amount','target_min','target_max','unit']}
    rec['food_contribution']=rec['food_contribution_estimate']=val('food_contribution_estimate')
    known=all(r['calculation_status']=='REFERENCE_ESTIMATE' and r['additional_amount_needed'] is not None and not r['target_conflict'] for r in rows)
    for key in ['target_amount','target_min','target_max','additional_amount_needed']:
        rec[key]=val(key) if known else None
    rec['additional_needed']=rec['additional_amount_needed']
    rec['calculation_status']='REFERENCE_TARGET_CALCULATED' if known else 'NEEDS_EVIDENCE'
    rec['target_scope']='TOTAL_DAILY_NUTRIENT_REFERENCE_NOT_PRODUCT_DOSE' if known else 'NO_ACTIONABLE_NUMERIC_TARGET'
    rec['confidence']=rec['confidence_level']='REFERENCE_ESTIMATE' if known else 'NEEDS_EVIDENCE'
    rec['recipe_reason']['nutrients']=[r['nutrient_id'] for r in rows]
    rec['upper_limit']={r['nutrient_id']:r.get('target_max') for r in rows} if bundle else rows[0].get('target_max')
    return known

def enrich(rec,row,matrix_doc,pet,stage):
    rec.update(goal=row['goal'],supplement_goal=row['goal'],supplement_goals=[row['goal']],
        recommendation_id=rec['supplement_type'],title=TITLES.get(rec['supplement_type'],'条件评估：营养支持'),
        physiologic_role=row['physiologic_role'],species_applicability=row['species'],life_stage_applicability=row['life_stage'],
        risk_factors=[],evidence_level=row['evidence_level'],evidence_source_ids=row['source'],
        evidence_sources=[{**deepcopy(matrix_doc['sources'][sid]),'evidence_level':row['evidence_level']} for sid in row['source']],
        clinical_outcome_supported=row['clinical_outcome_supported'],clinical_outcome_scope=row['clinical_outcome'],
        THERAPEUTIC_NUTRITION_EVIDENCE=row['therapeutic_nutrition_evidence'],
        contraindications=deepcopy(row['contraindications']),conditional_requirements=deepcopy(row['conditional_requirements']),
        interaction_status='UNKNOWN',interaction_notes=['尚无完整药物相互作用数据库；不能据此认定无药物相互作用。'],
        safety_status='CONDITIONAL',auto_recommend=False,automatic_dose_allowed=False,
        support_indications=[],evidence_id=row['evidence_id'],evidence_status='SUPPORTED_CONDITIONAL',
        target_direction='先核实对应营养需求与食物贡献，再确定额外需要',
        basis=rec['target_basis'],suppressed_nutrients=[])
    rec.setdefault('quality_indicators',['完整定量成分表','有效成分和载体可追溯','适用物种与保存条件清楚'])
    if pet['allergies']:rec['conditional_requirements'].append('ALLERGEN_FREE_ACTIVE_AND_CARRIER')
    return rec

def support_rec(row,doc,state,matrix):
    pet=state['raw']['pet'];nutrient=ACTIVE.get(row['active_nutrient']);food=next((r['food_contribution_estimate'] for r in matrix if r['nutrient_id']==nutrient),None)
    rec=dict(supplement_type=row['supplement'],active_nutrient=row['active_nutrient'],
        why_recommended='当前记录涉及'+ '、'.join(row['condition'])+'；需先满足本项适用条件。',
        recipe_reason={'ingredient_ids':[r['ingredient_id'] for r in state['raw']['daily_foods']], 'nutrients':[nutrient] if nutrient else [],'trigger_conditions':row['condition']},
        target_amount=None,target_min=None,target_max=None,unit=next((r['unit'] for r in matrix if r['nutrient_id']==nutrient),None),
        target_basis='INDIVIDUAL_CLINICAL_CONTEXT_REQUIRED',target_scope='CONDITIONAL_SUPPORT_NOT_A_DOSE',
        food_contribution=food,food_contribution_estimate=food,additional_amount_needed=None,additional_needed=None,
        label_should_show=['EPA、DHA各自每份含量；不能只看鱼油总重量'] if row['active_nutrient']=='EPA_DHA' else ['准确有效成分、每份含量、单位与全部载体'],
        disease_relevance=row['condition'],confidence='CONDITIONAL',confidence_level='CONDITIONAL',calculation_status='CONDITIONAL_NO_NUMERIC_TARGET',
        user_message='',mineral_pair_note=None,not_recommended_when=['适用条件未满足','与整份配方或已有治疗冲突'],
        nutrient_matrix=[],commercial_product_dose=None,upper_limit=None,reference_target=None,recommended_action='ASSESS_CONDITIONS')
    return enrich(rec,row,doc,pet,state['raw'].get('life_stage',''))

def run_supplements(state,store):
    doc=evidence_matrix(store);byid={r['evidence_id']:r for r in doc['rows']}
    pet=state['raw']['pet'];stage=state['raw'].get('life_stage','');diseases=set(state['raw']['disease_advice']['diseases'])
    context=pet.get('_clinical_nutrition_v17',{});deficiencies={r['active_nutrient']:r for r in context.get('documented_deficiencies',[])}
    view=ReviewedStore(store);matrix=nutrient_matrix(state,view);recs=[];audits=[]
    if not state['raw']['daily_foods']:return matrix,recs,{'layers':GOALS,'pipeline':PIPELINE,'candidates':[],'safety':safety_check([],matrix,pet,diseases,stage),'no_age_only_package':True,'no_brand_recommendation':True}
    blocked=block_nutrients(diseases)
    for rec in recommendations(state,view,matrix):
        rec=deepcopy(rec);row=byid[base_row(rec)];enrich(rec,row,doc,pet,stage)
        removed=[r['nutrient_id'] for r in rec['nutrient_matrix'] if r['nutrient_id'] in blocked]
        rec['nutrient_matrix']=[r for r in rec['nutrient_matrix'] if r['nutrient_id'] not in blocked]
        for n in removed:audits.append(dict(candidate_id='COMPLETION:'+n,goal='NUTRIENT_COMPLETION',active_nutrient=n,evidence_level='EVIDENCE_A',decision='WITHHELD_DISEASE_CONFLICT',safety_status='AVOID',target_amount=None,reason='疾病限制或化验要求优先；健康参考要求保留在营养矩阵，不生成额外补充目标。'))
        if not rec['nutrient_matrix']:continue
        known=refresh_completion(rec);rec['suppressed_nutrients']=removed
        applicable=applies(row,pet,stage)
        rec['auto_recommend']=bool(known and applicable and not removed)
        rec['evidence_status']='SUPPORTED_REFERENCE' if known and applicable else 'NEEDS_EVIDENCE'
        rec['recommended_action']='VERIFY_NUTRIENT_COMPLETION'
        rec['conditional_requirements']=['ALL_PRODUCT_PANELS','MEDICATION_REVIEW']+([] if known else ['KNOWN_COOKED_FOOD_CONTRIBUTION'])
        if diseases & {'CKD','PLN'} and rec['active_nutrient']=='ELEMENTAL_CALCIUM':
            rec.update(auto_recommend=False,target_amount=None,target_min=None,target_max=None,additional_amount_needed=None,additional_needed=None,confidence='CONDITIONAL',confidence_level='CONDITIONAL',calculation_status='CONDITIONAL_NO_NUMERIC_TARGET')
            rec['conditional_requirements']+=['IONIZED_CALCIUM','SERUM_PHOSPHORUS','RENAL_STAGE','VETERINARY_MINERAL_PLAN']
        if not applicable:rec.update(auto_recommend=False,safety_status='AVOID',evidence_status='NEEDS_EVIDENCE')
        audits.append(dict(candidate_id=row['evidence_id'],goal=row['goal'],evidence_level=row['evidence_level'],decision='REFERENCE_COMPLETION' if rec['auto_recommend'] else 'CONDITIONAL',safety_status=rec['safety_status']))
        recs.append(rec)
    # Support purpose is selected before its evidence/safety/target evaluation.
    conditions=set(diseases)
    if 'SENIOR' in stage:conditions.add('AGE_OR_BREED_ONLY')
    if context.get('risk_factors') or pet['bcs']>=7:conditions.add('MOBILITY_DECLINE_OR_OBESITY')
    if context.get('cognitive_dysfunction_report'):conditions.add('COGNITIVE_DYSFUNCTION')
    candidates=[r for r in doc['rows'] if r['goal'] not in {'NUTRIENT_COMPLETION','DEFICIENCY_CORRECTION'} and set(r['condition'])&conditions and pet['species'] in r['species']]
    for active in deficiencies:
        row=byid['DEF_B12' if active=='COBALAMIN' else 'DEF_TAU']
        if pet['species'] in row['species']:candidates.append(row)
    for row in candidates:
        active=row['active_nutrient'];supported=row['evidence_level'] in {'EVIDENCE_A','EVIDENCE_B'} and bool(row['source']) and applies(row,pet,stage)
        if active in deficiencies and row['goal']=='DISEASE_SUPPORT':
            audits.append({**deepcopy(row),'decision':'MERGED_WITH_DOCUMENTED_DEFICIENCY','safety_status':'CONDITIONAL'});continue
        audit={**deepcopy(row),'candidate_id':row['evidence_id'],'decision':'CONDITIONAL' if supported else 'AUDIT_ONLY','safety_status':'CONDITIONAL' if supported else 'UNKNOWN','target_amount':None}
        audits.append(audit)
        if not supported:continue
        rec=support_rec(row,doc,state,matrix)
        disease_names=store.keyed('diseases','disease_id')
        names=[disease_names[d]['name_zh'] for d in row['condition'] if d in disease_names]
        rec['why_recommended']='当前记录涉及'+('、'.join(names) if names else '已记录的营养或功能状态')+'；先核实本项适用条件，再考虑营养支持。'
        rec['risk_factors']=context.get('risk_factors',[])
        if row['goal']=='DEFICIENCY_CORRECTION':
            rec['why_recommended']='已有临床确认的营养缺乏记录：'+deficiencies[active]['report_reference']+'；纠正途径与方案仍需按临床计划确定。'
            rec['conditional_requirements']=['VETERINARY_ROUTE_AND_DOSE','FOLLOWUP_NUTRIENT_STATUS','ALL_PRODUCT_PANELS','MEDICATION_REVIEW']
        if row['evidence_id']=='MMVD_OMEGA' and context.get('mmvd_stage')!='C':rec['conditional_requirements'].append('MMVD_STAGE_C_NOT_CONFIRMED')
        if active=='EPA_DHA' and diseases & {'PANCREATITIS_DOG','HYPERLIPIDEMIA'}:rec['conditional_requirements'].append('WHOLE_RECIPE_FAT_CEILING_RECALCULATION')
        nutrient=ACTIVE.get(active)
        # Extract this nutrient from a mixed completion list before adding a
        # clinical indication. A diet estimate cannot serve as an absorption dose.
        for bundle in list(recs):
            if bundle['active_nutrient']=='MICRONUTRIENT_MATRIX' and any(r['nutrient_id']==nutrient for r in bundle['nutrient_matrix']):
                bundle['nutrient_matrix']=[r for r in bundle['nutrient_matrix'] if r['nutrient_id']!=nutrient]
                if bundle['nutrient_matrix']:refresh_completion(bundle)
                else:recs.remove(bundle)
        same=next((r for r in recs if r['active_nutrient']==active),None)
        if same and row['goal']!='DEFICIENCY_CORRECTION':
            same['support_indications'].append({k:deepcopy(rec[k]) for k in ['goal','why_recommended','evidence_level','evidence_source_ids','target_amount','conditional_requirements','clinical_outcome_supported']})
            same['supplement_goals']=sorted(set(same['supplement_goals']+[row['goal']]))
            audit['merged_into']=same['recommendation_id']
        else:
            if same:recs.remove(same)
            recs.append(rec)
    for rec in recs:
        known=rec['target_amount'] is not None
        rec['user_message']=('本次整份食物计算得到的是每日有效营养成分目标；额外需要需扣除食物贡献。' if known else '暂无可靠条件确定具体剂量。')
        if rec['active_nutrient']=='TAURINE' and pet['species']=='CAT':rec['user_message']+='应确保稳定可靠的牛磺酸来源。'
        if rec['active_nutrient']=='COBALAMIN':rec['user_message']+='需核对血液B12结果、吸收情况及临床补充途径。'
        if rec['active_nutrient']=='POTASSIUM':rec['user_message']+='需先检查血钾、肾病分期及正在使用的药物。'
        if rec['active_nutrient']=='EPA_DHA':rec['user_message']+='需计入当前食物的EPA、DHA、脂肪和热量，再核对个体目标。'
        rec['user_message']+=' '+rec['physiologic_role']+' 购买时核对每份有效成分和全部载体；不能用产品克数代替有效成分，也不能替代既定治疗。'
        if rec['suppressed_nutrients']:rec['user_message']+=' 此建议不包含新增'+ '、'.join(rec['suppressed_nutrients'])+'，需按疾病计划单独核对。'
    safety=safety_check(recs,matrix,pet,diseases,stage)
    return matrix,recs,dict(layers=GOALS,pipeline=PIPELINE,candidates=audits,safety=safety,no_age_only_package=True,no_brand_recommendation=True)

def safety_check(recs,matrix,pet,diseases,stage):
    ledger=[];conflicts=[];applicability=[];blocked=block_nutrients(diseases)
    for rec in recs:
        applicable=pet['species'] in rec['species_applicability'] and applicable_stage(pet,stage) in rec['life_stage_applicability']
        if not applicable:applicability.append(rec['recommendation_id'])
        active_rows=rec['nutrient_matrix']
        for row in active_rows:
            ledger.append({'nutrient_id':row['nutrient_id'],'recommendation_id':rec['recommendation_id'],'additional_amount_needed':row['additional_amount_needed'] if rec['target_amount'] is not None else None,'unit':row['unit'],'mode':'REFERENCE_COMPLETION'})
            if row['nutrient_id'] in blocked:conflicts.append(row['nutrient_id'])
        if not active_rows:ledger.append({'nutrient_id':ACTIVE.get(rec['active_nutrient'],rec['active_nutrient']),'recommendation_id':rec['recommendation_id'],'additional_amount_needed':None,'unit':rec['unit'],'mode':'CONDITIONAL_CLINICAL_NO_DOSE'})
        if rec['active_nutrient'] in {'URINARY_ACIDIFIER','VITAMIN_C'} and diseases & {'CALCIUM_OXALATE','UROLITH_UNKNOWN','URATE','CYSTINE'}:conflicts.append(rec['active_nutrient'])
        if rec['active_nutrient']=='URINARY_ALKALIZER' and diseases & {'STRUVITE','UROLITH_UNKNOWN'}:conflicts.append(rec['active_nutrient'])
    counts=Counter(r['nutrient_id'] for r in ledger);duplicates=[k for k,v in counts.items() if v>1]
    upper=[r['nutrient_id'] for r in matrix if r['target_conflict'] or r['additional_amount_needed'] is not None and r['additional_upper_headroom'] is not None and r['additional_amount_needed']>r['additional_upper_headroom']+1e-6]
    return {'status':'AVOID' if duplicates or conflicts or upper or applicability else 'CONDITIONAL',
        'duplicate_active_nutrients':duplicates,'upper_conflicts':upper,'disease_conflicts':conflicts,'applicability_conflicts':applicability,
        'active_ingredient_ledger':ledger,'interaction_status':'UNKNOWN','product_verification_complete':False,'unknown_is_safe':False,
        'checks':{'species_and_life_stage':'FAIL' if applicability else 'PASS','disease':'FAIL' if conflicts else 'PASS',
        'duplicate_active_ingredients':'FAIL' if duplicates else 'PASS','food_contribution':'KNOWN_ESTIMATES_AND_EXPLICIT_UNKNOWNS',
        'upper_limits':'FAIL' if upper else 'REFERENCE_SCREENED_NOT_ALL_UL_KNOWN','multiple_supplements':'UNKNOWN_WITHOUT_PRODUCT_PANELS','medication_interactions':'UNKNOWN'}}
