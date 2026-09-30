"""Food + supplement robust MILP. Mathematical completeness is not clinical release.

Concentrations use canonical nutrient units / 100 g final edible/as-sold mass.
Intervals are evidence bounds, not probability distributions. A missing endpoint
stays None; no implicit zero, midpoint, or guarantee-as-actual substitution.
"""
from dataclasses import dataclass, field
from math import isfinite
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint

SOURCE_TYPES={'FOOD','DEFINED_NUTRIENT_SOURCE','STANDARDIZED_OIL','MULTI_NUTRIENT_PREMIX'}

@dataclass(frozen=True)
class Interval:
    low: float|None
    high: float|None
    source_id: str
    locator: str
    evidence_type: str='SPECIFICATION_RANGE'
    def __post_init__(self):
        for v in (self.low,self.high):
            if v is not None and (type(v) not in (int,float) or not isfinite(v) or v<0):raise ValueError('Invalid interval endpoint')
        if self.low is not None and self.high is not None and self.low>self.high:raise ValueError('Reversed interval')
    @property
    def actual(self):
        return self.low if self.low==self.high and self.evidence_type in {'DATABASE_POINT','BATCH_ASSAY','CERTIFIED_POINT','CALCULATED_POINT'} else None

@dataclass(frozen=True)
class NutrientSource:
    id: str
    source_type: str
    nutrients: dict
    me: Interval
    water: Interval
    maximum_g: float
    quantum_g: float
    minimum_g: float=0
    availability_penalty: float=0
    cost_per_g: float|None=None
    complexity_penalty: float=0
    preference_penalty: float=0
    species: tuple=()
    life_stages: tuple=()
    food_state: str=''
    evidence_acceptance: str='NEEDS_REVIEW'
    complete_matrix: bool=False
    safety_envelope_source: str|None=None
    nutrient_units: dict=field(default_factory=dict)
    def __post_init__(self):
        if self.source_type not in SOURCE_TYPES:raise ValueError('Unsupported nutrient source type')
        for v in (self.maximum_g,self.quantum_g,self.minimum_g,self.availability_penalty,self.complexity_penalty,self.preference_penalty):
            if type(v) not in (int,float) or not isfinite(v) or v<0:raise ValueError('Invalid source policy')
        if self.quantum_g<=0 or self.maximum_g<self.quantum_g or self.minimum_g>self.maximum_g:raise ValueError('Invalid dispensing bounds')
        if self.cost_per_g is not None and (not isfinite(self.cost_per_g) or self.cost_per_g<0):raise ValueError('Invalid price')
        if self.water.high is not None and self.water.high>100:raise ValueError('Water > 100 g/100g')

class UnknownEndpoint(ValueError):pass

def _endpoint(interval,side,label):
    if not interval or not interval.source_id or not interval.locator:raise UnknownEndpoint(label+':SOURCE_MISSING')
    v=getattr(interval,side)
    if v is None:raise UnknownEndpoint(label+':'+side.upper()+'_UNKNOWN')
    return v

def _vector(sources,nutrient,side):
    return np.array([_endpoint(s.nutrients.get(nutrient),side,s.id+':'+nutrient) for s in sources])/100

def _vectors(sources,nutrient):
    return tuple(_vector(sources,nutrient,k) for k in ('low','high'))

def _denominators(sources,basis):
    if basis=='PER_DAY':return None,None
    if basis in {'PER_1000_KCAL_ME','PER_100_KCAL_ME','PER_MJ_ME'}:
        factor={'PER_1000_KCAL_ME':1/1000,'PER_100_KCAL_ME':1/100,'PER_MJ_ME':4.184/1000}[basis]
        return tuple(np.array([_endpoint(s.me,k,s.id+':ME') for s in sources])/100*factor for k in ('low','high'))
    if basis in {'PER_100G_DM','PER_KG_DM'}:
        scale=100 if basis=='PER_100G_DM' else 1000
        return tuple(np.array([1-_endpoint(s.water,k,s.id+':water')/100 for s in sources])/scale for k in ('high','low'))
    if basis in {'PER_100G_AS_FED','PER_KG_AS_FED'}:
        v=np.ones(len(sources))/(100 if basis=='PER_100G_AS_FED' else 1000);return v,v
    raise ValueError('Unsupported basis '+basis)

def computational_source_issues(sources,species,stage):
    issues=[]
    for s in sources:
        if s.evidence_acceptance!='ACCEPTED':issues.append(s.id+':EVIDENCE_NOT_ACCEPTED')
        if species not in s.species or stage not in s.life_stages:issues.append(s.id+':SPECIES_STAGE_NOT_SUPPORTED')
        if s.source_type=='FOOD' and s.food_state not in {'ROASTED','STEWED','HARD_BOILED','BOILED','BOILED_DRAINED','COOKED_DRY_HEAT','BAKED','STEAMED','COOKED'}:issues.append(s.id+':FINAL_COOKED_STATE_REQUIRED')
        if s.source_type!='FOOD' and (not s.complete_matrix or not s.safety_envelope_source):issues.append(s.id+':MATRIX_OR_USAGE_EVIDENCE_MISSING')
    return issues

def solve_intervals(sources,bounds,target_kcal,*,energy_tolerance=0,min_foods=4,max_foods=7,required=(),budget=None,food_shares=()):
    """Internal mathematics API, usable with explicitly artificial fixtures.

    Always returns clinical_release=False. Public planning must separately enforce
    source eligibility, independent required-nutrient coverage and rule conflicts.
    """
    sources=sorted(sources,key=lambda x:x.id);n=len(sources)
    if type(target_kcal) not in (int,float) or not isfinite(target_kcal) or target_kcal<=0 or not 0<=energy_tolerance<1:raise ValueError('Invalid energy target')
    if not 0<=min_foods<=max_foods:raise ValueError('Invalid food-count policy')
    if not n:return {'status':'NO_VALID_RECIPE','blockers':['CANDIDATES_EMPTY'],'clinical_release':False}
    if len({s.id for s in sources})!=n:raise ValueError('Duplicate source IDs')
    if not set(required)<={s.id for s in sources}:return {'status':'NO_VALID_RECIPE','blockers':['REQUIRED_SOURCE_MISSING'],'clinical_release':False}
    if budget is not None and (not isfinite(budget) or budget<0):raise ValueError('Invalid budget')
    if budget is not None and any(s.cost_per_g is None for s in sources):return {'status':'NEEDS_REVIEW','blockers':['PRICE_UNKNOWN_FOR_HARD_BUDGET'],'clinical_release':False}
    q=np.array([s.quantum_g for s in sources]);rows=[];lo=[];hi=[];labels=[]
    def add(v,l=-np.inf,h=np.inf,label='',binary=None):
        rows.append(np.r_[np.asarray(v)*q,np.zeros(n) if binary is None else binary]);lo.append(l);hi.append(h);labels.append(label)
    food=np.array([s.source_type=='FOOD' for s in sources],dtype=float);supp=1-food
    add(np.zeros(n),min_foods,max_foods,'FOOD_COUNT',food)
    for i,s in enumerate(sources):
        v=np.eye(n)[i];add(v,h=0,label='USAGE_MAX:'+s.id,binary=-v*s.maximum_g)
        add(v,l=0,label='USAGE_MIN_IF_USED:'+s.id,binary=-v*max(s.minimum_g,s.quantum_g))
        if s.id in required:add(v,l=max(s.minimum_g,s.quantum_g),label='REQUIRED:'+s.id)
    try:
        elo,ehi=_denominators(sources,'PER_100_KCAL_ME');elo*=100;ehi*=100
        add(elo,l=target_kcal*(1-energy_tolerance),label='ENERGY_MIN');add(ehi,h=target_kcal*(1+energy_tolerance),label='ENERGY_MAX')
        dmlo,dmhi=_denominators(sources,'PER_100G_DM');add(dmlo,l=1e-10,label='POSITIVE_DRY_MATTER')
        for b in bounds:
            if b.minimum is None and b.maximum is None:continue
            if b.basis=='RATIO':
                if b.nutrient!='ca_p_ratio':raise ValueError('Unsupported ratio')
                vl,vh=_vectors(sources,'calcium');dl,dh=_vectors(sources,'phosphorus');add(dl,l=1e-10,label='POSITIVE_PHOSPHORUS')
            else:
                vl=_vector(sources,b.nutrient,'low') if b.minimum is not None else None
                vh=_vector(sources,b.nutrient,'high') if b.maximum is not None else None
                dl,dh=_denominators(sources,b.basis)
            if b.minimum is not None:
                lower=b.minimum+(max(1,abs(b.minimum))*1e-7 if b.strict_minimum else 0)
                add(vl if dh is None else vl-lower*dh,l=lower if dh is None else 0,label=b.id+':MIN')
                if b.basis=='PER_1000_KCAL_ME':add(vl,l=lower*target_kcal/1000,label=b.id+':DAILY_MIN')
                if b.dependency:
                    dep=b.dependency;dv=_vector(sources,dep['nutrient_id'],'high');slope=dep['slope'];base=lower-slope*dep['baseline']
                    if slope<0 or dh is None:raise ValueError('Unsupported dependency')
                    add(vl-slope*dv-base*(dh if base>=0 else dl),l=0,label=b.id+':DEPENDENCY')
                    if b.basis=='PER_1000_KCAL_ME':add(vl-slope/(1-energy_tolerance)*dv,l=base*target_kcal/1000,label=b.id+':DEPENDENT_DAILY_FLOOR')
            if b.maximum is not None:
                upper=b.maximum-(max(1,abs(b.maximum))*1e-7 if b.strict_maximum else 0)
                add(vh if dl is None else vh-upper*dl,h=upper if dl is None else 0,label=b.id+':MAX')
        for s in food_shares:
            idx=next(i for i,f in enumerate(sources) if f.id==s['ingredient_id'])
            if s['basis']=='FRACTION_ME':
                # numerator high, all other sources low: tighter robust fraction than Nhi/total_lo.
                v=-s['maximum']*elo.copy();v[idx]=(1-s['maximum'])*ehi[idx]
            elif s['basis'] in {'FRACTION_MASS','FRACTION_AS_FED'}:
                v=-s['maximum']*np.ones(n);v[idx]+=1
            else:raise ValueError('Unsupported food share basis')
            add(v,h=0,label=s['id'])
    except UnknownEndpoint as e:return {'status':'NEEDS_REVIEW','blockers':[str(e)],'clinical_release':False}
    if budget is not None:add(np.array([s.cost_per_g for s in sources]),h=budget,label='BUDGET')
    domain=Bounds(np.zeros(2*n),np.r_[np.floor([s.maximum_g/s.quantum_g for s in sources]),np.ones(n)])
    fixed=[]
    def run(c):
        return milp(c=c,integrality=np.ones(2*n),bounds=domain,constraints=LinearConstraint(np.array(rows+[x[0] for x in fixed]),np.array(lo+[x[1] for x in fixed]),np.array(hi+[x[2] for x in fixed])),options={'presolve':True,'mip_rel_gap':0,'time_limit':30})
    objectives=[('COMMON_FOODS',np.r_[np.zeros(n),[s.availability_penalty if s.source_type=='FOOD' else 0 for s in sources]]),
                ('SUPPLEMENT_TYPES',np.r_[np.zeros(n),supp]),('SUPPLEMENT_GRAMS',np.r_[q*supp,np.zeros(n)])]
    if all(s.cost_per_g is not None for s in sources):objectives.append(('COST',np.r_[[s.cost_per_g*s.quantum_g for s in sources],np.zeros(n)]))
    objectives += [('FOOD_COUNT',np.r_[np.zeros(n),food]),('PREPARATION',np.r_[np.zeros(n),[s.complexity_penalty for s in sources]]),('PREFERENCE',np.r_[np.zeros(n),[s.preference_penalty for s in sources]])]
    objectives += [('TIE:'+s.id,np.eye(2*n)[i]) for i,s in enumerate(sources)]
    values=[];result=run(np.zeros(2*n))
    for label,objective in objectives:
        if result.status!=0 or not np.any(objective):continue
        result=run(objective)
        if result.status!=0:break
        integer=np.rint(result.x)
        if max(abs(result.x-integer))>1e-5:return {'status':'SOLVER_ERROR','blockers':['NONINTEGER_RESULT'],'clinical_release':False}
        value=float(objective@integer);fixed.append((objective,value-1e-8,value+1e-8));values.append({'objective':label,'value':value})
    if result.status!=0:return {'status':'NO_VALID_RECIPE' if result.status==2 else 'SOLVER_ERROR','blockers':['SIMULTANEOUS_HARD_CONSTRAINTS_INFEASIBLE' if result.status==2 else result.message],'constraint_ids':labels,'relaxed_constraints':False,'clinical_release':False}
    grams={s.id:float(round(result.x[i])*s.quantum_g) for i,s in enumerate(sources) if round(result.x[i])>0}
    audit=audit_intervals(sources,bounds,grams,target_kcal,energy_tolerance,min_foods=min_foods,max_foods=max_foods,required=required,budget=budget,food_shares=food_shares)
    return {'status':'NUMERIC_PASS' if audit['all_numeric_requirements_pass'] else 'NO_VALID_RECIPE','grams':grams if audit['all_numeric_requirements_pass'] else None,'audit':audit,'objectives':values,'cost_status':'KNOWN' if all(s.cost_per_g is not None for s in sources) else 'NOT_OPTIMIZED_MISSING_PRICES','clinical_release':False,'relaxed_constraints':False}

def audit_intervals(sources,bounds,grams,target_kcal,energy_tolerance=0,*,min_foods=4,max_foods=7,required=(),budget=None,food_shares=()):
    by={s.id:s for s in sources}
    if len(by)!=len(sources) or set(grams)-set(by):raise ValueError('Invalid source IDs')
    if not isfinite(target_kcal) or target_kcal<=0 or not 0<=energy_tolerance<1:raise ValueError('Invalid target')
    for v in grams.values():
        if type(v) not in (int,float) or not isfinite(v) or v<0:raise ValueError('Invalid grams')
    active=[(by[i],g) for i,g in sorted(grams.items()) if g>0];mass=sum(g for s,g in active)
    def sum_endpoint(items,side):
        vals=[None if x is None else getattr(x,side) for x,g in items]
        return None if any(v is None for v in vals) else sum(v*g/100 for v,(x,g) in zip(vals,items))
    def interval_total(n,items=active):return [sum_endpoint([(s.nutrients.get(n),g) for s,g in items],k) for k in ('low','high')]
    energy=[sum_endpoint([(s.me,g) for s,g in active],k) for k in ('low','high')]
    water=[sum_endpoint([(s.water,g) for s,g in active],k) for k in ('low','high')]
    dm=[None if w is None else mass-w for w in water[::-1]]
    def denom(b):
        factors={'PER_1000_KCAL_ME':(energy,1000),'PER_100_KCAL_ME':(energy,100),'PER_MJ_ME':(energy,1000/4.184),'PER_100G_DM':(dm,100),'PER_KG_DM':(dm,1000),'PER_100G_AS_FED':([mass,mass],100),'PER_KG_AS_FED':([mass,mass],1000),'PER_DAY':([1,1],1)}
        if b not in factors:raise ValueError('Unsupported basis')
        vv,scale=factors[b];return [None if v is None else v/scale for v in vv]
    def divide(num,den):return [None if num[0] is None or den[1] is None or den[1]<=0 else num[0]/den[1],None if num[1] is None or den[0] is None or den[0]<=0 else num[1]/den[0]]
    food_count=sum(s.source_type=='FOOD' for s,g in active)
    valid=bool(active) and min_foods<=food_count<=max_foods and set(required)<={s.id for s,g in active}
    valid=valid and all(s.minimum_g-1e-8<=g<=s.maximum_g+1e-8 and abs(g/s.quantum_g-round(g/s.quantum_g))<1e-7 for s,g in active)
    energy_pass=energy[0] is not None and energy[1] is not None and energy[0]>=target_kcal*(1-energy_tolerance)-1e-8 and energy[1]<=target_kcal*(1+energy_tolerance)+1e-8
    valid=valid and energy_pass and dm[0] is not None and dm[0]>0
    contributions=[];rows=[]
    ns=set().union(*(s.nutrients for s,g in active)) if active else set()
    ns|={b.nutrient for b in bounds if b.nutrient!='ca_p_ratio'}
    for n in sorted(ns):
        parts=[]
        for s,g in active:
            v=s.nutrients.get(n);p={'source_id':s.id,'source_type':s.source_type,'grams_per_day':g,'food_state':s.food_state,'evidence_source':v.source_id if v else None,'locator':v.locator if v else None,'minimum':None if v is None or v.low is None else v.low*g/100,'maximum':None if v is None or v.high is None else v.high*g/100,'actual':None if v is None or v.actual is None else v.actual*g/100}
            parts.append(p)
        total=interval_total(n)
        unit=next((s.nutrient_units[n] for s,g in active if n in s.nutrient_units),next((b.unit for b in bounds if b.nutrient==n),None))
        omega_mg=[None if v is None else v*(1000 if unit=='g' else 1) for v in total] if n in {'epa','dha','epa_dha'} and unit in {'g','mg'} else None
        contributions.append({'nutrient':n,'unit':unit,'daily_basis':'PER_DAY','active_omega3_mg_per_day_interval':omega_mg,'parts':parts,'food_contribution':interval_total(n,[(s,g) for s,g in active if s.source_type=='FOOD']),'supplement_contribution':interval_total(n,[(s,g) for s,g in active if s.source_type!='FOOD']),'total_intake':total,'per_1000_kcal':divide(total,[None if v is None else v/1000 for v in energy]),'actual_total':sum(p['actual'] for p in parts) if all(p['actual'] is not None for p in parts) else None})
    for b in bounds:
        required_row=b.minimum is not None or b.maximum is not None
        daily=interval_total(b.nutrient) if b.basis!='RATIO' else [None,None]
        den=interval_total('phosphorus') if b.basis=='RATIO' else denom(b.basis)
        observed=divide(interval_total('calcium') if b.basis=='RATIO' else daily,den)
        lower=b.minimum;upper=b.maximum
        if b.dependency and lower is not None:
            dep=divide(interval_total(b.dependency['nutrient_id']),den)[1]
            lower=None if dep is None else lower+max(0,dep-b.dependency['baseline'])*b.dependency['slope']
        status='NOT_ESTABLISHED' if not required_row else 'PASS'
        floor=lower*target_kcal/1000 if lower is not None and b.basis=='PER_1000_KCAL_ME' else None
        if required_row:
            if (b.minimum is not None and (lower is None or observed[0] is None)) or (upper is not None and observed[1] is None):status='UNKNOWN'
            elif (lower is not None and (observed[0]<=lower if b.strict_minimum else observed[0]<lower-1e-8)) or (upper is not None and (observed[1]>=upper if b.strict_maximum else observed[1]>upper+1e-8)):status='FAIL'
            if floor is not None and (daily[0] is None or daily[0]<floor-1e-8):status='UNKNOWN' if daily[0] is None else 'FAIL'
            valid=valid and status=='PASS'
        rows.append({'constraint_id':b.id,'nutrient':b.nutrient,'unit':b.unit,'basis':b.basis,'daily_interval':daily,'actual_on_target_basis_interval':observed,'minimum':lower,'maximum':upper,'planned_daily_minimum':floor,'status':status,'source_id':b.source_id,'source_locator':b.source_locator})
    policies=[]
    for share in food_shares:
        s=by[share['ingredient_id']];g=grams.get(s.id,0)
        if share['basis']=='FRACTION_ME':
            eh=s.me.high;el=s.me.low
            d=None if energy[0] is None or eh is None or el is None else energy[0]+(eh-el)*g/100
            actual=None if not d or eh is None else eh*g/100/d
        elif share['basis'] in {'FRACTION_MASS','FRACTION_AS_FED'}:actual=g/mass if mass else None
        else:raise ValueError('Unsupported food share basis')
        passed=actual is not None and actual<=share['maximum']+1e-8;valid=valid and passed;policies.append({'id':share['id'],'worst_case':actual,'maximum':share['maximum'],'status':'PASS' if passed else 'FAIL'})
    if budget is not None:
        cost=None if any(s.cost_per_g is None for s,g in active) else sum(s.cost_per_g*g for s,g in active)
        passed=cost is not None and cost<=budget+1e-8;valid=valid and passed;policies.append({'id':'BUDGET','actual':cost,'maximum':budget,'status':'PASS' if passed else 'FAIL'})
    return {'all_numeric_requirements_pass':bool(valid),'energy_interval_kcal_per_day':energy,'energy_status':'PASS' if energy_pass else 'FAIL','dry_matter_interval_g_per_day':dm,'total_mass_g_per_day':mass,'food_count':food_count,'supplement_count':len(active)-food_count,'rows':rows,'contributions':contributions,'policy_rows':policies,'complete_food_claim':False}


def food_first_math(existing,common_additions,supplements,bounds,target_kcal,**kwargs):
    attempts=[]
    for name,sources in [('ADJUST_EXISTING_FOODS',existing),('COMMON_FOOD_CANDIDATES',existing+common_additions),('FOOD_PLUS_STANDARDIZED_SUPPLEMENTS',existing+common_additions+supplements)]:
        r=solve_intervals(sources,bounds,target_kcal,**kwargs);attempts.append({'stage':name,'status':r['status'],'blockers':r.get('blockers',[])})
        if r['status']=='NUMERIC_PASS':return {**r,'attempts':attempts}
    return {**r,'attempts':attempts,'food_only_infeasible_proven':any(a['status']=='NO_VALID_RECIPE' and 'SIMULTANEOUS_HARD_CONSTRAINTS_INFEASIBLE' in a['blockers'] for a in attempts[:2])}


def reoptimize_math(sources,bounds,target,old,new,**kwargs):
    """Internal regression helper. Recomputes every supplement; never fixes old doses."""
    if old==new or old not in {s.id for s in sources} or new not in {s.id for s in sources}:raise ValueError('Distinct existing candidates required')
    return solve_intervals([s for s in sources if s.id!=old],bounds,target,required=[new],**kwargs)
