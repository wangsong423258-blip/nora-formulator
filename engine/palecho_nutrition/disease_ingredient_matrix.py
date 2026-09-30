"""Evidence-directed selection cautions. Nutrient concerns are not food bans.

Rows are species/stage specific; quantitative unknowns stay unknown. This is
an operational evidence matrix, not a validated clinical sensitivity study.
"""

def rows_for(profile,pet,advice,registry):
    diseases=set(advice['diseases']);sp=pet['species'];rows=[]
    diagnosed={d['disease_id']:d for d in profile.get('diseases',[])}
    mmvd=profile.get('clinical_nutrition',{}).get('mmvd_stage') or diagnosed.get('MMVD',{}).get('stage') or 'UNKNOWN'
    def add(did,stage,nutrients,code,message,source,applicability,categories=None):
        rows.append(dict(disease=did,species=sp,stage=stage or 'UNKNOWN',life_stage=profile.get('life_stage'),
          nutrients=nutrients,eligibility='CAUTION',reason_code=code,message=message,source_ids=[source],
          evidence_level='GUIDELINE_OR_EXPERT_CONSENSUS',applicability=applicability,
          categories=categories or [],unit='QUALITATIVE_DIRECTION',basis='WHOLE_DIET_INDIVIDUAL_REVIEW',
          numeric_limit=None,does_not_authorize_food_ban=True))
    for did in sorted(diseases):
        stage=diagnosed.get(did,{}).get('stage') or 'UNKNOWN'
        if did in {'CKD','PLN'}:
            add(did,stage,['phosphorus','protein','potassium'],'RENAL_STAGE_REVIEW',
              '按肾病分期、血磷和摄入情况复核。早期不自动套用晚期限制；不要自行加钾、钙或磷。',
              'IRIS_DOG2026' if sp=='DOG' else 'IRIS_CAT2026','CKD_STAGE_AND_LAB_DEPENDENT')
        elif did in {'MMVD','DCM','HCM','CHF'}:
            add(did,mmvd if did=='MMVD' else stage,['sodium','energy'],'CARDIAC_STAGE_REVIEW',
              '心脏病分期决定限钠强度；摄入与体况同样重要。分期未知时不把食材直接禁用。',
              'ACVIM_MMVD2019' if sp=='DOG' else 'ACVIM_CARDIOMYOPATHY_CAT2020','MMVD_B2_MILD_C_D_INDIVIDUALIZED_NO_A_B1_RESTRICTION')
        elif did in {'LIVER_CHRONIC','BILIARY','HEPATIC_LIPIDOSIS','PSS','HEPATIC_ENCEPHALOPATHY','COPPER_HEPATOPATHY'}:
            add(did,stage,['copper'] if did=='COPPER_HEPATOPATHY' else ['protein','energy'],'HEPATOBILIARY_INDIVIDUAL_REVIEW',
              '肝胆疾病不等于统一禁肉或限蛋白；铜相关病、肝性脑病及摄入不足需要分别管理。',
              'ACVIM_HEPATITIS_DOG2019' if sp=='DOG' else 'MERCK_DISEASE_NUTRITION','CONFIRMED_DIAGNOSIS_NO_GENERAL_PROTEIN_RESTRICTION')
        elif did in {'STRUVITE','CALCIUM_OXALATE','URATE','CYSTINE','SILICA','UROLITH_UNKNOWN','FIC'}:
            source='MERCK_UROLITH_DOG2025' if sp=='DOG' else 'MERCK_UROLITH_CAT2025'
            messages={
              'STRUVITE':'溶石期间需遵循完整的处方饮食；普通鲜食不能证明达到溶石所需的尿液条件。',
              'CALCIUM_OXALATE':'草酸钙结石不能靠食物溶解；需水分及尿液监测，不自行极端限钙或酸化尿液。',
              'URATE':'尿酸盐结石需评估嘌呤摄入；当前食品记录缺少嘌呤定量，不能证明本组合为低嘌呤方案。',
              'CYSTINE':'胱氨酸结石需个体化蛋白及尿液管理，不能由普通食品矿物值推断尿液pH。',
            }
            add(did,stage,['water','purines'] if did=='URATE' else ['water','urine_pH'],
              'STONE_SUBTYPE_REVIEW',messages.get(did,'先确认泌尿诊断与结石类型；不套用另一结石的酸化、限矿物或补剂方案。'),source,
              'DISSOLUTION_VS_PREVENTION_REQUIRE_CLINICAL_CONTEXT')
        elif did in {'OBESITY','DIABETES_DOG','DIABETES_CAT'}:
            source='AAHA_DIABETES_'+sp+'2026' if did.startswith('DIABETES') else 'AAHA_NUT2021'
            add(did,stage,['energy','carbohydrate','fiber'],'METABOLIC_INTAKE_REVIEW',
              '按体况及共病安排总热量与餐次。糖尿病沿用医嘱用药及进餐安排，不能因换食自行调整药物。',source,
              'BCS_AND_COMORBIDITY_DEPENDENT')
        elif did in {'PANCREATITIS_DOG','PANCREATITIS_CAT','HYPERLIPIDEMIA'}:
            add(did,stage,['fat'],'PANCREAS_SPECIES_REVIEW',
              '需核算整餐脂肪和能量；猫没有直接套用犬的脂肪硬限。急性症状另走临床分流。',
              'MERCK_PANC' if sp=='DOG' else 'ACVIM_PANCREAS_CAT2021','STABLE_PATIENT_WITH_INDIVIDUAL_TOLERANCE')
        elif did in {'CIE_DOG','CIE_CAT','EPI','PLE','CHRONIC_DIARRHEA','CONSTIPATION','FOOD_ALLERGY','FOOD_INTOLERANCE'}:
            add(did,stage,['fiber','fat','protein'],'GI_TRIAL_REVIEW',
              '按既往耐受和饮食试验选择；已确认过敏或不耐受须登记具体食材，不能仅凭疾病名称猜测过敏原。',
              'ACVIM_CIE2026' if sp=='DOG' else 'MERCK_GI','INDIVIDUAL_DIET_TRIAL_HISTORY_REQUIRED')
    for row in rows:
        did=row['disease'];stage=row['stage']
        row.update(reason=row['message'],stage_or_subtype=stage if stage!='UNKNOWN' else did,
                   nutrient_basis={'nutrients':row['nutrients'],'direction':'INDIVIDUAL_REVIEW','basis':'WHOLE_RECIPE_PREDICTED_ME_WHERE_NUMERIC'},
                   minimum=None,maximum=None,target=None,clinical_eligibility='CAUTION',
                   evidence_gap=None,required_context=['Diagnosis, current clinical stability and existing treatment diet'])
        if did=='CKD':
            row['nutrient_basis']['direction']='LOWER_PHOSPHORUS_PRESERVE_INTAKE' if stage in {'2','3','4'} else 'LAB_AND_STAGE_REVIEW_NO_AUTOMATIC_LATE_STAGE_RESTRICTION'
            row['required_context']+=['IRIS stage','Serum phosphorus and potassium','Proteinuria and nutritional status']
        elif did=='MMVD' and stage in {'A','B1'} or did=='HCM':
            row.update(eligibility='ENABLED',clinical_eligibility='ENABLED')
            row['nutrient_basis']['direction']='NO_DIAGNOSIS_ONLY_SODIUM_RESTRICTION'
        elif did in {'MMVD','CHF','DCM'}:
            row['nutrient_basis']['direction']='MILD_SODIUM_RESTRICTION' if stage=='B2' else 'INDIVIDUAL_SODIUM_AND_INTAKE_REVIEW'
        elif did=='PANCREATITIS_DOG':
            row.update(maximum={'nutrient':'fat','value':20,'unit':'g/1000_kcal_predicted_ME','inclusive':False})
            row['nutrient_basis']['direction']='LOW_FAT_FINAL_MIXTURE_LIMIT'
        elif did=='PANCREATITIS_CAT':
            row['nutrient_basis']['direction']='ADEQUATE_INTAKE_TOLERANCE_NO_CANINE_FAT_CAP'
            row['evidence_gap']='ACVIM 2021 finds no evidence requiring fat restriction; Merck 2025 suggests moderate fat. No universal feline numerical cap.'
        elif did=='DIABETES_CAT':
            row['target']={'nutrient':'carbohydrate','value':'<12–15% ME or <3 g/100 kcal','unit':'PUBLISHED_PREFERENCE_NOT_HARD_FOOD_BAN'}
            row['nutrient_basis']['direction']='LOWER_CARBOHYDRATE_PRESERVE_PROTEIN_AND_INTAKE'
        elif did=='DIABETES_DOG':row['nutrient_basis']['direction']='CONSISTENT_INTAKE_FIBER_INDIVIDUALIZED_NO_FELINE_CARB_CAP'
        elif did=='OBESITY':row['nutrient_basis']['direction']='CONTROL_ENERGY_PRESERVE_LEAN_MASS_NO_FOOD_GROUP_BAN'
        elif did=='COPPER_HEPATOPATHY' and sp=='DOG':
            row['maximum']={'nutrient':'copper','value':1.2,'unit':'mg/1000_kcal_predicted_ME','inclusive':False}
            row['nutrient_basis']['direction']='CONFIRMED_COPPER_ASSOCIATED_HEPATITIS_RESTRICT_COPPER'
            row['required_context']+=['Confirmed copper-associated hepatitis; ACVIM numerical recommendation refers to hepatic copper >600 microgram/g dry weight']
        elif did in {'LIVER_CHRONIC','BILIARY'}:row['nutrient_basis']['direction']='NO_GENERAL_PROTEIN_RESTRICTION'
        elif did=='URATE':
            row['nutrient_basis']['direction']='LOW_PURINE_INDIVIDUAL_PLAN'
            row['evidence_gap']='No authoritative same-state purine concentrations in these food records; low-purine composition cannot be certified.'
        elif did=='CALCIUM_OXALATE':
            row['nutrient_basis']['direction']='WATER_AVOID_EXCESS_OXALATE_NO_EXTREME_CALCIUM_RESTRICTION'
            row['evidence_gap']='No same-state oxalate measurements or urinary RSS prediction.'
        elif did=='STRUVITE':row['nutrient_basis']['direction']='PRESERVE_DISSOLUTION_PLAN_NO_EMPIRICAL_ACIDIFIER'
        elif did=='CYSTINE':row['nutrient_basis']['direction']='INDIVIDUAL_PROTEIN_SODIUM_URINE_MANAGEMENT'
        elif did in {'FOOD_ALLERGY','FOOD_INTOLERANCE'}:row['nutrient_basis']['direction']='EXCLUDE_DOCUMENTED_TRIGGER_ONLY'
        elif did in {'CIE_DOG','CIE_CAT','EPI','PLE','CHRONIC_DIARRHEA','CONSTIPATION'}:
            row['nutrient_basis']['direction']='INDIVIDUAL_DIET_TRIAL_TOLERANCE_NO_UNIVERSAL_FIBER_TARGET'
        sources=[registry['sources'][sid] for sid in row['source_ids']]
        row['source']=[{'id':s['source_id'],'url':s['url']} for s in sources]
        row['version']={s['source_id']:s['version'] for s in sources}
        row['year']={s['source_id']:s.get('publication_year') for s in sources}
    return rows
