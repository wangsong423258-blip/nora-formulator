"""Typed concentration evidence. Bounds and typical values never become actuals."""
from .units import number

MODELS={'DEFINED_NUTRIENT_SOURCE','STANDARDIZED_OIL','MULTI_NUTRIENT_PREMIX'}
CA_FRACTION=40.078/100.09  # CIAAW Ca standard atomic weight / JECFA formula weight

def contribution(record,amount_g,serving_g):
    number(amount_g,nonnegative=True);number(serving_g,positive=True)
    if record.get('unit')=='%':
        if record.get('basis')!='MASS_PERCENT_AS_SOLD':raise ValueError('Percentage needs an explicit mass basis')
        ratio=amount_g/100
    else:ratio=amount_g/serving_g
    out={k:None for k in ['guaranteed_min','guaranteed_max','typical_value','actual_value']}
    for k in out:
        v=record.get(k)
        if v is not None:out[k]=number(v,nonnegative=True)*ratio
    if out['guaranteed_min'] is not None and out['guaranteed_max'] is not None and out['guaranteed_min']>out['guaranteed_max']:
        raise ValueError('Contradictory concentration interval')
    if out['actual_value'] is not None and record.get('evidence_type') not in {'BATCH_ASSAY','CERTIFIED_POINT'}:
        raise ValueError('Actual concentration requires point evidence, not a guarantee or typical value')
    out['status']='POINT_AVAILABLE_PENDING_REVIEW' if out['actual_value'] is not None else 'NEEDS_REVIEW'
    out['unit']='g' if record.get('unit')=='%' else record.get('unit')
    return out

def defined_source_contribution(source,amount_g,*,purity_actual=None,purity_min=None,
                                dry_matter_actual=None,dry_matter_min=None,basis='AS_SOLD'):
    if source not in {'TAURINE','CALCIUM_CARBONATE'}:raise ValueError('No fixed stoichiometry for oils/premixes')
    number(amount_g,nonnegative=True)
    for v in [purity_actual,purity_min,dry_matter_actual,dry_matter_min]:
        if v is not None and not 0<=number(v)<=1:raise ValueError('Fractions must be in [0,1]')
    if basis not in {'AS_SOLD','AFTER_DRYING'}:raise ValueError('Unknown assay basis')
    factor=1 if source=='TAURINE' else CA_FRACTION
    dm=1 if basis=='AS_SOLD' else dry_matter_actual
    dm_min=1 if basis=='AS_SOLD' else dry_matter_min
    return dict(nutrient='taurine' if source=='TAURINE' else 'calcium',unit='g',
        actual_value=None if purity_actual is None or dm is None else amount_g*purity_actual*dm*factor,
        guaranteed_min=None if purity_min is None or dm_min is None else amount_g*purity_min*dm_min*factor,
        guaranteed_max=None,typical_value=None,
        limitation='Chemical contribution only; uncharacterised carrier/impurities, species use and full matrix still require review')

def require_solver_ready(package):
    if package.get('model_type') not in MODELS:raise ValueError('Missing supplement model')
    if package.get('evidence_acceptance')!='ACCEPTED' or not package.get('complete_matrix'):
        raise ValueError('Supplement evidence/full matrix incomplete')
    rows=package.get('nutrient_matrix',[])
    if not rows:raise ValueError('Supplement matrix empty')
    for r in rows:
        point=r.get('actual_value') is not None and r.get('evidence_type') in {'BATCH_ASSAY','CERTIFIED_POINT'}
        bounded=r.get('guaranteed_min') is not None and r.get('guaranteed_max') is not None and r.get('guaranteed_min')<=r.get('guaranteed_max')
        if not point and not bounded:raise ValueError('Full point or bounded composition required; missing upper is not an actual')
        if not r.get('source_id') or not r.get('source_locator'):raise ValueError('Concentration provenance missing')
    if not package.get('human_review_certificate'):raise ValueError('Named review certificate missing')
