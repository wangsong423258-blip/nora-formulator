"""Strict dimensional conversions; NULL propagates and never becomes zero."""
from math import isfinite

class UnitError(ValueError):
    pass

MASS = {'g':1.0, 'mg':1e-3, 'ug':1e-6}
ENERGY = {'kcal':1.0, 'kJ':1/4.184, 'MJ':1000/4.184}
BASES = {'PER_100G_AS_FED','PER_KG_AS_FED','PER_100G_DM','PER_KG_DM',
         'PER_1000_KCAL_ME','PER_100_KCAL_ME','PER_MJ_ME','PER_DAY','RATIO'}

def number(x, *, positive=False, nonnegative=False):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x):
        raise UnitError(f'Finite numeric value required, got {x!r}')
    if positive and x<=0 or nonnegative and x<0:
        raise UnitError(f'Out of range: {x!r}')
    return float(x)

def convert_unit(value, source, target):
    if source==target:
        if source not in {*MASS,*ENERGY,'IU','ratio'}: raise UnitError(f'Unknown unit {source}')
        return None if value is None else number(value)
    for group in (MASS,ENERGY):
        if source in group and target in group:
            return None if value is None else number(value)*group[source]/group[target]
    raise UnitError(f'Incompatible units: {source} -> {target}; vitamin form/activity is not implicit')

def _denominator(basis, *, as_fed_g=None, water_g=None, me_kcal=None):
    if basis not in BASES: raise UnitError(f'Unknown basis: {basis}')
    if basis=='PER_DAY': return 1.0
    if basis=='RATIO': raise UnitError('Ratios require their named numerator and denominator')
    if 'AS_FED' in basis:
        return number(as_fed_g,positive=True)/(100 if basis=='PER_100G_AS_FED' else 1000)
    if basis.endswith('_DM'):
        mass=number(as_fed_g,positive=True);water=number(water_g,nonnegative=True)
        dm=mass-water
        if dm<=0: raise UnitError('Dry matter must be positive and moisture must be measured')
        return dm/(100 if basis=='PER_100G_DM' else 1000)
    energy=number(me_kcal,positive=True)
    return energy / {'PER_1000_KCAL_ME':1000,'PER_100_KCAL_ME':100,'PER_MJ_ME':1000/4.184}[basis]

def convert_basis(value, source, target, **context):
    if source not in BASES or target not in BASES: raise UnitError('Unknown basis')
    if source==target: return None if value is None else number(value)
    if 'RATIO' in (source,target): raise UnitError('Cannot convert ratio into a concentration')
    a=_denominator(source,**context);b=_denominator(target,**context)
    return None if value is None else number(value)*a/b

def sum_known(values):
    vals=list(values)
    return None if any(v is None for v in vals) else sum(number(v) for v in vals)

def vitamin_a_activity(retinol_ug,beta_carotene_ug,species):
    """FEDIAF 2025 Table VII-14 p63; no human RAE/unspecified carotenoids."""
    if species not in ['DOG','CAT']:raise UnitError('Unknown vitamin activity species')
    if retinol_ug is None or species=='DOG' and beta_carotene_ug is None:return None
    value=number(retinol_ug,nonnegative=True)/0.3
    if species=='DOG':value+=number(beta_carotene_ug,nonnegative=True)/1000*833
    return value

def vitamin_d3_activity(cholecalciferol_ug):
    """D3 only, never an implicit conversion of D2+D3 or 25-OH-D."""
    return None if cholecalciferol_ug is None else number(cholecalciferol_ug,nonnegative=True)*40

def convert_food_weight(grams,source_basis,target_basis,*,yield_factor=None,source_id=None,process_match=False):
    """Measured edible raw->cooked yield. Nutrient retention is a separate operation."""
    number(grams,nonnegative=True)
    allowed={'RAW_WEIGHT','COOKED_WEIGHT'}
    if source_basis not in allowed or target_basis not in allowed:raise UnitError('Weight basis must specify RAW or COOKED; EDIBLE_WEIGHT describes portion only')
    if source_basis==target_basis:return grams
    if not source_id or not process_match:raise UnitError('Matched sourced yield required')
    y=number(yield_factor,positive=True)
    return grams*y if source_basis=='RAW_WEIGHT' else grams/y

def estimate_me(composition, rule):
    """Per 100 g as fed, from actual proximate analysis. Never use dietary fibre for CF."""
    needed=('water','protein','fat','ash','crude_fiber')
    c={k:number(composition.get(k),nonnegative=True) for k in needed}
    if sum(c.values())>100+1e-8: raise UnitError('Proximate fractions exceed 100 g')
    nfe=100-sum(c.values())
    p=rule['parameters']
    if rule['model']=='NATURAL_ME':
        me=p['protein']*c['protein']+p['fat']*c['fat']+p['nfe']*nfe
    elif rule['model']=='NRC_4STEP':
        dm=100-c['water']
        if dm<=0: raise UnitError('No dry matter')
        cf_dm=c['crude_fiber']/dm*100
        digest=p['digestibility_intercept']-p['crude_fiber_dm_slope']*cf_dm
        if not 0<digest<=100: raise UnitError('ME model outside its supported domain')
        ge=p['protein_ge']*c['protein']+p['fat_ge']*c['fat']+p['carb_ge']*(nfe+c['crude_fiber'])
        me=ge*digest/100-p['urine_protein']*c['protein']
    else: raise UnitError('Unknown ME model')
    return {'estimate_kcal_per_100g':number(me,positive=True),'nfe_g_per_100g':nfe,
            'source_id':rule['source_id'],'status':'ESTIMATE_REQUIRES_APPLICABILITY_REVIEW'}
