"""Build-time data, evidence, dimensional and clinical integrity gates."""
import copy, hashlib, json
from pathlib import Path
from datetime import date
from .master import SCHEMA, MasterError
from .units import BASES, convert_unit, convert_basis, number
from .requirements import EXPECTED_PROFILES, REQUIRED_NUTRIENTS_BY_SPECIES, GROWTH_EXTRA, CONDITIONAL_NUTRIENTS_BY_SPECIES, profile_coverage_issues

def require(ok,message):
    if not ok:raise MasterError(message)

def index(t,name,key):return {r[key]:r for r in t[name]}

def validate_master(t):
    require(set(t)==set(SCHEMA),'Sheet mismatch')
    for name,spec in SCHEMA.items():
        rows=t[name];pk=spec['pk'];seen=set()
        require(bool(rows),name+' empty')
        for r in rows:
            require(set(r)==set(spec['columns']),name+' columns mismatch')
            require(isinstance(r[pk],str) and r[pk] not in seen and bool(r[pk]),name+' empty/duplicate key')
            seen.add(r[pk])
            for c,kind in spec['columns'].items():
                v=r[c]
                if v is None:continue
                if kind=='BOOLEAN':require(type(v) is bool,f'{name}.{c} must be boolean')
                elif kind=='REAL':number(v)
                else:require(isinstance(v,str),f'{name}.{c} must be text')
                if c.endswith('_json'):
                    try:json.loads(v,parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
                    except (ValueError,TypeError) as e:raise MasterError(f'{name}.{c} invalid JSON: {e}')
            require(bool(r.get('source_id')),name+' missing source_id')
    require(len(t['18_Versions'])==1,'One active version required')
    require(t['18_Versions'][0]['schema_version']==6,'Unsupported schema version')
    ids={name:{r[spec['pk']] for r in t[name]} for name,spec in SCHEMA.items()}
    fks={'nutrient_id':'01_Nutrients','ingredient_id':'08_Ingredients','disease_id':'05_Diseases','cooking_method_id':'12_Cooking_Methods'}
    for name,rows in t.items():
        for r in rows:
            for field,table in fks.items():
                if field in r and r[field] is not None:
                    require(r[field] in ids[table],f'{name}: unresolved {field} {r[field]}')
    evidence={(r['table_name'],r['row_id']):r for r in t['16_Evidence_Map']}
    require(len(evidence)==len(t['16_Evidence_Map']),'Duplicate evidence edges')
    for name,rows in t.items():
        if name in ['15_Sources','16_Evidence_Map']:continue
        for r in rows:
            k=(name,r[SCHEMA[name]['pk']]);e=evidence.get(k)
            require(e is not None and e['source_id']==r['source_id'],f'Missing/mismatched evidence {k}')
    for e in t['16_Evidence_Map']:
        require(e['table_name'] in ids and e['row_id'] in ids[e['table_name']],'Orphan evidence edge')
    validate_user_supplement_policy(t)
    return {'status':'PASS','rows':sum(map(len,t.values()))}

def normalize_units(t):
    t=copy.deepcopy(t);nut=index(t,'01_Nutrients','nutrient_id');changes=0
    for name,fields in [('02_Requirements',['minimum','maximum']),('09_Ingredient_Nutrients',['value']),('06_Disease_Rules',['value'])]:
        for r in t[name]:
            if not r['nutrient_id']:continue
            canonical=nut[r['nutrient_id']]['canonical_unit']
            require(r['basis'] in BASES,f'{name}: unknown/ambiguous basis')
            if r['unit']!=canonical:changes+=1
            for f in fields:r[f]=convert_unit(r[f],r['unit'],canonical)
            r['unit']=canonical
            require(bool(r['food_state']),f'{name}: missing food_state')
    return t,{'status':'PASS','unit_conversions':changes,'basis_policy':'No implicit energy/moisture conversion'}

def validate_sources(t,root):
    sources=index(t,'15_Sources','source_id');hashes=0
    for s in sources.values():
        require(all(s.get(k) for k in ['organization','title','version','URL','access_date','source_type','evidence_level','read_status']),'Incomplete source '+s['source_id'])
        date.fromisoformat(s['access_date'])
        require(s['URL'].startswith(('https://','local://')),'Source URL must be https/local')
        if s['local_file']:
            p=(Path(root)/s['local_file']).resolve()
            require(p.is_relative_to(Path(root).resolve()),'Source archive must stay inside the project')
            require(p.is_file(),'Missing archived source '+str(p))
            require(hashlib.sha256(p.read_bytes()).hexdigest()==s['sha256'],'Source SHA256 mismatch '+s['source_id']);hashes+=1
    for name,rows in t.items():
        for r in rows:
            for field in ('source_id','source_A','source_B','additional_source_id','market_source_id','policy_source_id','retention_source_id','assay_source_id'):
                if r.get(field):require(r[field] in sources,'Unresolved source '+str(r[field]))
            # Unknown fields may cite the record whose absence was checked, but never supply numbers from unread sources.
            if name in ['02_Requirements','06_Disease_Rules','09_Ingredient_Nutrients','20_Supplement_Nutrients'] and any(r.get(f) is not None for f in ('minimum','maximum','value','guaranteed_min','guaranteed_max','typical_value','actual_value')):
                require(sources[r['source_id']]['read_status'] not in ['BIBLIOGRAPHY_ONLY','NEEDS_REVIEW','ABSTRACT_ONLY'],'Numeric claim cites unread source')
                require(sources[r['source_id']]['source_type']!='PROJECT_POLICY','Engineering policy cannot invent nutritional composition/targets')
                require(bool(r.get('source_locator')),'Numeric claim missing source locator')
                if name=='09_Ingredient_Nutrients' and r['nutrient_id'] in ['vitamin_a_dog','vitamin_a_cat','vitamin_d3_activity','vitamin_e']:
                    require(bool(r.get('additional_source_id')),'Derived vitamin activity requires its conversion source')
                if r.get('additional_source_id'):
                    additional=sources[r['additional_source_id']]
                    require(additional['read_status'] not in ['BIBLIOGRAPHY_ONLY','NEEDS_REVIEW','ABSTRACT_ONLY'] and additional['source_type']!='PROJECT_POLICY','Numeric derivation cites unread or non-nutritional source')
    return {'status':'PASS','sources':len(sources),'archived_hashes_verified':hashes,
            'unreviewed_sources':[s['source_id'] for s in sources.values() if s['read_status'] in ['NEEDS_REVIEW','BIBLIOGRAPHY_ONLY']]}

def validate_practical_references(t):
    """A V1 label/reference can be usable without becoming an Advanced approval."""
    sources=index(t,'15_Sources','source_id');nutrients=index(t,'01_Nutrients','nutrient_id');references=labels=0
    def archived_source(sid):
        require(sid in sources and sources[sid]['local_file'] and sources[sid]['sha256'],'V1 numerical evidence needs a source archive')
        return sources[sid]
    def label_numbers(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key.endswith('_source_id') or key=='source_id':
                    if item is not None:archived_source(item)
                elif key.endswith('_source_ids') and item is not None:
                    for sid in item:archived_source(sid)
                label_numbers(item)
        elif isinstance(value,list):
            for item in value:label_numbers(item)
        elif type(value) in (int,float):number(value,nonnegative=True)
    policy=json.loads(t['18_Versions'][0]['runtime_config_json'])['practical_v1']
    method=policy['junior_energy_envelope_method']
    require(method.get('method_id')=='JUNIOR_DECLARED_INORGANIC_MASS_REFERENCE_V1' and bool(method.get('version')),'Unrecognized Junior reference envelope method')
    require(method.get('classification')=='NOMINAL_LABEL_MIXTURE_REFERENCE_ENERGY_ENVELOPE_NOT_ME','Junior label-mixture envelope must not be measured ME')
    require(all(method.get(k) is False for k in ['advanced_eligible','measured_energy','nutrient_values_changed','unknowns_to_zero']),'Energy envelope cannot certify Advanced energy or rewrite nutrients')
    require(bool(method.get('applicability')) and bool(method.get('limitations')) and bool(method.get('equation')),'Energy envelope requires applicability, equation and limitations')
    chemical_ids=method.get('chemical_source_ids',[])
    require(set(chemical_ids)=={'V1_JECFA_DICALCIUM_FORMULA','V1_NIST_CALCIUM_CARBONATE','V1_NIST_ATOMIC_CA','V1_NIST_ATOMIC_P','V1_NIST_ATOMIC_O','V1_NIST_ATOMIC_C'},'Energy envelope lacks the scoped chemical evidence')
    for sid in chemical_ids:
        source=archived_source(sid)
        require(source['source_type']=='OFFICIAL_CHEMICAL_REFERENCE' and source['read_status']=='RELEVANT_SECTIONS_READ','Energy envelope chemical source unread or unofficial')
    label=archived_source(method['label_source_id'])
    require(method.get('label_archive_sha256')==label['sha256'],'Energy envelope label archive mismatch')
    junior=next((json.loads(r['v1_spec_json']) for r in t['14_Supplements'] if r['supplement_id']=='V1_NAPF_JUNIOR'),{})
    require(method.get('required_label_amount_per_g')==junior.get('amount_per_g'),'Energy envelope must cover the complete archived nominal nutrient declaration')
    label_numbers(method)
    from .sources_energy_envelope import junior_reference_envelope
    elements=sum(junior.get('amount_per_g',{}).get(k,0) for k in ['calcium','phosphorus','sodium','potassium','magnesium','chloride'])
    # The sum includes only explicitly declared elemental masses. Absent terms
    # contribute no lower-mass credit; this does not create nutrient zeros.
    envelope=junior_reference_envelope(junior,method,elements)
    require(envelope is not None,'Junior envelope carrier/form/label applicability mismatch')
    require(0<=envelope['low_kcal_per_g']<=envelope['high_kcal_per_g']<=9 and envelope['not_a_batch_guaranteed_energy_bound'] is True,'Invalid qualified reference envelope')
    legal=policy['eu_legal_maximum_policy']
    archived_source(legal['source_id'])
    require(legal['source_id']=='FEDIAF2025' and bool(legal.get('source_locator')),'V1 legal applicability requires FEDIAF evidence')
    require(legal.get('trigger')=='SAME_NUTRIENT_DECLARED_ADDITION' and legal.get('trigger_amount')=='POSITIVE_ACTUAL_SELECTED_SUPPLEMENT_DOSE','V1 legal maximum requires the particular nutrient to be added')
    require(legal.get('comparison_scope')=='TOTAL_FOOD_PLUS_SUPPLEMENT_NUTRIENT' and legal.get('food_only')=='AUDIT_LEGAL_REFERENCE_ENFORCE_NUTRITIONAL_MAXIMUM_IF_PRESENT','V1 legal applicability must retain total-content and nutritional-maximum checks')
    require(legal.get('other_nutrient_addition_triggers') is False and legal.get('advanced_enforcement_unchanged') is True,'V1 legal policy cannot affect other nutrients or Advanced enforcement')
    liver=policy['small_liver_inclusion_policy']
    require(liver.get('ingredient_id')=='FDC_171061' and liver.get('food_state')=='SIMMERED','V1 small liver scope must match the existing cooked identity')
    require(liver.get('max_cooked_food_mass_fraction')==0.05 and liver.get('max_reference_food_energy_fraction')==0.05,'V1 liver design cap changed without policy migration')
    require(set(liver.get('required_resolved_nutrients',[]))=={'vitamin_a','copper'} and liver.get('required_nutrients_resolved_before_use') is True,'V1 liver use cannot bypass unknown A/Cu')
    require(liver.get('guardrail_type')=='PROJECT_DESIGN_PORTION_CAP_NOT_TOXICOLOGICAL_UPPER_LIMIT' and liver.get('advanced_exclusion_unchanged') is True,'V1 liver portion cap is not a toxicological upper limit or Advanced approval')
    context=liver['vitamin_d_qualitative_context'];source=archived_source(context['source_id'])
    require(context.get('ingredient_id')=='FDC_171061' and context.get('source_sha256')==source['sha256'] and context.get('source_locator'),'Liver D context must have exact archived food identity and locator')
    require(liver.get('qualitative_reference')==context.get('qualitative_context')=='DATABASE_ASSUMED_NEGLIGIBLE_NOT_MEASURED_OR_BOUND','Liver D context is qualitative source interpretation only')
    require(context.get('runtime_numeric_contribution') is None and context.get('runtime_upper_bound') is None and context.get('preserve_advanced_null') is True,'Assumed-zero source must not become a measured concentration or upper bound')
    require(liver.get('vitamin_d_minimum_credit_allowed') is False and liver.get('vitamin_d_minimum_must_be_met_from_other_sources') is True and liver.get('vitamin_d_upper_background_audit')=='UNQUANTIFIED_FUTURE_REFINEMENT_WITH_SMALL_PORTION_POLICY','Small liver policy must retain D minimum exclusion and explicit unknown upper background')
    for row in t['09_Ingredient_Nutrients']:
        require(row['data_precision'] in {'HIGH_CONFIDENCE','REFERENCE_ESTIMATE','LIMITED','REJECTED'},'Unknown food precision level')
        if not row['v1_reference_json']:continue
        ref=json.loads(row['v1_reference_json']);references+=1
        require(ref.get('v1_candidate_usable') is True,'Unaccepted V1 food reference')
        require(ref.get('candidate_status')=='REFERENCE_ESTIMATE_OK' and ref.get('confidence')=='REFERENCE_ESTIMATE','V1 food reference status not accepted')
        require(ref.get('ingredient_id')==row['ingredient_id'] and ref.get('canonical_storage_nutrient')==row['nutrient_id'],'V1 reference identity mismatch')
        require(ref.get('source_id') in sources and bool(ref.get('source_locator')),'V1 food reference lacks evidence')
        source=archived_source(ref['source_id'])
        if ref.get('source_sha256'):require(ref['source_sha256']==source['sha256'],'V1 food source archive hash mismatch')
        require(source['source_type'] in {'NATIONAL_FOOD_DATABASE','OFFICIAL_FOOD_DATABASE','DATABASE','PEER_REVIEWED_ANALYSIS'},'V1 food representative must be sourced nutrition data')
        require(source['read_status'] in {'RELEVANT_SECTIONS_READ','FULL_RELEVANT_SECTIONS_READ'},'V1 food numeric reference source unread')
        require(ref.get('basis')=='PER_100G_AS_FED_EDIBLE_COOKED' and row['food_state'] not in ['RAW','AS_SOLD'],'V1 cooked reference state mismatch')
        number(ref.get('value'),nonnegative=True)
        require(ref.get('unit') in {'g','mg','ug','kcal','IU'},'V1 food reference unit unknown')
        convert_unit(ref['value'],ref['unit'],row['unit'])
        if ref.get('food_state'):require(ref['food_state']==row['food_state'],'V1 food cooking method mismatch')
        if ref.get('method_match') in {'COOKED_LEAN_BEEF_CUT_PROXY','ROASTED_CHICKEN_LIGHT_MEAT_PROXY','MATCHED_ROASTED_CHICKEN_LIGHT_MEAT_REPRESENTATIVE'}:
            require(row['food_state']=='ROASTED' and ref.get('advanced_eligible') is False and bool(ref.get('restriction')) and bool(ref.get('identity_match')),'Cooked meat proxy must retain explicit identity/state limitations')
        if ref.get('method_match')=='MATCHED_BOILED_WHOLE_EGG_REPRESENTATIVE':
            require(row['ingredient_id']=='FDC_173424' and row['food_state']=='HARD_BOILED' and row['nutrient_id'] in {'arachidonic','chloride'},'Boiled whole egg reference cannot map another food, cooking state or nutrient')
            require(ref.get('advanced_eligible') is False and bool(ref.get('restriction')) and ref.get('identity_match')=='SAME_SPECIES_WHOLE_EGG_BOILED_REPRESENTATIVE','Egg representative retains identity and Advanced limits')
            if row['nutrient_id']=='arachidonic':
                require(ref.get('original_source',{}).get('column_header')=='cis n-6 C20:4 /100g food (g)','Unspecified total 20:4 cannot become arachidonic acid')
        if ref.get('method_match')=='MATCHED_EXISTING_COOKED_FOOD_CHLORIDE_REPRESENTATIVE':
            allowed={('FDC_170440','BOILED_DRAINED','13-490'),('FDC_169967','BOILED_DRAINED','13-503'),
                     ('FDC_170394','BOILED_DRAINED','13-497'),('FDC_169976','BOILED_DRAINED','13-581'),
                     ('FDC_169292','BOILED_DRAINED','13-628'),('FDC_168484','BOILED','13-646'),
                     ('FDC_172411','ROASTED','18-372')}
            require((row['ingredient_id'],row['food_state'],ref.get('original_source',{}).get('food_code')) in allowed and row['nutrient_id']=='chloride','Cooked chloride representative food/cooking/source identity mismatch')
            require(ref.get('advanced_eligible') is False and bool(ref.get('restriction')) and ref.get('identity_match')=='SAME_FOOD_EDIBLE_PORTION_AND_COOKING_REPRESENTATIVE','Cooked chloride representative retains portion and Advanced restrictions')
        require(ref.get('upper_bound') is None and ref.get('not_a_guaranteed_maximum') is True,'Reference mean is not a guaranteed upper bound')
        if ref.get('nutrient')=='vitamin_d_total_human_activity':
            require(row['nutrient_id']=='vitamin_d_total' and ref.get('automatic_pet_vitamin_d_conversion_allowed') is False,'Human D activity cannot become pet D automatically')
    for row in t['14_Supplements']:
        require(type(row['v1_usable']) is bool,'V1 supplement admission must be boolean')
        package=json.loads(row['v1_spec_json'] or '{}')
        require(package.get('supplement_id')==row['supplement_id'],'V1 supplement package identity mismatch')
        if not row['v1_usable']:continue
        labels+=1
        require(package.get('v1_evidence_status')=='ACCEPTED_LABEL_REFERENCE','Rejected supplement cannot be V1 usable')
        require(not any(package.get(k) for k in ['conflict','official_conflict','official_conflicts','unresolved_official_conflict']),'Conflicting official label cannot be admitted')
        require(package.get('source_id')==row['source_id'] and row['source_id'] in sources,'V1 label source mismatch')
        source=archived_source(row['source_id'])
        require(source['source_type']=='OFFICIAL_TECHNICAL_REFERENCE' and source['evidence_level']=='OFFICIAL_LABEL_OR_GUIDELINE','V1 supplement requires official technical label evidence')
        require(package.get('archive_sha256')==source['sha256'],'V1 label archive hash mismatch')
        require(sources[row['source_id']]['read_status']=='RELEVANT_SECTIONS_READ','V1 numeric label source unread')
        require(package.get('product_name') and package.get('species_allowed') and package.get('life_stage_allowed'),'V1 label identity/species/lifecycle absent')
        require(isinstance(package['species_allowed'],list) and set(package['species_allowed'])<={'DOG','CAT'},'V1 supplement species unknown')
        require(isinstance(package['life_stage_allowed'],list) and set(package['life_stage_allowed'])<={'ALL','ADULT','HEALTHY_SENIOR','GROWTH','EARLY_GROWTH','LATE_GROWTH_SMALL_MEDIUM','LATE_GROWTH_LARGE'},'V1 supplement lifecycle unknown')
        require(package.get('evidence_type')=='LABEL_DECLARED' and package.get('actual_concentration') is None,'Label declaration is not actual concentration')
        require(bool(package.get('amount_per_g') or package.get('declared_per_serving')),'V1 label needs exact nutrient amount and unit')
        require(package.get('amount_unit') in {'g','capsule','ml','tablet'},'V1 label unit unknown')
        label_numbers(package)
        for nutrient,value in (package.get('amount_per_g') or {}).items():
            require(nutrient in nutrients,'V1 supplement nutrient unknown')
            number(value,nonnegative=True)
        for record in package.get('nutrient_records',[]):
            nutrient=record.get('nutrient');require(nutrient in nutrients,'V1 supplement record nutrient unknown')
            require(record.get('unit')==nutrients[nutrient]['canonical_unit'] and record.get('basis')=='AS_SOLD_PER_G','V1 nutrient record needs canonical unit and per-g basis')
            number(record.get('amount_per_g'),nonnegative=True)
            require(record.get('actual_value') is None and record.get('evidence_type')=='LABEL_DECLARED','V1 label record cannot claim batch assay')
            if record.get('chemical_form')=='calcium-D-pantothenate':
                require(record.get('active_pantothenic_acid_per_g') is not None and record.get('active_conversion_source_id') in sources,'B5 chemical-form conversion missing')
                require(abs(record['active_pantothenic_acid_per_g']-record['amount_per_g']*record['active_conversion_factor'])<1e-12,'B5 conversion inconsistent')
        for nutrient,record in package.get('declared_per_serving',{}).items():
            require(nutrient in nutrients or nutrient=='fish_oil','V1 serving component unknown')
            require(record.get('unit') in {'g','mg','ug','IU','kcal','ml'},'V1 serving component unit missing')
            number(record.get('value'),nonnegative=True)
            if nutrient=='vitamin_e' and record.get('chemical_form') is None and record['unit']!='IU':
                require(record.get('canonical_IU') is None,'Unspecified vitamin E form cannot silently become IU')
        require(bool(package.get('usage_tables') or package.get('usage_label_note') or package.get('v1_use_scope') or
                     package.get('source_type')=='DEFINED_NUTRIENT_SOURCE' and package.get('usage_rule')),'V1 label usage scope missing')
        if package.get('amount_unit')=='capsule':
            require(package.get('daily_solver_eligible') is False,'Discrete/weekly capsule schedule cannot silently become daily grams')
        require(not row['auto_use_allowed'] and row['review_status']!='APPROVED','V1 label admission cannot confer Advanced approval')
    return {'status':'PASS','food_reference_records':references,'label_admitted_supplements':labels}

def validate_condition(c):
    require(type(c) is dict,'Conditions must be a finite JSON object, never executable code')
    for k,v in c.items():
        require(k in {'breed','subtype','stage','clinical_status','hepatic_copper_dry','obstruction_excluded','swallowing_safe','oral_pain_managed','bromide_use'},'Unsupported condition field '+k)
        if isinstance(v,dict):
            require(set(v)<= {'gt','gte','lt','lte','eq','in'} and bool(v),'Unsupported condition operator')
            for op,n in v.items():
                if op=='in':require(type(n) is list and all(isinstance(x,str) for x in n),'Invalid condition membership')
                else:number(n)
        else:require(isinstance(v,(str,bool)),'Condition equality value must be string/bool')

def validate_disease_rules(t):
    diseases=index(t,'05_Diseases','disease_id');fields={'foods_to_limit','foods_to_avoid','foods_or_patterns_preferred','hydration_notes','feeding_frequency_notes','weight_monitoring','appetite_monitoring','stool_monitoring','vomiting_monitoring','red_flags','reassessment_note'}
    for d in diseases.values():
        require(d['nutrition_effect_level'] in 'ABC','Invalid nutrition_effect_level')
        require(d['species'] in ['DOG','CAT','BOTH'],'Invalid disease species')
        require(type(d['auto_recipe_allowed']) is bool,'Missing disease automation policy')
        require(d['auto_recipe_allowed'] is False and d['production_recipe'] is False,'Disease production is frozen')
        validate_condition(json.loads(d['auto_condition_json']))
        require(type(json.loads(d['clinical_units_json'])) is dict,'Invalid clinical measurement dictionary')
        require(not d['requires_clinical_data'] or bool(d['clinical_fields']),'Missing clinical data specification')
        actual=[r['field'] for r in t['13_Disease_Lifestyle'] if r['disease_id']==d['disease_id']]
        require(set(actual)==fields and len(actual)==len(fields),'Incomplete/duplicate lifestyle field set '+d['disease_id'])
    for r in t['06_Disease_Rules']:
        d=diseases[r['disease_id']];validate_condition(json.loads(r['condition_json']))
        require(r['species'] in [d['species'],'DOG','CAT'] if d['species']=='BOTH' else r['species']==d['species'],'Rule species mismatch')
        require(r['action'] in ['STRATEGY','HARD_MIN','HARD_MAX','ADVISORY_MIN','ADVISORY_MAX'],'Unsupported disease action')
        if r['action'].startswith('HARD'):
            require(d['nutrition_effect_level']!='C','C level disease cannot alter core nutrients')
            require(r['value'] is not None and r['operator'] in ['LT','LE','GT','GE'],'Incomplete hard rule')
            number(r['value'],nonnegative=True)
        if r['action']=='STRATEGY':require(r['value'] is None and bool(r['text_zh']),'Strategy has fake numeric precision')
    for r in t['13_Disease_Lifestyle']:
        require(r['text_zh'] is not None or r['status']=='NEEDS_REVIEW','Blank advice must explicitly need review')
    return {'status':'PASS','diseases':len(diseases),'numeric_hard_rules':sum(r['action'].startswith('HARD') for r in t['06_Disease_Rules']),
            'lifestyle_gaps':sum(r['text_zh'] is None for r in t['13_Disease_Lifestyle'])}

def validate_foods(t):
    practical=validate_practical_references(t)
    foods=index(t,'08_Ingredients','ingredient_id');nut=index(t,'01_Nutrients','nutrient_id');vectors={}
    for r in t['09_Ingredient_Nutrients']:
        f=foods[r['ingredient_id']];key=(r['ingredient_id'],r['nutrient_id'])
        require(key not in vectors,'Duplicate ingredient/nutrient');vectors[key]=r
        require(r['food_state']==f['food_state'],'Raw/cooked/state mismatch '+r['ingredient_id'])
        require(r['basis']=='PER_100G_AS_FED','Ingredient vector must explicitly describe 100 g edible as-fed food')
        if r['value'] is None:require(r['status'].startswith('UNKNOWN'),'NULL must be UNKNOWN')
        else:
            number(r['value'],nonnegative=True)
            require(r['status'] in ['SOURCE_REPORTED','DERIVED_VERIFIED','ASSAY_VERIFIED'],'Numeric status invalid')
            require(r['derivation_code']!='Z','Assumed zero is not an observed zero')
    required={n for n in nut if n!='ca_p_ratio'}
    for f in foods.values():
        if f['toxicity_flag']:
            require(not f['recipe_eligible'],'Toxic food eligible')
            continue
        require({n for i,n in vectors if i==f['ingredient_id']}==required,'Incomplete explicit NULL nutrient vector')
        expected_weight={'RAW':'RAW_WEIGHT','COOKED':'COOKED_WEIGHT','AS_SOLD':'AS_SOLD_WEIGHT'}.get(f['raw_or_cooked'])
        require(f['weight_basis']==expected_weight and f['portion_basis']=='EDIBLE_WEIGHT','Food weighing/state mismatch')
        if f['recipe_eligible']:
            require(f['review_status']=='APPROVED' and f['precision_g'] is not None and f['precision_g']>0,'Eligible food needs reviewed dispensing precision')
            require(f['raw_or_cooked']!='RAW','V1 has no validated raw-to-cooked processing pipeline')
            require(f['max_amount'] is not None and f['max_amount']>0,'Eligible food requires reviewed maximum daily amount')
            require(f['me_method'] and f['assay_scope'],'Eligible food requires reviewed ME/assay provenance')
            for species in ['dog','cat']:
                if f[species+'_allowed']:require(vectors[(f['ingredient_id'],'me_'+species)]['value'] is not None,'Missing species ME')
            require(vectors[(f['ingredient_id'],'water')]['value'] is not None,'Missing water / DM')
        if f['raw_purchase_yield'] is not None:number(f['raw_purchase_yield'],positive=True)
    for r in t['11_Substitution_Groups']:
        require(r['candidate_only'] is True and r['requires_full_resolve'] is True and r['fixed_weight_ratio'] is None,'Fixed-weight substitution prohibited')
    for r in t['10_Ingredient_Limits']:
        require(r['operator'] in ['EXCLUDE','MAX_SHARE','MIN_AMOUNT','MAX_AMOUNT'],'Unsupported ingredient limit operator')
        if r['operator']=='MAX_SHARE':
            require(r['basis'] in ['FRACTION_ME','FRACTION_AS_FED'] and r['unit']=='ratio','Food share basis/units missing')
            require(type(r['value']) in [float,int] and 0<=r['value']<=1,'Share must be a fraction in [0,1]')
        if r['operator'] in ['MIN_AMOUNT','MAX_AMOUNT']:
            require(r['basis']=='PER_DAY' and r['unit']=='g','Ingredient amount limits must be g/day')
            number(r['value'],nonnegative=True)
    from .whole_diet import SOURCE_TYPES
    source_ids={s['source_id'] for s in t['15_Sources'] if s['read_status'] not in ['BIBLIOGRAPHY_ONLY','ABSTRACT_ONLY','NEEDS_REVIEW']}
    for r in t['08_Ingredients']:require(r['source_type']=='FOOD','Food source type mismatch')
    for r in t['09_Ingredient_Nutrients']:
        lo=r.get('lower_bound');hi=r.get('upper_bound')
        if lo is not None or hi is not None:
            for value in [lo,hi]:
                if value is not None:number(value,nonnegative=True)
            require(r.get('bound_source_id') in source_ids and bool(r.get('bound_source_locator')),'Food bounds need read evidence')
            require(lo is None or hi is None or lo<=hi,'Reversed food bounds')
            require(r['value'] is None or (lo is None or lo<=r['value']) and (hi is None or r['value']<=hi),'Point outside food bounds')
    for r in t['14_Supplements']:
        require(r['source_type'] in SOURCE_TYPES-{'FOOD'} and r['model_type']==r['source_type'],'Supplement source type mismatch')
    supplements=index(t,'14_Supplements','supplement_id')
    for r in t['20_Supplement_Nutrients']:
        require(r['supplement_id'] in supplements,'Orphan supplement analysis')
        require(r['basis'] in ['MASS_PERCENT_AS_SOLD','PER_TEASPOON','PER_1G_AS_SOLD'],'Unknown supplement analysis basis')
        require(r['unit'] in ['%','g','mg','ug','IU','kcal'],'Unknown supplement analysis unit')
        require((r['unit']=='%')==(r['basis']=='MASS_PERCENT_AS_SOLD'),'Percentage requires mass-percent basis')
        number(r['serving_mass_g'],positive=True)
        for field in ['guaranteed_min','guaranteed_max','typical_value','actual_value']:
            if r[field] is not None:number(r[field],nonnegative=True)
        kind=r['evidence_type']
        require(kind in ['GUARANTEED_MIN','GUARANTEED_MAX','SPECIFICATION_RANGE','TYPICAL','BATCH_ASSAY','CERTIFIED_POINT'],'Unknown concentration evidence type')
        if kind.startswith('GUARANTEED'):
            require(r['actual_value'] is None and r['typical_value'] is None,'Guarantee cannot provide actual/typical concentration')
            require(r['guaranteed_min' if kind=='GUARANTEED_MIN' else 'guaranteed_max'] is not None,'Missing guarantee value')
        if r['guaranteed_min'] is not None and r['guaranteed_max'] is not None:require(r['guaranteed_min']<=r['guaranteed_max'],'Reversed supplement guarantee bounds')
        if r['actual_value'] is not None:require(kind in ['BATCH_ASSAY','CERTIFIED_POINT'],'Actual concentration lacks point evidence')
    for r in t['14_Supplements']:
        if r['auto_use_allowed']:
            from .supplement_models import require_solver_ready
            package=json.loads(r['evidence_package_json'] or '{}')
            package['nutrient_matrix']=[n for n in t['20_Supplement_Nutrients'] if n['supplement_id']==r['supplement_id']]
            try:require_solver_ready(package)
            except ValueError as exc:raise MasterError(str(exc)) from exc
            require(all(r.get(k) is not None for k in ['precision_g','carrier_allergens','add_after_cooling','amount_per_unit','unit','basis','version','batch_or_spec','species','usage_limit_json','max_daily_amount']),'Supplement lacks specification/usage certificate')
            require(bool(json.loads(r['exact_composition_json'] or r['composition_bounds_json'] or '{}')) and bool(json.loads(r['usage_limit_json'])),'Supplement point/bounded composition or usage missing')
            number(r['amount_per_unit'],positive=True);number(r['precision_g'],positive=True);number(r['max_daily_amount'],positive=True)
            # Standalone defined sources/premixes use table20 directly; they need
            # not masquerade as ordinary food with a fabricated point vector.
            if r['ingredient_id'] is not None:require(r['ingredient_id'] in foods and foods[r['ingredient_id']]['recipe_eligible'],'Supplement ingredient not eligible')
            require(r['review_status']=='APPROVED','Unapproved supplement')
    from .energy_methods import METHOD_IDS
    methods=t['19_ME_Methods']
    require({(m['implementation_id'],m['species']) for m in methods}=={(m,s) for m in METHOD_IDS for s in ['DOG','CAT']},'Published ME method registry incomplete')
    for m in methods:
        require(m['basis']=='PER_100G_AS_FED' and m['unit']=='kcal','ME method dimensions invalid')
        require(bool(m['equation']) and bool(m['applicability']) and bool(m['limitations']) and bool(m['version']),'Incomplete ME evidence')
    return {'status':'PASS','food_records':len(foods),'eligible':sum(f['recipe_eligible'] for f in foods.values()),'practical_references':practical,
            'unknown_composition_cells':sum(r['value'] is None for r in vectors.values())}

def validate_constraints(t):
    profiles={r['profile_id'] for r in t['02_Requirements']};nut=index(t,'01_Nutrients','nutrient_id')
    require(profiles==EXPECTED_PROFILES,'Missing/unknown lifecycle nutrient profile')
    catalog=set().union(*REQUIRED_NUTRIENTS_BY_SPECIES.values(),*GROWTH_EXTRA.values(),*CONDITIONAL_NUTRIENTS_BY_SPECIES.values())
    require(catalog<=set(nut),'Independent required nutrient registry incomplete')
    for p in sorted(profiles):require(not profile_coverage_issues(t['02_Requirements'],p),'Required minimum coverage missing: '+str(profile_coverage_issues(t['02_Requirements'],p)))
    for r in t['02_Requirements']:
        require(r['species'] in ['DOG','CAT'] and r['profile_id'].startswith(r['species']+'_'),'Profile species mismatch')
        validate_condition(json.loads(r['condition_json']))
        for v in ['minimum','maximum']:
            if r[v] is not None:number(r[v],nonnegative=True)
            require((r[v] is None)==(r[v+'_status']=='NOT_ESTABLISHED'),'Unknown target confused with zero')
        if r['minimum'] is not None and r['maximum'] is not None:require(r['minimum']<=r['maximum'],'Lower exceeds upper bound')
        require(r['enforced'] or r['minimum'] is None and r['maximum'] is None,'Established bound cannot be disabled')
        dep=json.loads(r['dependency_json'])
        if dep:
            require(set(dep)=={'nutrient_id','slope','baseline','basis','source_locator'},'Invalid dependent requirement schema')
            require(dep['nutrient_id'] in nut and dep['basis']==r['basis'] and r['minimum'] is not None,'Invalid nutrient dependency')
            number(dep['slope'],nonnegative=True);number(dep['baseline'],nonnegative=True)
    targets={n for n,r in nut.items() if r['role']=='PROFILE_NUTRIENT'}|{'ca_p_ratio'}
    for p in profiles:
        require({r['nutrient_id'] for r in t['02_Requirements'] if r['profile_id']==p}>=targets,'Profile missing essential/conditional nutrient coverage')
    conflicts=[]
    for d in t['06_Disease_Rules']:
        if not d['action'].startswith('HARD'):continue
        for r in t['02_Requirements']:
            if r['species'] not in [d['species']] or r['nutrient_id']!=d['nutrient_id'] or r['basis']!='PER_1000_KCAL_ME':continue
            if d['basis'] not in ['PER_1000_KCAL_ME','PER_100_KCAL_ME','PER_MJ_ME']:continue
            val=convert_basis(d['value'],d['basis'],r['basis'],me_kcal=1000)
            contradiction=(d['action']=='HARD_MAX' and r['minimum'] is not None and (r['minimum']>val or r['minimum']==val and d['operator']=='LT')) or (d['action']=='HARD_MIN' and r['maximum'] is not None and (r['maximum']<val or r['maximum']==val and d['operator']=='GT'))
            if contradiction:conflicts.append({'profile_id':r['profile_id'],'disease_rule_id':d['rule_id'],'baseline_requirement_id':r['requirement_id'],'source_A':r['source_id'],'source_B':d['source_id'],'condition_json':d['condition_json'],'resolution':'REQUIRES_PROFESSIONAL_REVIEW; do not relax baseline'})
    return {'status':'PASS','profiles':len(profiles),'requirements':len(t['02_Requirements']),'detected_conditional_conflicts':conflicts,
            'policy':'All numeric hard bounds must coexist; incompatible disease overrides never erase baseline bounds'}

def validate_release(t,root):
    """A review DB is useful, but never a release approval."""
    v=t['18_Versions'][0];reasons=[]
    if not v['production_ready'] or v['release_status']!='APPROVED':reasons.append('Version is explicitly NEEDS_REVIEW')
    for field in ['expert_signoff','recipe_process_validation']:
        if not v[field]:reasons.append('Missing independently reviewed '+field)
    if not any(f['recipe_eligible'] for f in t['08_Ingredients']):reasons.append('No evidence-approved ingredients / pet ME / complete vectors')
    if not any(s['auto_use_allowed'] for s in t['14_Supplements']):reasons.append('No product- and batch-verified supplements')
    pending=sum(r['review_status']!='APPROVED' or not r['reviewer'] for r in t['16_Evidence_Map'] if r['assertion_kind']!='POLICY')
    if pending:reasons.append(f'{pending} evidence edges lack named independent approval')
    config=json.loads(v['runtime_config_json'])
    for conflict in config.get('nutrition_conflicts',[]):
        if conflict['status']=='NEEDS_REVIEW':reasons.append('Unresolved nutrition conflict: '+conflict['id'])
    # Merely toggling the version flag cannot release this dataset.
    essential={r['nutrient_id'] for r in t['02_Requirements'] if r['minimum'] is not None or r['maximum'] is not None}-{'ca_p_ratio'}
    for f in t['08_Ingredients']:
        if not f['recipe_eligible']:continue
        missing=[r['nutrient_id'] for r in t['09_Ingredient_Nutrients'] if r['ingredient_id']==f['ingredient_id'] and r['nutrient_id'] in essential and r['value'] is None]
        if missing:reasons.append(f['ingredient_id']+': missing '+','.join(missing))
    sources=index(t,'15_Sources','source_id')
    for field in ['expert_signoff','recipe_process_validation']:
        if v[field] and (v[field] not in sources or not sources[v[field]]['local_file'] or not sources[v[field]]['sha256']):
            reasons.append(field+' must reference an archived, hashed independent review')
    return {'status':'PASS' if not reasons else 'BLOCKED','reasons':reasons}


def validate_user_supplement_policy(t):
    """Brand-free consumer configuration cannot silently become an approval gate."""
    cfg=json.loads(t['18_Versions'][0]['runtime_config_json']).get('supplement_user_input',{})
    require(cfg.get('brand_catalog_required') is False and cfg.get('domestic_channels_required') is False,'Consumer user-input engine must not require brands or domestic channels')
    require(cfg.get('runtime_offline') is True and cfg.get('legacy_sku_runtime_enabled') is False,'User-input runtime isolation required')
    rules=cfg.get('calcium_conversion_rules',{})
    require(set(rules)=={'CALCIUM_CARBONATE'} and rules['CALCIUM_CARBONATE']['elemental_fraction']==.4 and rules['CALCIUM_CARBONATE']['source_id']=='USI_NIH_CALCIUM','Unreviewed calcium chemical conversion')
    rows=t['21_Supplement_Guides'];require({r['supplement_type'] for r in rows}=={'TAURINE','CALCIUM','OMEGA3_FISH_OIL','DOG_VITAMIN_MINERAL','CAT_VITAMIN_MINERAL'},'Five supplement selection types required')
    for r in rows:
        for key in ['required_label_fields_json','optional_label_fields_json','quality_indicators_json','rejection_conditions_json','input_units_json']:
            require(isinstance(json.loads(r[key]),list),'Guide list invalid: '+key)
        if r['supplement_type'] in {'DOG_VITAMIN_MINERAL','CAT_VITAMIN_MINERAL'}:
            require(json.loads(r['modes_json'])['available_modes']==['LABEL_GUIDED','NUTRIENT_CALCULATED'],'Both premix modes required')
    require(len(t['22_Quality_Guides'])==5 and all(r['required'] is False and r['ranking'] is None for r in t['22_Quality_Guides']),'Quality evidence optional, never national ranking')
    return {'status':'PASS','types':len(rows),'quality_categories':5}
