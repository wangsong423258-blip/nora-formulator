"""Representative food and declared-label adapters for consumer V1 only.

Nothing here promotes a food reference or label declaration to a measured value.
Unknown contributions remain None. The optimizer may CREDIT only known amounts.
"""
import json, math

PRECISIONS={'HIGH_CONFIDENCE','REFERENCE_ESTIMATE','LIMITED','REJECTED'}
UNKNOWN_CLASSES={'CRITICAL','REFERENCE_ESTIMATE_OK','SUPPLEMENT_COVERED','NON_BLOCKING','FUTURE_REFINEMENT','LAB_RESEARCH_ONLY'}
ENERGY_METHOD='FOOD_ENERGY_REFERENCE_AAHA_USDA'


def supplement_catalog(store):
    out=[]
    for row in store.rows('supplements'):
        if row.get('v1_spec_json'):
            spec=json.loads(row['v1_spec_json']);spec['v1_usable']=bool(row.get('v1_usable'))
            out.append(spec)
    return out


def _table_cap(rows,weight,interpolate=False):
    """Published entries/bands; optional explicit policy interpolation in-domain."""
    for r in rows:
        w=r.get('bw_kg');g=r.get('g_day')
        if w is None or g is None:continue
        if isinstance(w,list):
            if w[0]<=weight<=w[1]:return max(g) if isinstance(g,list) else g
        elif abs(weight-w)<1e-8:return g
    if interpolate:
        points=sorted((r['bw_kg'],r['g_day']) for r in rows
                      if isinstance(r.get('bw_kg'),(int,float)) and isinstance(r.get('g_day'),(int,float)))
        for (wa,ga),(wb,gb) in zip(points,points[1:]):
            if wa<weight<wb:return ga+(gb-ga)*(weight-wa)/(wb-wa)
    return None


def _junior_cap(spec,pet):
    week=math.floor(pet['age_days']/7);adult=pet.get('expected_adult_weight_kg',0)
    candidates=[]
    for key,rows in spec.get('usage_tables',{}).items():
        for row in rows:
            ages=row['age_weeks']
            if ages[0]<=week and (ages[1] is None or week<=ages[1]):
                candidates.append((float(key.split('kg_')[0]),row));break
    candidates.sort(key=lambda x:x[0])
    pair=next(([(w,r),(w,r)] for w,r in candidates if abs(w-adult)<1e-8),None)
    if pair is None:
        pair=next(([a,b] for a,b in zip(candidates,candidates[1:]) if a[0]<adult<b[0]),None)
    if pair is None:return None
    (wa,ra),(wb,rb)=pair;t=0. if wa==wb else (adult-wa)/(wb-wa)
    cap=ra['g_day']+(rb['g_day']-ra['g_day'])*t
    bands=[r.get('bodyweight_kg_reference',[None,None]) for r in [ra,rb]]
    bw=[None if any(b[j] is None for b in bands) else bands[0][j]+(bands[1][j]-bands[0][j])*t for j in [0,1]]
    deviation=(bw[0] is not None and pet['weight_kg']<bw[0]) or (bw[1] is not None and pet['weight_kg']>bw[1])
    spec['runtime_dose_policy']={'type':'PUBLISHED_AGE_AND_EXPECTED_ADULT_WEIGHT_GUIDANCE' if wa==wb else 'PALECHO_LINEAR_INTERPOLATION_BETWEEN_PUBLISHED_GROWTH_TABLES',
        'expected_adult_weight_kg':adult,'bracketing_expected_adult_weights_kg':[wa,wb],
        'age_weeks_completed':week,'approximate_bodyweight_reference_kg':bw,
        'bodyweight_reference_not_a_contraindication':True,'bodyweight_reference_deviation':bool(deviation),
        'source_ids':sorted({f'V1_NAPFCHECK_JUNIOR_{w:g}KG' for w in [wa,wb]}),
        'not_toxicological_maximum':True,'not_manufacturer_interpolation_formula':wa!=wb,
        'no_extrapolation':True,'requires_whole_ration_reaudit':True}
    spec['dose_reference_warnings']=['CURRENT_WEIGHT_OUTSIDE_APPROXIMATE_GUIDANCE_MONITOR_GROWTH'] if deviation else []
    return cap


def dose_cap(spec,pet,stage,target=None,bounds=()):
    sid=spec['supplement_id'];tables=spec.get('usage_tables',{});w=pet['weight_kg'];growth='GROWTH' in stage
    if not spec.get('v1_usable') or spec.get('v1_evidence_status')!='ACCEPTED_LABEL_REFERENCE':return None
    if pet['species'] not in spec.get('species_allowed',[]) or spec.get('amount_unit')!='g':return None
    if spec.get('daily_solver_eligible') is False:return None
    label_stage=stage.removeprefix(pet['species']+'_')
    label_stage={'SENIOR':'HEALTHY_SENIOR','MATURE':'ADULT','LATE_GROWTH_SMALL':'LATE_GROWTH_SMALL_MEDIUM'}.get(label_stage,label_stage)
    allowed=spec.get('life_stage_allowed',[])
    if 'ALL' not in allowed and label_stage not in allowed and not (growth and 'GROWTH' in allowed):return None
    if sid=='V1_FM_CANI_COOKING':
        return None if growth else _table_cap(tables.get('ADULT_NO_DAIRY_NO_TREATS',[]),w,interpolate=True)
    if sid=='V1_FM_FELINE':
        if growth:
            rows=[r for r in tables.get('GROWTH',[]) if pet['age_days']/7>=r['age_weeks_from']]
            if not rows:return None
            row=rows[-1];bw=row.get('bodyweight_kg_reference')
            if bw and not bw[0]<=w<=bw[1]:
                spec['dose_reference_warnings']=['CURRENT_WEIGHT_OUTSIDE_APPROXIMATE_GUIDANCE_MONITOR_GROWTH']
            return max(row['g_day'])
        return _table_cap(tables.get('SENIOR' if 'SENIOR' in stage else 'ADULT',[]),w)
    if sid=='V1_NAPF_JUNIOR':
        if not growth or pet['age_days']<56:return None
        return _junior_cap(spec,pet)
    if sid=='V1_NAPF_CALCIUM':
        # Adult table only. A growth-specific individualized protocol is not guessed.
        return None if growth else _table_cap(tables.get(pet['species']+'_ADULT',[]),w)
    if sid=='V1_ANIFORTE_TAURINE':return .5
    if sid=='V1_PAHEMA_TAURINE':
        # The dog section is therapeutic, never a healthy-dog permission.
        return 75*w/992 if pet['species']=='CAT' and label_stage=='ADULT' else None
    if sid=='V1_NAPF_DICALCIUM':
        if target is None:return None
        # Manufacturer calls for individual whole-ration calculation. This is
        # a finite search domain: enough mineral to supply either daily minimum
        # even with no food credit, not a manufacturer/toxicological maximum.
        required={n:max((b.minimum*target*1.05/1000 for b in bounds
                    if b.nutrient==n and b.minimum is not None and b.basis=='PER_1000_KCAL_ME'),default=0.)
                  for n in ('calcium','phosphorus')}
        return max(required['calcium']/.25,required['phosphorus']/.18) or None
    # Senior label has a dairy-containing ration; current solver has no dairy.
    return None


def food_vector(food,records,species):
    vals={};provenance={}
    for n,r in records.items():
        v=r['value']
        if r.get('data_precision')=='REJECTED':v=None
        if r['food_state']!=food['food_state'] or r['basis']!='PER_100G_AS_FED':v=None
        vals[n]=v
        provenance[n]={'source_id':r['source_id'],'locator':r['source_locator'],'food_state':r['food_state'],'data_precision':r.get('data_precision') or ('REFERENCE_ESTIMATE' if v is not None else 'LIMITED')}
        ref=json.loads(r.get('v1_reference_json') or '{}')
        # Migration stores the accepted exact-identity reference separately.
        if (v is None and ref.get('value') is not None and ref.get('v1_candidate_usable') is True
            and ref.get('candidate_status')=='REFERENCE_ESTIMATE_OK'
            and ref.get('basis')=='PER_100G_AS_FED_EDIBLE_COOKED'
            and ref.get('ingredient_id')==food['ingredient_id']
            and ref.get('canonical_storage_nutrient')==n
            and (ref.get('method_match') in {'MATCHED_COOKED_UNSALTED_REPRESENTATIVE','MATCHED_NDB_ID_COOKED_PEELED_UNSALTED'}
                 or (n in {'chloride','arachidonic'} and ref.get('source_id')=='COFID2021'
                     and food['ingredient_id']=='FDC_173424' and food['food_state']=='HARD_BOILED'
                     and ref.get('method_match')=='MATCHED_BOILED_WHOLE_EGG_REPRESENTATIVE')
                 or (n=='chloride' and ref.get('source_id')=='COFID2021'
                     and ref.get('food_state')==food['food_state']
                     and (food['ingredient_id'],food['food_state']) in {
                         ('FDC_170440','BOILED_DRAINED'),('FDC_169967','BOILED_DRAINED'),
                         ('FDC_170394','BOILED_DRAINED'),('FDC_169976','BOILED_DRAINED'),
                         ('FDC_169292','BOILED_DRAINED'),('FDC_168484','BOILED'),('FDC_172411','ROASTED')}
                     and ref.get('method_match')=='MATCHED_EXISTING_COOKED_FOOD_CHLORIDE_REPRESENTATIVE')
                 or (n=='chloride' and ref.get('source_id')=='COFID2021' and food['food_state']=='ROASTED'
                     and (food['ingredient_id'],ref.get('method_match')) in {
                         ('FDC_170633','COOKED_LEAN_BEEF_CUT_PROXY'),
                         ('FDC_171477','MATCHED_ROASTED_CHICKEN_LIGHT_MEAT_REPRESENTATIVE')}))
            and food.get('raw_or_cooked')=='COOKED' and food.get('weight_basis')=='COOKED_WEIGHT'
            and r['food_state']==food['food_state']):
            # Reference units are preserved in the evidence package. Convert
            # their mass unit explicitly into the canonical stored unit.
            scales={'g':1.,'mg':.001,'ug':.000001,'µg':.000001}
            ru=ref.get('unit');tu=r.get('unit');factor=1. if ru==tu else (scales[ru]/scales[tu] if ru in scales and tu in scales else None)
            if factor is not None:
                vals[n]=ref['value']*factor
                provenance[n]={**ref,'original_reference_value':ref['value'],'original_reference_unit':ru,
                               'value':vals[n],'unit':tu,'unit_conversion_factor':factor,'data_precision':'REFERENCE_ESTIMATE'}
    # Traceable chemical activity conversions, never raw-to-cooked conversions.
    a='vitamin_a_'+species.lower()
    if vals.get(a) is not None:vals['vitamin_a']=vals[a];provenance['vitamin_a']=provenance[a]
    elif vals.get('retinol') is not None:
        vals['vitamin_a']=vals['retinol']/0.3
        provenance['vitamin_a']={**provenance['retinol'],'method':'FEDIAF2025: 1 IU retinol = 0.3 ug; retinol contribution only, unquantified carotenoids not credited'}
    if vals.get('vitamin_d3_activity') is not None:
        vals['vitamin_d']=vals['vitamin_d3_activity'];provenance['vitamin_d']=provenance['vitamin_d3_activity']
    if vals.get('vitamin_e') is None and vals.get('alpha_tocopherol') is not None:
        vals['vitamin_e']=vals['alpha_tocopherol']*1.49
        provenance['vitamin_e']={**provenance['alpha_tocopherol'],'method':'FEDIAF2025 natural food alpha-tocopherol mg ×1.49 IU/mg'}
    # D-total used solely for conservative upper screening, not D3 minimum credit.
    upper=dict(vals)
    if vals.get('vitamin_d_total') is not None:upper['vitamin_d']=vals['vitamin_d_total']*40
    return vals,upper,provenance


def source_candidates(pet,stage,store,target,excluded=(),*,include_supplements=True,quick_meal=False):
    raw={}
    for r in store.rows('ingredient_nutrients'):raw.setdefault(r['ingredient_id'],{})[r['nutrient_id']]=r
    sources=[];rejections=[]
    liver_policy=store.config.get('practical_v1',{}).get('small_liver_inclusion_policy',{})
    liver_context=liver_policy.get('vitamin_d_qualitative_context',{})
    liver_enabled=(liver_policy.get('ingredient_id')=='FDC_171061' and liver_policy.get('food_state')=='SIMMERED'
                   and liver_policy.get('max_cooked_food_mass_fraction')==.05 and liver_policy.get('max_reference_food_energy_fraction')==.05
                   and liver_context.get('qualitative_context')=='DATABASE_ASSUMED_NEGLIGIBLE_NOT_MEASURED_OR_BOUND'
                   and liver_context.get('runtime_numeric_contribution') is None and liver_context.get('runtime_upper_bound') is None)
    # Only this historical organ-review policy is superseded by the explicit
    # V1 small-organ constraint. All toxicity and other exclusions remain.
    limits={r['ingredient_id'] for r in store.rows('ingredient_limits') if r['operator']=='EXCLUDE'
            and not (r['limit_id']=='FDC_171061_ORGAN_REVIEW' and liver_enabled)}
    for f in sorted(store.rows('ingredients'),key=lambda x:x['ingredient_id']):
        i=f['ingredient_id'];tags=set((f['allergen_tags'] or '').split(';'))|{i,f['food_category']};reasons=[]
        if i in excluded:reasons.append('REPLACED_OUT')
        if tags&set(pet['allergies']):reasons.append('ALLERGEN_EXCLUDED')
        if include_supplements and tags&set(pet['dislikes']):reasons.append('DISLIKED')
        if f['toxicity_flag'] or i in limits:reasons.append('SAFETY_EXCLUSION')
        if not f[pet['species'].lower()+'_allowed']:reasons.append('SPECIES_EXCLUSION')
        if f['raw_or_cooked']=='RAW' or f['portion_basis']!='EDIBLE_WEIGHT':reasons.append('COOKED_EDIBLE_STATE_REQUIRED')
        if f['raw_or_cooked']=='COOKED' and f['weight_basis']!='COOKED_WEIGHT':reasons.append('DATA_METHOD_MISMATCH')
        if 'available_ingredients' in pet and i not in pet['available_ingredients']:reasons.append('UNAVAILABLE')
        if reasons:rejections.append({'id':i,'reasons':reasons});continue
        v,upper,p=food_vector(f,raw.get(i,{}),pet['species'])
        if any(v.get(n) is None for n in ('energy_human','water','protein','fat','calcium','phosphorus')):
            rejections.append({'id':i,'reasons':['CRITICAL_MACRO_OR_CALCIUM_PHOSPHORUS_UNKNOWN']});continue
        # Unknown iodine/D in marine fish is a material safety gap; terrestrial
        # ordinary-food trace uncertainty stays visible in the reference audit.
        if not quick_meal and f['food_category']=='FISH' and any(upper.get(n) is None for n in ('iodine','vitamin_d')):
            rejections.append({'id':i,'reasons':['CRITICAL_FISH_IODINE_OR_D_UNQUANTIFIED']});continue
        if f['food_category']=='ORGAN':
            if i!='FDC_171061' or f['food_state']!='SIMMERED' or any(v.get(n) is None for n in ['vitamin_a','copper']):
                rejections.append({'id':i,'reasons':['ORGAN_IDENTITY_OR_A_COPPER_UNKNOWN']});continue
            p['vitamin_d']={**liver_context,
                'numeric_contribution':None,'upper_bound':None,
                'only_with':'SIMMERED_CHICKEN_LIVER_5PCT_FOOD_MASS_AND_ENERGY_POLICY'}
        e=v['energy_human']/100
        if e<=0:continue
        q=.5 if f['food_category']=='OIL' else 5.
        sources.append(dict(id=i,type='FOOD',definition=f,values=v,upper=upper,provenance=p,energy_low=e,energy_high=e,
             dm_low=(100-v['water'])/100,quantum=q,cap=target*1.05/e,category=f['food_category'],
             cost={'LOW':1,'MEDIUM':2,'HIGH':3}.get(f.get('cost_level_cn'),2),unit='g',
             preference_penalty=1 if not include_supplements and tags&set(pet['dislikes']) else 0))
    if not include_supplements:return sources,rejections
    from .profile import lifecycle
    from .runtime import active_bounds
    _,profile=lifecycle(pet,store)
    supplement_bounds=active_bounds({'profile_id':profile,'pet':pet,'disease_constraints':[]},store) if profile else []
    for spec in supplement_catalog(store):
        cap=dose_cap(spec,pet,stage,target,supplement_bounds)
        if cap is None or cap<=0:
            rejections.append({'id':spec['supplement_id'],'reasons':['LABEL_OR_SPECIES_STAGE_OR_DOSING_SCOPE_UNAVAILABLE']});continue
        # A supplier must specify carriers when an allergy diet is requested.
        carrier=(spec.get('carrier') or '').lower()
        carrier_tags={'EGG':['egg'],'SOY':['soy'],'FISH':['fish'],'CHICKEN':['chicken','poultry'],'BEEF':['beef'],'PORK':['pork']}
        if pet['allergies'] and (not carrier or 'unknown' in carrier or any(any(t in carrier for t in words) for tag,words in carrier_tags.items() if tag in pet['allergies'])):
            rejections.append({'id':spec['supplement_id'],'reasons':['CARRIER_ALLERGY_REVIEW']});continue
        v={n:a*100 for n,a in spec.get('amount_per_g',{}).items()}
        conversion_provenance={}
        for r in spec.get('nutrient_records',[]):
            if r['nutrient']=='b5' and r.get('active_pantothenic_acid_per_g') is not None:
                v['b5']=100*r['active_pantothenic_acid_per_g']
                conversion_provenance['b5']={'additional_source_id':r['active_conversion_source_id'],
                    'conversion_factor':r['active_conversion_factor'],'conversion_locator':r['active_conversion_locator'],
                    'source_form':r['chemical_form'],'canonical_form':'pantothenic acid'}
        if not v:continue
        inorganic=spec['supplement_id'] in {'V1_NAPF_DICALCIUM','V1_NAPF_CALCIUM'}
        # Disjoint elemental masses cannot yield food energy. Do not sum their
        # parent salts again or assume undeclared ash/water. This tightens only
        # the label-reference energy envelope, not an assayed ME concentration.
        nonenergy_elements={n:spec.get('amount_per_g',{}).get(n) for n in ['calcium','phosphorus','sodium','potassium','magnesium','chloride']
                            if spec.get('amount_per_g',{}).get(n) is not None}
        nonenergy_mass=sum(nonenergy_elements.values())
        if nonenergy_mass<0 or nonenergy_mass>1:
            rejections.append({'id':spec['supplement_id'],'reasons':['DECLARED_ELEMENT_MASS_BALANCE_INVALID']});continue
        energy_high=0. if inorganic else 9.*(1.-nonenergy_mass)
        if inorganic:
            spec['energy_model']={'classification':'CHEMICALLY_DEFINED_INORGANIC_NONENERGY_SOURCE',
                 'source_id':spec['source_id'],'basis':'Official 100% inorganic mineral ingredient declaration; no organic carrier declared.',
                 'measured_energy':False,'unknown_trace_composition_remains_unknown':True}
        else:
            spec['energy_model']={'type':'COMPOSITION_INFORMED_REFERENCE_ENERGY_ENVELOPE',
                'low_kcal_per_g':0.,'high_kcal_per_g':energy_high,
                'equation':'9 * (1 - sum(non-overlapping declared Ca,P,Na,K,Mg,Cl element mass fractions))',
                'nonenergy_element_g_per_g':nonenergy_elements,'nonenergy_element_sum_g_per_g':nonenergy_mass,
                'source_id':spec['source_id'],'measured_energy':False,'not_a_batch_guaranteed_energy_bound':True,
                'undeclared_ash_water_or_salt_fraction_assumed_zero':False}
            if spec['supplement_id']=='V1_NAPF_JUNIOR':
                from .sources_energy_envelope import junior_reference_envelope
                model=junior_reference_envelope(spec,store.config.get('practical_v1',{}).get('junior_energy_envelope_method'),nonenergy_mass)
                if model:
                    energy_high=model['high_kcal_per_g'];spec['energy_model']=model
        if spec['supplement_id']=='V1_NAPF_DICALCIUM':
            spec['runtime_dose_policy']={'type':'WHOLE_DIET_MINIMUM_BASED_SEARCH_DOMAIN',
                'formula':'max(calcium_minimum_per1000kcal * target_kcal * 1.05 / 1000 / 0.25, phosphorus_minimum_per1000kcal * target_kcal * 1.05 / 1000 / 0.18)',
                'not_manufacturer_or_toxicological_maximum':True,'requires_full_ration_reaudit':True}
        if spec['supplement_id']=='V1_FM_CANI_COOKING':
            spec['runtime_dose_policy']={'type':'PALECHO_LINEAR_INTERPOLATION_WITHIN_PUBLISHED_WEIGHT_TABLE',
                'weight_domain_kg':[2.5,70],'extrapolation_allowed':False,
                'source_id':'V1_FUTTERMEDICUS_COOKING_DOSE',
                'scope':'Manufacturer no-dairy/no-treats cooked meat, starch, vegetable and oil ration structure.',
                'not_manufacturer_interpolation_formula':True,'not_toxicological_maximum':True,'requires_full_ration_reaudit':True}
        # Powder energy/water are not invented as zero concentrations. For
        # portion uncertainty use a conservative 0..9 kcal/g physical envelope;
        # unknown powder DM is omitted from the maximum denominator (safe side).
        sources.append(dict(id=spec['supplement_id'],type=spec['source_type'],definition=spec,values=v,upper=dict(v),
              provenance={n:{'source_id':spec['source_id'],'evidence_type':'LABEL_DECLARED','actual_concentration':None,**conversion_provenance.get(n,{})} for n in v},
              energy_low=0.,energy_high=energy_high,dm_low=0.,quantum=.01,cap=cap,category='SUPPLEMENT',cost=0,unit='g'))
    return sources,rejections


def unknown_class(n,source,covered=False):
    if n in ('me_dog','me_cat','crude_fiber','nfe'):return 'LAB_RESEARCH_ONLY'
    if n in ('energy_human','protein','fat','calcium','phosphorus','water'):return 'CRITICAL'
    if covered:return 'SUPPLEMENT_COVERED'
    if n in ('vitamin_k','biotin') and source.get('species')=='DOG':return 'NON_BLOCKING'
    return 'FUTURE_REFINEMENT'
