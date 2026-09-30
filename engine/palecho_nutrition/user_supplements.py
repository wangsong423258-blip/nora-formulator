"""Brand-independent label validation and deterministic dispensing adapters.

User declarations are not assays. No product catalogue, URL fetch or brand rank
is consulted. Missing composition is never promoted to a zero concentration.
"""
import copy, hashlib, json, math, re
from datetime import datetime
from .units import number, convert_unit

TYPES=('TAURINE','CALCIUM','OMEGA3_FISH_OIL','DOG_VITAMIN_MINERAL','CAT_VITAMIN_MINERAL')
MODES=('LABEL_GUIDED','NUTRIENT_CALCULATED')
PREMIX={'DOG_VITAMIN_MINERAL','CAT_VITAMIN_MINERAL'}
MASS={'g':1.,'mg':.001,'ug':.000001,'μg':.000001,'µg':.000001}
UNITS={'g','mg','scoop','mL','capsule','tablet'}
QUALITY=('peroxide_value','p_anisidine_value','totox','heavy_metal_test','pcb_test','third_party_test')

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def pos(v):return number(v,positive=True)
def nonneg(v):return number(v,nonnegative=True)
def check(ok,reason):
    if not ok:raise ValueError(reason)

def selection_guides(store):
    rows=store.rows('supplement_selection_guides')
    guides=[{k.removesuffix('_json'):(json.loads(v) if k.endswith('_json') else v) for k,v in r.items()} for r in rows]
    for g in guides:
        g['optional_quality_fields']=g['quality_indicators']
        g['available_modes']=g['modes'].get('available_modes',['NUTRIENT_CALCULATED'])
    return guides

def quality_guides(store):return store.rows('supplement_quality_guides')

def validate_spec(raw,store,species=None,life_stage=None):
    """Return VALID/WARNING/INVALID; normalized data is absent on any error."""
    warnings=[]
    try:
        check(isinstance(raw,dict),'SPEC_OBJECT_REQUIRED');s=copy.deepcopy(raw)
        sid=s.get('id');check(isinstance(sid,str) and bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,79}',sid)),'BUSINESS_ID_REQUIRED')
        typ=s.get('supplement_type');check(typ in TYPES,'SUPPLEMENT_TYPE_INVALID')
        sp=s.get('species');sp=[sp] if isinstance(sp,str) else sp
        if sp==['BOTH']:sp=['DOG','CAT']
        check(isinstance(sp,list) and bool(sp) and set(sp)<= {'DOG','CAT'},'SPECIES_REQUIRED')
        if species:check(species in sp,'SPECIES_CONFLICT')
        if typ in PREMIX:check(('DOG' if typ.startswith('DOG') else 'CAT') in sp and (not species or typ.startswith(species)), 'SPECIES_CONFLICT')
        mode=s.get('supplement_mode','NUTRIENT_CALCULATED');check(mode in MODES,'SUPPLEMENT_MODE_INVALID')
        check(mode!='LABEL_GUIDED' or typ in PREMIX,'LABEL_GUIDED_PREMIX_ONLY')
        check(s.get('user_confirmed') is True,'USER_LABEL_CONFIRMATION_REQUIRED')
        check(bool(s.get('label_source')) and isinstance(s['label_source'],(str,dict)),'LABEL_SOURCE_REQUIRED')
        for field in ('created_at','updated_at'):
            if s.get(field):datetime.fromisoformat(s[field].replace('Z','+00:00'))
            s.setdefault(field,None)
        check(not s.get('extra_active_components_unknown',False),'EXTRA_ACTIVE_COMPONENTS_UNKNOWN')
        sa=pos(s.get('serving_amount',1 if mode=='LABEL_GUIDED' else None))
        su=s.get('serving_unit',s.get('recommended_unit') if mode=='LABEL_GUIDED' else None)
        check(su in UNITS,'SERVING_UNIT_UNKNOWN_NO_GUESSED_DROP_OR_SCOOP')
        form=s.get('dosage_form',{'g':'POWDER','mg':'POWDER','scoop':'POWDER','mL':'LIQUID','capsule':'CAPSULE','tablet':'TABLET'}[su])
        check(form in {'POWDER','LIQUID','CAPSULE','TABLET'},'DOSAGE_FORM_INVALID')
        check(su in {'POWDER':{'g','mg','scoop'},'LIQUID':{'mL'},'CAPSULE':{'capsule'},'TABLET':{'tablet'}}[form],'DOSAGE_FORM_UNIT_CONFLICT')
        if su in {'g','mg'}:unit='g';per=sa*MASS[su]
        elif su=='scoop':unit='g';per=sa*pos(s.get('grams_per_scoop'))
        else:unit=su;per=sa
        mass=per if unit=='g' else None
        if s.get('product_mass_g_per_serving') is not None:
            stated_mass=pos(s['product_mass_g_per_serving'])
            check(mass is None or abs(mass-stated_mass)<1e-8,'PRODUCT_MASS_CONFLICT');mass=stated_mass
        if form in {'CAPSULE','TABLET'}:
            quantum=pos(s.get('dose_increment',1));check(quantum in (1,.5),'UNIT_SUSPECT_DIVISION')
            if quantum==.5:check(s.get('division_allowed') is True and bool(s.get('division_label_source')),'DIVISION_NOT_LABEL_SUPPORTED')
        else:quantum=pos(s.get('measurement_increment',.01 if unit=='g' else .1))
        constraints=s.get('label_constraints',{});check(isinstance(constraints,dict) and set(constraints)<= {'required_food_categories'},'UNSUPPORTED_LABEL_CONSTRAINT_REQUIRES_REVIEW')
        categories=constraints.get('required_food_categories',[]);check(isinstance(categories,list) and set(categories)<= {'MEAT','POULTRY','EGG','FISH','ORGAN','VEGETABLE','STARCH','OIL'},'LABEL_FOOD_CATEGORY_INVALID')
        records=copy.deepcopy(s.get('active_components',s.get('nutrient_panel',[])))
        check(isinstance(records,list),'NUTRIENT_PANEL_REQUIRED')
        aliases={'taurine_mg_per_serving':'taurine','elemental_calcium_mg_per_serving':'calcium','elemental_calcium_mg':'calcium','epa_mg_per_serving':'epa','dha_mg_per_serving':'dha'}
        for field,n in aliases.items():
            if field in s:records.append({'nutrient_id':n,'amount':s[field],'unit':'mg','basis':'PER_SERVING','chemical_form':'ELEMENTAL' if n=='calcium' else None})
        if typ=='CALCIUM' and not any(r.get('nutrient_id')=='calcium' for r in records):
            compound=s.get('calcium_compound')
            rules=store.config.get('supplement_user_input',{}).get('calcium_conversion_rules',{})
            check(isinstance(compound,dict) and compound.get('form') in rules,'ELEMENTAL_CALCIUM_UNKNOWN')
            rule=rules[compound['form']];a=nonneg(compound.get('mg_per_serving'))
            purity=pos(compound.get('purity_fraction'));check(purity<=1,'PURITY_INVALID')
            records.append({'nutrient_id':'calcium','amount':a*purity*rule['elemental_fraction'],'unit':'mg','basis':'PER_SERVING','chemical_form':'ELEMENTAL','derivation_source':rule['source_id']})
            warnings.append('ELEMENTAL_CALCIUM_DERIVED_FROM_EXPLICIT_COMPOUND_AND_PURITY')
        definitions=store.keyed('nutrients','nutrient_id');values={};panel=[];active_mass=0.
        for r in records:
            check(isinstance(r,dict),'COMPONENT_OBJECT_REQUIRED');n=r.get('nutrient_id');n={'folate':'b9','niacin':'b3','pantothenic_acid':'b5','vitamin_b1':'b1','vitamin_b2':'b2','vitamin_b6':'b6','vitamin_b12':'b12'}.get(n,n)
            check(n in definitions and (definitions[n]['role']=='PROFILE_NUTRIENT' or n in {'epa','dha'}),'NUTRIENT_ID_INVALID')
            check(n not in values,'DUPLICATE_NUTRIENT')
            a=nonneg(r.get('amount',r.get('value')));u=r.get('unit');u='ug' if u in {'μg','µg'} else u
            check(r.get('basis') in {'PER_SERVING','PER_G','PER_UNIT'},'NUTRIENT_BASIS_REQUIRED')
            evidence=r.get('evidence_type','LABEL_DECLARED')
            check(evidence=='LABEL_DECLARED','ACTUAL_CONCENTRATION_UNAVAILABLE_GUARANTEE_ONLY')
            if n=='calcium':check(r.get('chemical_form','ELEMENTAL')=='ELEMENTAL','ELEMENTAL_CALCIUM_UNKNOWN')
            den=per
            if r['basis']=='PER_G':check(unit=='g','PER_G_NEEDS_MASS_BASIS');den=1.
            elif r['basis']=='PER_UNIT':den=per/sa
            elif r.get('per_serving_amount') is not None:
                check(r.get('serving_unit')==su,'COMPONENT_SERVING_UNIT_CONFLICT');den=pos(r['per_serving_amount'])*per/sa
            target=definitions[n]['canonical_unit']
            if a>0 and 'CAT' in sp:
                if n=='vitamin_a':check(r.get('chemical_form') in {'RETINOL','RETINYL_ACETATE','RETINYL_PALMITATE'},'CAT_PREFORMED_VITAMIN_A_REQUIRED')
                if n=='vitamin_d':check(r.get('chemical_form')=='CHOLECALCIFEROL','CAT_VITAMIN_D3_FORM_REQUIRED')
            if target=='IU' and u!='IU':
                check(u in MASS,'UNIT_SUSPECT');ug=a*MASS[u]*1e6;form_n=r.get('chemical_form')
                if n=='vitamin_d' and form_n=='CHOLECALCIFEROL':a=ug*40
                elif n=='vitamin_a' and form_n=='RETINOL':a=ug/.3
                elif n=='vitamin_e' and form_n=='D_ALPHA_TOCOPHEROL':a=ug/1000*1.49
                else:raise ValueError('VITAMIN_ACTIVITY_FORM_REQUIRED')
                u='IU'
            v=convert_unit(a,u,target)/den;values[n]=v
            panel.append({**r,'canonical_unit':target,'amount_per_unit':v,'dose_unit':unit})
        if 'epa' in values and 'dha' in values:
            combined=values['epa']+values['dha']
            if 'epa_dha' in values:check(abs(values['epa_dha']-combined)<1e-8,'EPA_DHA_AGGREGATE_CONFLICT')
        masses={n:v*per*(MASS.get(definitions[n]['canonical_unit'],0) or {'vitamin_a':.3e-6,'vitamin_d':.025e-6,'vitamin_e':1/1.49/1000}.get(n,0)) for n,v in values.items()}
        # Aggregates and their components are not disjoint physical masses.
        if 'epa_dha' in masses:
            check(masses['epa_dha']+1e-8>=masses.get('epa',0)+masses.get('dha',0),'EPA_DHA_AGGREGATE_CONFLICT')
            masses.pop('epa',None);masses.pop('dha',None)
        for aggregate,part in [('methionine_cystine','methionine'),('phenylalanine_tyrosine','phenylalanine')]:
            if aggregate in masses:
                check(masses[aggregate]+1e-8>=masses.get(part,0),'AMINO_ACID_AGGREGATE_CONFLICT');masses.pop(part,None)
        groups={'fat':{'linoleic','alpha_linolenic','arachidonic','epa','dha','epa_dha'},'protein':{'arginine','histidine','isoleucine','leucine','lysine','methionine','methionine_cystine','phenylalanine','phenylalanine_tyrosine','threonine','tryptophan','valine'}}
        for aggregate,parts in groups.items():
            if aggregate in masses:
                check(sum(masses.get(n,0) for n in parts)<=masses[aggregate]+1e-8,'MACRO_COMPONENTS_EXCEED_TOTAL')
                for n in parts:masses.pop(n,None)
        active_mass=sum(masses.values())
        if mass is not None:check(active_mass<=mass+1e-9,'UNIT_SUSPECT_ACTIVE_MASS_EXCEEDS_PRODUCT')

        if s.get('calcium_compound'):
            compound=s['calcium_compound'];compound_mass=nonneg(compound.get('mg_per_serving'))
            if mass is not None:check(compound_mass<=mass*1000+1e-8,'COMPOUND_EXCEEDS_PRODUCT_MASS')
            rule=store.config.get('supplement_user_input',{}).get('calcium_conversion_rules',{}).get(compound.get('form'))
            if rule and 'calcium' in values:
                purity=pos(compound.get('purity_fraction'));check(purity<=1,'PURITY_INVALID')
                expected=compound_mass*purity*rule['elemental_fraction']
                check(abs(values['calcium']*per*1000-expected)<=max(.01,expected*.005),'CALCIUM_COMPOUND_DECLARATION_CONFLICT')
        if typ=='TAURINE':check(values.get('taurine',0)>0,'TAURINE_EFFECTIVE_AMOUNT_REQUIRED')
        if typ=='CALCIUM':check(values.get('calcium',0)>0,'ELEMENTAL_CALCIUM_UNKNOWN')
        if typ=='OMEGA3_FISH_OIL':
            check('epa' in values and 'dha' in values and values['epa']+values['dha']>0,'EPA_DHA_REQUIRED')
            combined=(values['epa']+values['dha'])*per*1000
            # Canonical EPA/DHA are grams; optional label totals are mg.
            for k in ('fish_oil_total_mg','total_omega3_mg'):
                if k in s:check(combined<=nonneg(s[k])+1e-8,'EPA_DHA_EXCEEDS_'+k.upper())
            if 'fish_oil_total_mg' in s and 'total_omega3_mg' in s:check(s['total_omega3_mg']<=s['fish_oil_total_mg']+1e-8,'OMEGA3_EXCEEDS_TOTAL_OIL')
            if mass is not None and 'fish_oil_total_mg' in s:check(s['fish_oil_total_mg']<=mass*1000+1e-8,'OIL_EXCEEDS_PRODUCT_MASS')
            values['epa_dha']=values['epa']+values['dha']
        if 'epa' in values and 'dha' in values:values['epa_dha']=values['epa']+values['dha']
        q=s.get('optional_quality_data',{});check(isinstance(q,dict),'QUALITY_DATA_INVALID')
        for k in ('peroxide_value','p_anisidine_value','totox'):
            if k in q:nonneg(q[k])
        if all(k in q for k in ('peroxide_value','p_anisidine_value','totox')):
            check(abs(2*q['peroxide_value']+q['p_anisidine_value']-q['totox'])<=.1,'TOTOX_INCONSISTENT')
        for k in ('heavy_metal_test','pcb_test','third_party_test'):
            if k in q:check(isinstance(q[k],dict) and q[k].get('result') in {'PASS','FAIL','NOT_TESTED'} and bool(q[k].get('reference')),'QUALITY_TEST_REFERENCE_REQUIRED')
            if isinstance(q.get(k),dict) and q[k]['result']=='FAIL':raise ValueError('PRODUCT_QUALITY_TEST_FAILED')
        if q:warnings.append('QUALITY_INFORMATION_USER_DECLARED_NOT_INDEPENDENTLY_VERIFIED')
        carrier_text=json.dumps(s.get('carrier',{}),ensure_ascii=False).lower()
        check(not any(x in carrier_text for x in ['xylitol','木糖醇','cocoa','onion','garlic']),'UNSAFE_CARRIER')
        stages=s.get('life_stages',['ADULT','HEALTHY_SENIOR'])
        check(isinstance(stages,list) and bool(stages) and set(stages)<= {'ALL','ADULT','HEALTHY_SENIOR','GROWTH'},'LIFE_STAGE_INVALID')
        if life_stage:
            stage='GROWTH' if 'GROWTH' in life_stage else 'HEALTHY_SENIOR' if 'SENIOR' in life_stage else 'ADULT'
            check('ALL' in stages or stage in stages,'LIFE_STAGE_CONFLICT')
        relation=None
        if mode=='LABEL_GUIDED':
            check(s.get('complete_homemade_diet') is True,'NOT_SUITABLE_FOR_COMPLETE_DIET_GUIDANCE')
            basis=s.get('usage_basis',s.get('product_usage_basis'))
            check(basis in {'PER_BODY_WEIGHT','PER_FOOD_WEIGHT','PER_DAILY_DIET','PER_SERVING'},'USAGE_BASIS_INVALID')
            dose=pos(s.get('recommended_amount'));ru=s.get('recommended_unit')
            check(ru in UNITS,'RECOMMENDED_UNIT_INVALID')
            if ru in {'g','mg'}:check(unit=='g','RECOMMENDED_UNIT_CONFLICT');dose*=MASS[ru]
            elif ru=='scoop':check(unit=='g','RECOMMENDED_UNIT_CONFLICT');dose*=pos(s.get('grams_per_scoop'))
            else:check(ru==unit,'RECOMMENDED_UNIT_CONFLICT')
            base=1. if basis=='PER_DAILY_DIET' else pos(s.get('usage_basis_amount'))
            if basis=='PER_BODY_WEIGHT':check(s.get('usage_basis_unit')=='kg','USAGE_BASIS_UNIT_REQUIRED')
            if basis=='PER_FOOD_WEIGHT':check(s.get('usage_basis_unit')=='g' and s.get('food_weight_basis')=='COOKED_EDIBLE','COOKED_FOOD_WEIGHT_BASIS_REQUIRED')
            if basis=='PER_SERVING':check(s.get('usage_basis_unit')=='serving','USAGE_BASIS_UNIT_REQUIRED')
            relation={'basis':basis,'amount_per_basis':dose/base,'basis_amount':base,'source':'USER_LABEL'}
            warnings.append('MICRONUTRIENT_ADEQUACY_MANUFACTURER_GUIDED_NOT_NUMERICALLY_VERIFIED')
        elif typ in PREMIX:check(bool(values),'NUTRIENT_PANEL_REQUIRED')
        for n in s.get('declared_active_nutrients',[]):check(n in values,'DECLARED_ACTIVE_COMPONENT_MISSING:'+str(n))
        # Captures any declared active ingredient, never discards unknown extras.
        check(not s.get('undeclared_active_ingredients'),'EXTRA_ACTIVE_COMPONENTS_UNKNOWN')
        for key in ('max_daily_amount','energy_kcal_per_serving'):
            if key in s:pos(s[key]) if key=='max_daily_amount' else nonneg(s[key])
        if 'max_daily_amount' in s:check(s.get('max_daily_unit')==unit,'MAX_DAILY_UNIT_REQUIRED')
        energy=s.get('energy_kcal_per_serving')
        if energy is not None:elo=ehi=energy/per
        elif typ=='CALCIUM' and s.get('pure_inorganic') is True:
            check(s.get('calcium_compound',{}).get('form')=='CALCIUM_CARBONATE' and s['calcium_compound'].get('purity_fraction')==1 and len(values)==1,'PURE_INORGANIC_IDENTITY_REQUIRED');elo=ehi=0.
        else:
            elo=0.
            if mass is not None:ehi=9*mass/per
            elif typ=='OMEGA3_FISH_OIL' and s.get('fish_oil_total_mg') is not None and s.get('pure_oil') is True and form=='LIQUID':ehi=9*s['fish_oil_total_mg']/1000/per
            else:ehi=None;warnings.append('ENERGY_OR_PRODUCT_MASS_NEEDED_FOR_WHOLE_DIET_CALCULATION')
        normalized={'id':sid,'supplement_type':typ,'species':sp,'supplement_mode':mode,'serving_amount':sa,'serving_unit':su,
            'dose_unit':unit,'dosage_form':form,'quantum':quantum,'active_components':panel,'amount_per_unit':values,
            'amount_per_g':values if unit=='g' else None,'label_source':s['label_source'],'user_confirmed':True,
            'optional_quality_data':q,'created_at':s['created_at'],'updated_at':s['updated_at'],'manufacturer':s.get('manufacturer'),
            'product_name':s.get('product_name',typ),'life_stages':stages,'dose_relation':relation,
            'max_daily_amount':s.get('max_daily_amount'),'energy_low':elo,'energy_high':ehi,
            'energy_is_user_label':energy is not None,'measurement_requirement':quantum,
            'division_allowed':s.get('division_allowed',False),'carrier':s.get('carrier'),
            'label_constraints':s.get('label_constraints',{}),'input_acceptance':'LABEL_GUIDED_ACCEPTED' if mode=='LABEL_GUIDED' else 'NUTRIENT_CALCULATED_ACCEPTED','nutrition_validation_level':'MANUFACTURER_GUIDED' if mode=='LABEL_GUIDED' else 'FORMULA_CALCULATED'}
        normalized['canonical_units']={n:definitions[n]['canonical_unit'] for n in values}
        for n in ['taurine','epa','dha','calcium']:
            normalized[('elemental_calcium' if n=='calcium' else n)+'_mg_per_unit']=values[n]*1000 if n in values else None
        normalized['spec_hash']=digest(normalized)
        return {'status':'WARNING' if warnings else 'VALID','normalized':normalized,'warnings':warnings,'errors':[]}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError) as e:
        return {'status':'INVALID','normalized':None,'warnings':warnings,'errors':[str(e)],'action':'REJECT_INPUT'}

class SupplementInputValidator:
    def __init__(self,store):self.store=store
    def validate(self,spec,**context):return validate_spec(spec,self.store,**context)

def validate_specs(pet,store,stage=None):
    raw=pet.get('user_supplements',[]);check(isinstance(raw,list),'USER_SUPPLEMENTS_MUST_BE_ARRAY')
    results=[validate_spec(s,store,pet['species'],stage) for s in raw]
    ids=[r['normalized']['id'] for r in results if r['normalized']]
    check(len(ids)==len(set(ids)),'DUPLICATE_USER_SUPPLEMENT_ID')
    return results

def user_sources(pet,stage,store,target,bounds):
    results=validate_specs(pet,store,stage);bad=[e for r in results for e in r['errors']]
    if bad:return [],results,bad
    specs=[r['normalized'] for r in results];guided=[s for s in specs if s['supplement_mode']=='LABEL_GUIDED']
    if len(guided)>1 or guided and len(specs)>1:return [],results,['LABEL_GUIDED_UNKNOWN_MATRIX_NO_AUTOMATIC_STACKING']
    sources=[];issues=[]
    for s in specs:
        if s['energy_high'] is None:issues.append(s['id']+':ENERGY_OR_PRODUCT_MASS_REQUIRED');continue
        if pet.get('allergies') and not isinstance(s['carrier'],dict):issues.append(s['id']+':CARRIER_ALLERGEN_DECLARATION_REQUIRED');continue
        if pet.get('allergies'):
            if s['carrier'].get('allergens_complete') is not True:issues.append(s['id']+':CARRIER_ALLERGEN_DECLARATION_REQUIRED');continue
            if set(s['carrier'].get('allergen_tags',[]))&set(pet['allergies']):issues.append(s['id']+':CARRIER_ALLERGY_CONFLICT');continue
        amounts=s['amount_per_unit']
        caps=[b.minimum*target*1.1/1000/amounts[b.nutrient] for b in bounds if b.minimum and b.basis=='PER_1000_KCAL_ME' and amounts.get(b.nutrient,0)>0]
        cap=max(caps+[20.])*2 # finite search domain, NEVER a toxicological maximum
        if s['max_daily_amount'] is not None:cap=min(cap,s['max_daily_amount'])
        relation=s['dose_relation'];fixed=None;food_factor=None
        if relation:
            factor=relation['amount_per_basis']
            if relation['basis']=='PER_BODY_WEIGHT':fixed=factor*pet['weight_kg']
            elif relation['basis']=='PER_DAILY_DIET':fixed=factor
            elif relation['basis']=='PER_SERVING':
                count=pet.get('daily_label_servings');check(count is not None,'DAILY_LABEL_SERVINGS_REQUIRED');fixed=factor*pos(count)
            else:food_factor=factor;cap=max(cap,target*10*factor)
            if fixed is not None:cap=max(cap,fixed)
            if s['max_daily_amount'] is not None:cap=min(cap,s['max_daily_amount'])
        sources.append({'id':'USER:'+s['id'],'type':'MULTI_NUTRIENT_PREMIX' if s['supplement_type'] in PREMIX else 'DEFINED_NUTRIENT_SOURCE',
          'definition':s,'values':{n:v*100 for n,v in amounts.items()},'upper':{n:v*100 for n,v in amounts.items()},
          'provenance':{n:{'source_id':'USER_LABEL:'+s['id'],'label_source':s['label_source'],'spec_hash':s['spec_hash'],'evidence_type':'USER_CONFIRMED_LABEL_DECLARED','actual_concentration':None} for n in amounts},
          'energy_low':s['energy_low'],'energy_high':s['energy_high'],'dm_low':0.,'quantum':s['quantum'],'cap':cap,
          'category':'SUPPLEMENT','cost':0,'unit':s['dose_unit'],'required_food_categories':s['label_constraints'].get('required_food_categories',[]),'fixed_dose':fixed,'food_dose_factor':food_factor})
    return sources,results,issues

def dose_for_gap(spec,nutrient,minimum_daily,food_known_daily,*,maximum_daily=None,food_actual_known=False):
    """Scalar helper; public meal use still requires the simultaneous solver."""
    c=spec['amount_per_unit'].get(nutrient)
    if not c:return {'status':'NO_EFFECTIVE_CONCENTRATION'}
    gap=max(0.,nonneg(minimum_daily)-nonneg(food_known_daily));theory=gap/c
    practical=math.ceil((theory-1e-10)/spec['quantum'])*spec['quantum']
    total=food_known_daily+practical*c
    cap=spec.get('max_daily_amount')
    ok=(maximum_daily is None or total<=maximum_daily+1e-9) and (cap is None or practical<=cap+1e-9)
    return {'status':'DOSE_CANDIDATE_REQUIRES_WHOLE_DIET_CHECK' if ok else 'PRODUCT_CONCENTRATION_NOT_PRACTICAL',
      'theoretical_dose':theory,'practical_dose':round(practical,8) if ok else None,'dose_unit':spec['dose_unit'],
      'known_total_daily':total if ok else None,'total_actual_daily':total if ok and food_actual_known else None,
      'unknown_background_is_zero':False,'complete_diet_validated':False}
