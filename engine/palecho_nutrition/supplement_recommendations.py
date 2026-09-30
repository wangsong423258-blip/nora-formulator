"""Whole-recipe active-nutrient planning, separate from commercial product doses."""
from copy import deepcopy
from .nutrient_reminders import REMINDER_NUTRIENTS
from .recommendation_evidence import ROLES, LABELS, source_record, quality_indicators

MASS_MG = {'calcium','phosphorus','taurine','epa_dha'}


def nutrient_matrix(state, store):
    audit=state['raw'].get('food_reference_audit')
    if not audit:return []
    energy_low,energy_high=audit['reference_energy_kcal_interval']
    target=audit['target_kcal'];dm=audit['food_dry_matter_lower_g']
    grouped={}
    for row in audit['rows']:
        nutrient=row['nutrient_id']
        if row['source_basis']=='RATIO':continue
        scale=1000. if nutrient in MASS_MG and row['unit']=='g' else 1.
        unit='mg' if scale==1000 else row['unit']
        # Apply both nutrient density at actual food energy and absolute daily
        # floor at target energy; retain dry-matter and additive upper bounds.
        factors={'PER_1000_KCAL_ME':(max(target,energy_high)/1000,energy_low/1000),
                 'PER_100G_DM':(dm/100,dm/100),'PER_KG_DM':(dm/1000,dm/1000),'PER_DAY':(1,1)}
        lo_factor,hi_factor=factors[row['source_basis']]
        evidence=source_record(store,row['source_id'],row['source_basis'],row['source_locator'])
        item=grouped.setdefault(nutrient,{'nutrient_id':nutrient,'unit':unit,'target_basis':'PER_DAY',
            'target_min':None,'target_max':None,'food_known_subtotal':row['known_subtotal_daily']*scale,
            'food_contribution_estimate':None,'unquantified_food_ids':[], 'evidence':[],
            'constraints':[], 'reference_scope':'REPRESENTATIVE_FOOD_NOT_MEASURED_INTAKE'})
        item['unquantified_food_ids']=sorted(set(item['unquantified_food_ids'])|set(row['unquantified_background']))
        item['evidence'].append(evidence)
        item['constraints'].append({'constraint_id':row['constraint_id'],'minimum':row['minimum'],
            'maximum':row['maximum'],'source_basis':row['source_basis'],'source_unit':row['unit'],
            'lower_daily_factor':lo_factor,'upper_daily_factor':hi_factor,'output_unit_factor':scale,
            'upper_applicability':row['upper_applicability_source'],
            'source_id':row['source_id'],'source_locator':row['source_locator']})
        if evidence['evidence_status']=='VERIFIED':
            if row['minimum'] is not None:
                val=row['minimum']*lo_factor*scale;item['target_min']=max(item['target_min'] or 0,val)
            if row['maximum'] is not None:
                val=row['maximum']*hi_factor*scale;item['target_max']=min(item['target_max'] if item['target_max'] is not None else val,val)
    for item in grouped.values():
        unknown=bool(item['unquantified_food_ids'])
        verified=all(x['evidence_status']=='VERIFIED' for x in item['evidence'])
        item['food_contribution_estimate']=None if unknown else item['food_known_subtotal']
        item['target_amount']=item['target_min']
        item['additional_amount_needed']=None if unknown or not verified or item['target_min'] is None else max(0,item['target_min']-item['food_known_subtotal'])
        item['known_contribution_gap']=None if item['target_min'] is None else max(0,item['target_min']-item['food_known_subtotal'])
        item['additional_upper_headroom']=None if unknown or not verified or item['target_max'] is None else max(0,item['target_max']-item['food_known_subtotal'])
        item['calculation_status']='NEEDS_EVIDENCE' if not verified else 'NEEDS_DATA' if unknown else 'REFERENCE_ESTIMATE'
        item['food_covers_reference_minimum']=item['target_min'] is not None and item['food_known_subtotal']>=item['target_min']-1e-8
        item['target_conflict']=item['target_min'] is not None and item['target_max'] is not None and item['target_min']>item['target_max']+1e-8
    # Mineral targets must be jointly feasible. Complete phosphorus changes the
    # calcium target too; never recommend calcium against an obsolete P total.
    ca,p=grouped.get('calcium'),grouped.get('phosphorus')
    ratios=[r for r in audit['rows'] if r['source_basis']=='RATIO']
    ratio_evidence=[source_record(store,r['source_id'],'RATIO',r['source_locator']) for r in ratios]
    ratios_verified=bool(ratios) and all(e['evidence_status']=='VERIFIED' for e in ratio_evidence)
    if ca and not ratios_verified:
        ca['calculation_status']='NEEDS_EVIDENCE';ca['additional_amount_needed']=None
        ca['applicability_note']='钙磷比例的适用依据未核验，暂不计算额外钙剂量。'
    if ca:ca['evidence']+=ratio_evidence
    if ca and p and ratios_verified and ca['calculation_status']==p['calculation_status']=='REFERENCE_ESTIMATE':
        ratio_min=max((r['minimum'] for r in ratios if r['minimum'] is not None),default=0)
        ratio_max=min((r['maximum'] for r in ratios if r['maximum'] is not None),default=float('inf'))
        pf=max(p['food_known_subtotal'],p['target_min'] or 0,ca['food_known_subtotal']/ratio_max)
        cf=max(ca['food_known_subtotal'],ca['target_min'] or 0,ratio_min*pf)
        pf=max(pf,cf/ratio_max)
        cf=max(cf,ratio_min*pf)
        ca['target_min']=max(ca['target_min'] or 0,ratio_min*pf)
        p['target_min']=max(p['target_min'] or 0,cf/ratio_max)
        for item,amount in [(ca,cf),(p,pf)]:
            item['target_amount']=amount;item['additional_amount_needed']=amount-item['food_known_subtotal']
            item['target_conflict']|=item['target_max'] is not None and amount>item['target_max']+1e-8
        # Ratio upper is coupled to final P, not an independent arbitrary dose.
        ca['target_max']=min(ca['target_max'] if ca['target_max'] is not None else float('inf'),ratio_max*pf)
        ca['additional_upper_headroom']=max(0,ca['target_max']-ca['food_known_subtotal'])
        ca['calcium_phosphorus_check']={'food_calcium_mg':ca['food_known_subtotal'],
            'food_phosphorus_mg':p['food_known_subtotal'],'planned_total_calcium_mg':cf,
            'planned_total_phosphorus_mg':pf,'ratio_min':ratio_min,'ratio_max':ratio_max,
            'planned_ratio':cf/pf,'requires_phosphorus_completion':p['additional_amount_needed']>1e-8,
            'status':'CONFLICT' if ca['target_conflict'] or p['target_conflict'] else 'REFERENCE_TARGETS_COMPATIBLE'}
    # A wet-commercial taurine starting level is not a validated home-cooking
    # retention model. Keep its total reference, explicitly withhold exact top-up.
    if 'taurine' in grouped and state['raw']['pet']['species']=='CAT':
        item=grouped['taurine'];item['applicability_note']='FEDIAF 湿粮牛磺酸参考水平用于规划；家用烹调和食品背景的精确适用性待核验。'
        item['confidence_level']='LIMITED';item['additional_amount_needed']=None
        item['calculation_status']='NEEDS_EVIDENCE' if item['calculation_status']=='REFERENCE_ESTIMATE' else item['calculation_status']
    return list(grouped.values())


def recommendations(state, store, matrix):
    if not state['raw']['daily_foods']:return []
    pet=state['raw']['pet'];diseases=state['raw']['disease_advice']['diseases']
    def needed(x):
        return x['target_min'] is not None and (not x['food_covers_reference_minimum'] or (x['additional_amount_needed'] or 0)>1e-8)
    groups=[('CALCIUM',[x for x in matrix if x['nutrient_id']=='calcium']),
            ('TAURINE',[x for x in matrix if x['nutrient_id']=='taurine'] if pet['species']=='CAT' else []),
            ('OMEGA3_EPA_DHA',[x for x in matrix if x['nutrient_id']=='epa_dha']),
            ('VITAMIN_MINERAL',[x for x in matrix if x['nutrient_id'] in REMINDER_NUTRIENTS-{'calcium','taurine','epa_dha','ca_p','ca_p_ratio'}])]
    result=[]
    for kind,rows in groups:
        rows=[x for x in rows if needed(x)]
        if not rows:continue
        bundle=kind=='VITAMIN_MINERAL'
        def values(key):return {r['nutrient_id']:{'amount':r[key],'unit':r['unit']} for r in rows} if bundle else rows[0][key]
        unknown=any(r['calculation_status']!='REFERENCE_ESTIMATE' for r in rows)
        titles={'CALCIUM':'补足元素钙并核对钙磷平衡','TAURINE':'确保牛磺酸的稳定来源','OMEGA3_EPA_DHA':'关注 EPA+DHA 的有效含量','VITAMIN_MINERAL':'补足这份食材组合的微量营养来源'}
        why={'CALCIUM':'这份食物组合的元素钙参考贡献不足，或需随最终磷总量一起调整钙磷平衡。',
             'TAURINE':'猫需要稳定的牛磺酸来源；当前食品和家用烹调数据不能证明这份饭已覆盖适用需求。',
             'OMEGA3_EPA_DHA':'当前生命阶段有适用的 EPA+DHA 参考要求，食物贡献尚不能稳定覆盖；鱼油总重量不能替代有效成分量。',
             'VITAMIN_MINERAL':'这组日常食材尚不能稳定覆盖矩阵所列维生素和矿物质；需落实逐项营养来源，不能仅凭产品名称判断完整性。'}
        disease_relevance=[]
        for d in state['result'].get('disease_adaptations',[]) if 'result' in state else state['raw']['disease_advice'].get('disease_adaptations',[]):
            sid=d.get('source_id');did=d['disease_id']
            scope=('肾脏饮食核对钙磷与额外矿物来源；不是磷结合剂或肾脏治疗目标。' if did in {'CKD','PLN'} else
                   '额外油脂和载体必须计入脂肪及能量上限。' if did in {'PANCREATITIS_DOG','HYPERLIPIDEMIA'} else
                   '营养来源应符合已应用的食材禁忌和饮食安排；没有仅凭诊断追加补剂剂量。')
            disease_relevance.append({'disease_id':did,'message':scope,'evidence_source_ids':[sid] if sid else [],'disease_specific_dose_established':False})
        refs=[e for r in rows for e in r['evidence']]
        result.append({'supplement_type':kind,'active_nutrient':'MICRONUTRIENT_MATRIX' if bundle else {'CALCIUM':'ELEMENTAL_CALCIUM','TAURINE':'TAURINE','OMEGA3_EPA_DHA':'EPA_DHA'}[kind],
            'title':titles[kind], 'why_recommended':why[kind],
            'physiologic_role':ROLES[kind], 'recipe_reason':{'nutrients':[r['nutrient_id'] for r in rows],
                'trigger_conditions':['RECIPE_NUTRIENT_COMPLETION']+(['SPECIES_REQUIREMENT'] if kind=='TAURINE' else []),
                'ingredient_ids':[r['ingredient_id'] for r in state['raw']['daily_foods']]},
            'target_amount':values('target_amount'),'target_min':values('target_min'),'target_max':values('target_max'),
            'target_scope':'TOTAL_DAILY_ACTIVE_NUTRIENT_REFERENCE','unit':'MIXED_SEE_NUTRIENT_MATRIX' if bundle else rows[0]['unit'],'target_basis':'PER_DAY',
            'food_contribution_estimate':values('food_contribution_estimate'),'additional_amount_needed':values('additional_amount_needed'),
            'label_should_show':LABELS[kind],'quality_indicators':quality_indicators(store,kind),
            'disease_relevance':disease_relevance,'evidence_source_ids':sorted({e['source_id'] for e in refs}|{'MSD_NUTRITION2024'}),
            'evidence_level':'NUTRIENT_REQUIREMENT','confidence_level':'LIMITED' if unknown else 'REFERENCE_ESTIMATE',
            'calculation_status':'NEEDS_DATA_OR_APPLICABILITY_REVIEW' if unknown else 'REFERENCE_TARGET_CALCULATED',
            'user_message':'支持满足这份饭的营养需要。目标是有效营养成分，不是产品克数或粒数；' + ('部分食物含量或适用证据尚不完整，不能把未知当作零或据此确定精确添加量。' if unknown else '额外有效成分为本次整餐计算的参考补足量，换食材、产品或份量后应重算。'),
            'mineral_pair_note':('钙目标假设同时落实矩阵中的磷目标，不能只添加钙而忽略磷。' if kind=='CALCIUM' and rows[0].get('calcium_phosphorus_check',{}).get('requires_phosphorus_completion') else None),
            'not_recommended_when':['食物或已纳入整餐的来源已满足同一营养目标','产品成分或单位不清楚','叠加后超过营养上限或与禁忌/疾病要求冲突'],
            'nutrient_matrix':deepcopy(rows),'commercial_product_dose':None})
    return result
