"""Deterministic integer dispensing MILP. All safety rules are simultaneous hard constraints.

The mathematical API is deliberately separate from clinical release. A numerical
PASS here is never, by itself, a complete-food or medical suitability claim.
"""
from dataclasses import dataclass, field
from math import isfinite
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint

@dataclass(frozen=True)
class Food:
    id: str
    nutrients: dict  # canonical amounts per 100 g as consumed; None is unknown
    me: float       # species-specific ME kcal per 100 g
    water: float    # g per 100 g
    maximum_g: float
    quantum_g: float
    minimum_g: float=0
    availability_penalty: float=0
    cost_per_g: float=0
    complexity_penalty: float=0
    source_id: str=''
    nutrient_sources: dict=field(default_factory=dict)

@dataclass(frozen=True)
class NutrientBound:
    id: str
    nutrient: str
    unit: str
    basis: str
    minimum: float|None=None
    maximum: float|None=None
    source_id: str=''
    source_locator: str=''
    dependency: dict=field(default_factory=dict)
    strict_minimum: bool=False
    strict_maximum: bool=False

class MissingComposition(ValueError):pass

def _vector(foods,nutrient):
    vals=[f.nutrients.get(nutrient) for f in foods]
    if any(v is None for v in vals):
        raise MissingComposition(nutrient+': '+','.join(f.id for f,v in zip(foods,vals) if v is None))
    if any(type(v) not in (int,float) or not isfinite(v) or v<0 for v in vals):raise ValueError('Invalid nutrient vector')
    return np.array(vals,dtype=float)/100

def _basis_vector(foods,basis):
    if basis=='PER_1000_KCAL_ME':return np.array([f.me/100/1000 for f in foods])
    if basis=='PER_100_KCAL_ME':return np.array([f.me/100/100 for f in foods])
    if basis=='PER_MJ_ME':return np.array([f.me/100*4.184/1000 for f in foods])
    if basis=='PER_100G_DM':return np.array([(1-f.water/100)/100 for f in foods])
    if basis=='PER_KG_DM':return np.array([(1-f.water/100)/1000 for f in foods])
    if basis=='PER_100G_AS_FED':return np.ones(len(foods))/100
    if basis=='PER_KG_AS_FED':return np.ones(len(foods))/1000
    raise ValueError('Unsupported linear basis '+basis)

def solve_math(foods,bounds,target_kcal,*,energy_tolerance=0,required_foods=(),budget=None,food_shares=(),diagnostic_budget=64):
    foods=sorted(foods,key=lambda f:f.id);n=len(foods)
    if not n:return {'status':'NO_VALID_RECIPE','conflicts':[{'id':'CANDIDATES_EMPTY'}]}
    if len({f.id for f in foods})!=n:raise ValueError('Duplicate foods')
    if not isfinite(target_kcal) or target_kcal<=0 or not 0<=energy_tolerance<1:raise ValueError('Invalid energy target')
    for f in foods:
        if any(not isfinite(v) for v in [f.me,f.water,f.maximum_g,f.minimum_g,f.quantum_g,f.cost_per_g,f.availability_penalty,f.complexity_penalty]):raise ValueError('Nonfinite food property')
        if f.me<0 or not 0<=f.water<100 or f.quantum_g<=0 or f.maximum_g<f.quantum_g or not 0<=f.minimum_g<=f.maximum_g:raise ValueError('Invalid dispensing/ME/water domain')
    quantum=np.array([f.quantum_g for f in foods]);rows=[];lower=[];upper=[];labels=[]
    def add(coeff,lo=-np.inf,hi=np.inf,id='',source='',locator='',binary=None):
        rows.append(np.concatenate([np.array(coeff)*quantum,np.zeros(n) if binary is None else np.array(binary)]));lower.append(lo);upper.append(hi)
        labels.append({'id':id,'source_id':source,'source_locator':locator})
    energy=np.array([f.me/100 for f in foods])
    add(energy,target_kcal*(1-energy_tolerance),target_kcal*(1+energy_tolerance),'ENERGY_BAND','PALECHO_SPEC','Explicit dispensing band; all nutrient checks still use actual ME')
    for i,f in enumerate(foods):
        unit=np.eye(n)[i];z=np.zeros(n);z[i]=-f.maximum_g
        add(unit,hi=0,id='MAX_AMOUNT:'+f.id,source=f.source_id,binary=z)
        z=np.zeros(n);z[i]=-max(f.minimum_g,f.quantum_g)
        add(unit,lo=0,id='MIN_IF_USED:'+f.id,source=f.source_id,binary=z)
        if f.id in required_foods:add(unit,lo=max(f.minimum_g,f.quantum_g),id='REQUIRED:'+f.id)
    if not set(required_foods)<={f.id for f in foods}:return {'status':'NO_VALID_RECIPE','conflicts':[{'id':'REQUIRED_FOOD_NOT_ELIGIBLE'}]}
    try:
        for b in bounds:
            if b.minimum is None and b.maximum is None:continue
            if b.basis=='RATIO':
                if b.nutrient!='ca_p_ratio':raise ValueError('Unsupported ratio')
                vec=_vector(foods,'calcium');den=_vector(foods,'phosphorus')
            else:
                vec=_vector(foods,b.nutrient);den=None if b.basis=='PER_DAY' else _basis_vector(foods,b.basis)
            if b.minimum is not None:
                lo=b.minimum+(max(1,abs(b.minimum))*1e-7 if b.strict_minimum else 0)
                add(vec if den is None else vec-lo*den,lo=lo if den is None else 0,id=b.id+':MIN',source=b.source_id,locator=b.source_locator)
                # Actual daily intake must also meet the planned daily intake, even at the low end of the energy band.
                if b.basis=='PER_1000_KCAL_ME':add(vec,lo=b.minimum*target_kcal/1000,id=b.id+':DAILY_MIN',source=b.source_id)
                if b.dependency:
                    dep=b.dependency;dv=_vector(foods,dep['nutrient_id']);slope=dep['slope']
                    if den is None:raise ValueError('Dependency requires a concentration basis')
                    add(vec-slope*dv-(lo-slope*dep['baseline'])*den,lo=0,id=b.id+':DEPENDENCY',source=b.source_id,locator=dep['source_locator'])
            if b.maximum is not None:
                hi=b.maximum-(max(1,abs(b.maximum))*1e-7 if b.strict_maximum else 0)
                add(vec if den is None else vec-hi*den,hi=hi if den is None else 0,id=b.id+':MAX',source=b.source_id,locator=b.source_locator)
        for share in food_shares:
            i=next(i for i,f in enumerate(foods) if f.id==share['ingredient_id'])
            den=energy if share['basis']=='FRACTION_ME' else np.ones(n)
            vec=np.zeros(n);vec[i]=den[i]
            add(vec-share['maximum']*den,hi=0,id=share['id'],source=share['source_id'])
    except MissingComposition as e:return {'status':'UNKNOWN_COMPOSITION','reasons':[str(e)]}
    if budget is not None:add(np.array([f.cost_per_g for f in foods]),hi=budget,id='BUDGET')
    integrality=np.ones(n*2);domain=Bounds(np.zeros(n*2),np.concatenate([np.floor(np.array([f.maximum_g for f in foods])/quantum),np.ones(n)]))
    def run(objective,indices=None,extra=()):
        ids=list(range(len(rows))) if indices is None else list(indices)
        aa=[rows[i] for i in ids]+[e[0] for e in extra]
        ll=[lower[i] for i in ids]+[e[1] for e in extra];uu=[upper[i] for i in ids]+[e[2] for e in extra]
        return milp(c=objective,integrality=integrality,bounds=domain,
                    constraints=LinearConstraint(np.array(aa).reshape((-1,n*2)),np.array(ll),np.array(uu)),
                    options={'presolve':True,'mip_rel_gap':0,'time_limit':30})
    feasibility=run(np.zeros(n*2))
    if feasibility.status==2:
        active=list(range(len(rows)));calls=0
        for k in list(active):
            if calls>=diagnostic_budget:break
            candidate=[j for j in active if j!=k];rr=run(np.zeros(n*2),candidate);calls+=1
            if rr.status==2:active=candidate
        return {'status':'NO_VALID_RECIPE','conflicts':[labels[i] for i in active],
                'diagnostic':'Irreducible subset relative to dispensing domains' if calls==len(rows) else 'Conflict subset; diagnostic budget reached, not certified minimal',
                'relaxed_constraints':False}
    if feasibility.status!=0:return {'status':'SOLVER_ERROR','reason':feasibility.message,'no_recipe_returned':True}
    # Lexicographic objectives; no safety slack, no arbitrary weighted tradeoff against nutrients.
    objectives=[np.r_[np.zeros(n),[f.availability_penalty for f in foods]],
                np.r_[[f.cost_per_g*f.quantum_g for f in foods],np.zeros(n)],
                np.r_[np.zeros(n),np.ones(n)],
                np.r_[np.zeros(n),[f.complexity_penalty for f in foods]]]
    # Final per-variable lexicographic fixing makes alternate optima reproducible.
    objectives.extend(np.eye(n*2)[i] for i in range(n))
    fixed=[];result=feasibility;objective_values=[]
    for objective in objectives:
        if not np.any(objective):continue
        result=run(objective,extra=fixed)
        if result.status!=0:return {'status':'SOLVER_ERROR','reason':result.message,'no_recipe_returned':True}
        integer=np.rint(result.x)
        if np.max(abs(result.x-integer))>1e-5:return {'status':'SOLVER_ERROR','reason':'Noninteger dispensing result'}
        optimum=float(objective@integer);objective_values.append(optimum)
        fixed.append((objective,optimum-1e-8,optimum+1e-8))
    counts=np.rint(result.x[:n]);grams={f.id:float(counts[i]*f.quantum_g) for i,f in enumerate(foods) if counts[i]>0}
    audit=audit_math(foods,bounds,grams,target_kcal,energy_tolerance,food_shares=food_shares,budget=budget)
    if not audit['all_numeric_requirements_pass']:
        return {'status':'NO_VALID_RECIPE','reason':'Final dispensed quantities failed independent re-audit','audit':audit,'relaxed_constraints':False}
    return {'status':'NUMERIC_PASS','grams':grams,'audit':audit,'objective_values':objective_values,
            'method':'SCIPY_HIGHS_MILP_INTEGER_DISPENSING_LEXICOGRAPHIC','clinical_release':False}

def audit_math(foods,bounds,grams,target_kcal,energy_tolerance=0,*,food_shares=(),budget=None):
    by_id={f.id:f for f in foods}
    if len(by_id)!=len(foods):raise ValueError('Duplicate foods')
    if not isfinite(target_kcal) or target_kcal<=0 or not 0<=energy_tolerance<1:raise ValueError('Invalid energy target')
    if set(grams)-set(by_id):raise ValueError('Unknown recipe ingredient')
    for g in grams.values():
        if type(g) not in (float,int) or not isfinite(g) or g<0:raise ValueError('Invalid ingredient amount')
    active=[(by_id[i],g) for i,g in grams.items() if g>0]
    for f,g in active:
        if any(type(v) not in (int,float) or not isfinite(v) for v in [f.me,f.water,f.maximum_g,f.minimum_g,f.quantum_g,f.cost_per_g]):raise ValueError('Nonfinite food property')
        if f.me<0 or not 0<=f.water<100 or f.quantum_g<=0 or f.maximum_g<f.quantum_g or not 0<=f.minimum_g<=f.maximum_g:raise ValueError('Invalid dispensing/ME/water domain')
    mass=sum(g for f,g in active);me=sum(f.me*g/100 for f,g in active);dm=sum((1-f.water/100)*g for f,g in active)
    def total(n):
        values=[f.nutrients.get(n) for f,g in active]
        if any(v is not None and (type(v) not in (int,float) or not isfinite(v) or v<0) for v in values):raise ValueError('Invalid nutrient vector: '+n)
        return None if any(v is None for v in values) else sum(v*g/100 for v,(f,g) in zip(values,active))
    rows=[];valid=bool(active) and me>0 and dm>0
    energy_pass=target_kcal*(1-energy_tolerance)-1e-8<=me<=target_kcal*(1+energy_tolerance)+1e-8
    valid=valid and energy_pass
    for f,g in active:
        if not f.minimum_g-1e-8<=g<=f.maximum_g+1e-8 or abs(g/f.quantum_g-round(g/f.quantum_g))>1e-7:valid=False
    policy=[]
    for s in food_shares:
        g=grams.get(s['ingredient_id'],0);f=by_id[s['ingredient_id']]
        actual=(g*f.me/100/me if me>0 else None) if s['basis']=='FRACTION_ME' else (g/mass if mass>0 else None)
        passed=actual is not None and actual<=s['maximum']+1e-8
        policy.append({'id':s['id'],'actual':actual,'maximum':s['maximum'],'basis':s['basis'],'status':'PASS' if passed else 'FAIL','source_id':s['source_id']});valid=valid and passed
    if budget is not None:
        cost=sum(f.cost_per_g*g for f,g in active);passed=cost<=budget+1e-8
        policy.append({'id':'BUDGET','actual':cost,'maximum':budget,'unit':'CNY_PER_DAY','status':'PASS' if passed else 'FAIL'});valid=valid and passed
    for b in bounds:
        daily=None if b.nutrient=='ca_p_ratio' else total(b.nutrient)
        factor={'PER_DAY':1,'PER_1000_KCAL_ME':me/1000,'PER_100_KCAL_ME':me/100,'PER_MJ_ME':me*4.184/1000,'PER_100G_DM':dm/100,'PER_KG_DM':dm/1000,'PER_100G_AS_FED':mass/100,'PER_KG_AS_FED':mass/1000}.get(b.basis)
        if b.basis=='RATIO':
            ca=total('calcium');p=total('phosphorus');actual=None if ca is None or p is None or p<=0 else ca/p
        else:actual=None if daily is None or not factor else daily/factor
        lo=b.minimum;dependency_unknown=False
        if b.dependency and lo is not None:
            dep=total(b.dependency['nutrient_id'])
            if dep is None or not factor:dependency_unknown=True
            else:lo+=max(0,dep/factor-b.dependency['baseline'])*b.dependency['slope']
        required=lo is not None or b.maximum is not None
        status='NOT_ESTABLISHED'
        planned_floor=lo*target_kcal/1000 if lo is not None and b.basis=='PER_1000_KCAL_ME' else None
        if required:
            status='UNKNOWN' if actual is None or dependency_unknown else 'PASS'
            if status=='PASS':
                tol=1e-8
                if lo is not None and (actual<=lo if b.strict_minimum else actual<lo-tol):status='FAIL'
                if b.maximum is not None and (actual>=b.maximum if b.strict_maximum else actual>b.maximum+tol):status='FAIL'
                if planned_floor is not None and (daily is None or daily<planned_floor-tol):status='FAIL'
            if status!='PASS':valid=False
        rows.append({'constraint_id':b.id,'nutrient_id':b.nutrient,'actual_daily':daily,
                     'actual_per_1000_kcal_ME':None if daily is None or me<=0 else daily/me*1000,
                     'actual_per_100g_DM':None if daily is None or dm<=0 else daily/dm*100,
                     'actual_on_target_basis':actual,'minimum':lo,'maximum':b.maximum,'minimum_daily':None if lo is None or factor is None else max(lo*factor,planned_floor or 0),
                     'maximum_daily':None if b.maximum is None or factor is None else b.maximum*factor,
                     'target_interval':[lo,b.maximum],'unit':b.unit,'basis':b.basis,'strict_minimum':b.strict_minimum,'strict_maximum':b.strict_maximum,
                     'status':status,'required':required,'source_id':b.source_id,'source_locator':b.source_locator,
                     'ingredient_sources':[{'ingredient_id':f.id,**f.nutrient_sources.get(b.nutrient,{'source_id':f.source_id})} for f,g in active]})
    return {'actual_kcal_ME_per_day':me,'total_g_per_day':mass,'dry_matter_g_per_day':dm,
            'energy_status':'PASS' if energy_pass else 'FAIL','rows':rows,'all_numeric_requirements_pass':bool(valid),
            'policy_rows':policy,'complete_food_claim':False}
