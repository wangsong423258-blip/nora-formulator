"""Published ME predictions, never human food energy or guaranteed analyses.

All inputs are g/100 g of the SAME final edible sample. A calculation is not
an applicability approval. NRC equations here cite FEDIAF's reproduction.
"""
from .units import number

INPUTS=('protein','fat','water','ash','crude_fiber')
METHOD_IDS={'FEDIAF_2025_NATURAL','FEDIAF_2025_NRC_PREPARED','AAFCO_MODIFIED_ATWATER'}

def calculate_me(method_id,species,composition,*,basis='PER_100G_AS_FED',
                 input_kind='AVERAGE_ANALYSIS',scope='INGREDIENT',applicability_reviewed=False):
    if method_id not in METHOD_IDS or species not in {'DOG','CAT'}:
        raise ValueError('Unsupported ME method or species')
    if basis!='PER_100G_AS_FED' or input_kind!='AVERAGE_ANALYSIS':
        raise ValueError('ME needs same-state average proximate analysis on as-fed basis')
    if scope not in {'INGREDIENT','WHOLE_DIET'}:raise ValueError('Unknown scope')
    if method_id!='FEDIAF_2025_NATURAL' and scope!='WHOLE_DIET':
        raise ValueError('Prepared-food equations require the whole diet, not summed ingredient predictions')
    missing=[n for n in INPUTS if composition.get(n) is None]
    result=dict(method_id=method_id,species=species,unit='kcal',basis=basis,
                value=None,me_source_type='UNKNOWN',missing_inputs=missing,
                applicability_reviewed=applicability_reviewed,status='NEEDS_REVIEW')
    result.update(source='https://europeanpetfood.org/wp-content/uploads/2025/09/FEDIAF-Nutritional-Guidelines_2025-ONLINE.pdf',
                  version='2025',year=2025,life_stage='ALL_WITH_APPLICABLE_FOOD_AND_INPUT_ANALYSES',
                  disease='NOT_VALIDATED_FOR_INDIVIDUAL_MALDIGESTION',
                  formula=('4*protein + '+('9' if species=='DOG' else '8.5')+'*fat + 4*NFE') if method_id=='FEDIAF_2025_NATURAL' else method_id,
                  assumptions=['Same-state average proximate composition, not guaranteed minima/maxima.',
                               'Crude fiber is not interchangeable with total dietary fiber.',
                               'Prediction, not a measurement of this animal digestibility.'])
    if method_id=='AAFCO_MODIFIED_ATWATER':
        result.update(source='https://www.aafco.org/resources/startups/calorie-content/',
                      version='PUBLIC_CALORIE_METHOD_VERIFIED_2026-09-24',year=None,
                      formula='3.5*protein + 8.5*fat + 3.5*NFE')
    known=[number(composition[n],nonnegative=True) for n in INPUTS if composition.get(n) is not None]
    result['known_proximate_sum']=sum(known)
    if missing and sum(known)>100:
        result['input_issue']='INCONSISTENT_PROXIMATE_MASS_BALANCE'
        result['required_resolution']='Obtain coherent same-sample proximate analyses; never clamp negative NFE'
        return result
    if missing:return result
    p,f,w,a,cf=[number(composition[n],nonnegative=True) for n in INPUTS]
    if any(v>100 for v in [p,f,w,a,cf]) or w>=100 or p+f+w+a+cf>100:
        raise ValueError('Invalid proximate mass balance; do not clamp NFE to zero')
    nfe=100-p-f-w-a-cf
    if method_id=='FEDIAF_2025_NATURAL':me=4*p+(9 if species=='DOG' else 8.5)*f+4*nfe
    elif method_id=='AAFCO_MODIFIED_ATWATER':me=3.5*p+8.5*f+3.5*nfe
    else:
        cf_dm=cf*100/(100-w)
        digest=(91.2-1.43*cf_dm) if species=='DOG' else (87.9-.88*cf_dm)
        if not 0<digest<=100:raise ValueError('Digestibility outside physical range')
        ge=5.7*p+9.4*f+4.1*(nfe+cf)
        me=ge*digest/100-(1.04 if species=='DOG' else .77)*p
        result['crude_fiber_DM_percent']=cf_dm
        if species=='DOG' and cf_dm>8:
            result['limitation']='FEDIAF: high fermentable NSP with CF >8% DM may underestimate ME'
    number(me,positive=True)
    result.update(value=me,nfe=nfe,me_source_type='CALCULATED',
                  status='CALCULATED_REVIEWED' if applicability_reviewed else 'CALCULATED_PENDING_APPLICABILITY')
    return result
