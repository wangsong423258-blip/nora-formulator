"""All-and-only selected gram variables; no food-use binary or cost objective.

Hard constraints are simultaneous. Lexicographic preferences operate only
inside that feasible set. Unknown nutrients are not numerical coefficients.
"""
import math
import sys
import time
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp, linprog
from .ingredient_first_repository import ANIMAL, CORE_ANIMAL
from .freshfood_contract import ContractError

PRIORITIES=['P0_FOOD_SAFETY','P1_DISEASE_HARD','P2_SPECIES','P3_LIFE_STAGE',
 'P4_ENERGY','P5_IMPORTANT_NUTRIENTS','P6_FIXED_USER_SET','P7_MEANINGFUL_AMOUNT',
 'P8_DISEASE_SOFT','P9_CATEGORY_DOMINANCE','P10_KITCHEN_PRACTICALITY']

def nutrient_vector(foods,n):
    values=[f['nutrients_per_100g'].get(n) for f in foods]
    if any(v is None for v in values):raise ValueError('UNKNOWN_NUTRIENT_COEFFICIENT:'+n)
    return np.array(values,dtype=float)/100

def energy_vector(foods,m):
    coefficients=m.get('pet_me_coefficients')
    return np.array([coefficients[f['ingredient_id']] for f in foods],dtype=float)/100 if coefficients else nutrient_vector(foods,'energy')

def constraints_for(foods,m,repo):
    p=repo.policy;sp=m['species'];target=m['target'];n=len(foods)
    e=energy_vector(foods,m);protein=nutrient_vector(foods,'protein');fat=nutrient_vector(foods,'fat')
    rows=[]
    def add(code,v,lo=-math.inf,hi=math.inf,kind='ENGINEERING_LIMIT',rule=None):
        rows.append({'constraint_id':code,'coefficients':list(map(float,v)),
          'minimum':None if not math.isfinite(lo) else float(lo),'maximum':None if not math.isfinite(hi) else float(hi),
          'classification':kind,'rule_id':rule or 'USER_SELECTED_SET'})
    tol=p['energy_tolerance']
    add('ENERGY',e,target*(1-tol),target*(1+tol),'ENGINEERING_LIMIT','ENG_ENERGY_TOLERANCE')
    for name,v in [('PROTEIN',protein),('FAT',fat)]:
        r=m['nutrient_targets'][name.lower()];minimum=r['minimum_g_per_1000kcal'];rid=r['rule_id']
        add(name+'_MINIMUM',v,minimum*target/1000,kind='SCIENTIFIC_REFERENCE_SCREEN',rule=rid)
        add(name+'_DENSITY',v-minimum*e/1000,0,kind='SCIENTIFIC_REFERENCE_SCREEN',rule=rid)
    if m['fat_max'] is not None:
        add('DISEASE_FAT_MAX',fat-m['fat_max']*e/1000,hi=0,kind='DISEASE_LIMIT',rule='DOG_PANCREATITIS_FAT')
    if sp=='DOG' and 'COPPER_HEPATOPATHY' in m['diseases']:
        # ACVIM 2019, confirmed copper-associated hepatitis: <0.12 mg/100 kcal.
        # Strict inequality represented below 1.2 mg/1000 kcal by 1e-6 mg.
        add('DISEASE_COPPER_MAX',nutrient_vector(foods,'copper')-1.2*e/1000,
            hi=-1e-6,kind='DISEASE_LIMIT',rule='COPPER_HEPATOPATHY')
    add('FAT_DOMINANCE',fat-p['max_fat_g_per_1000kcal'][sp]*e/1000,hi=0,rule='ENG_MAX_FAT_G_PER_1000KCAL')
    animal=protein*np.array([f['category'] in ANIMAL for f in foods])
    add('ANIMAL_PROTEIN_CORE',animal-p['animal_protein_share'][sp]*protein,0,rule='ENG_ANIMAL_PROTEIN_SHARE')
    all_food=np.ones(n)
    for cat,maximum in p['category_mass_max'][sp].items():
        present=np.array([float(f['category']==cat) for f in foods])
        if np.any(present):add('CATEGORY_MASS_MAX:'+cat,present-maximum*all_food,hi=0,rule='ENG_CATEGORY_MASS_MAX')
    for cat,maximum in p['category_energy_max'][sp].items():
        present=np.array([float(f['category']==cat) for f in foods])
        if np.any(present):add('CATEGORY_ENERGY_MAX:'+cat,e*present-maximum*e,hi=0,rule='ENG_CATEGORY_ENERGY_MAX')
    core=np.array([float(f['category'] in CORE_ANIMAL) for f in foods])
    lower=[];upper=[];minima={}
    for j,f in enumerate(foods):
        unit=np.eye(n)[j];cat=f['category'];oil=cat=='FAT_OIL'
        scale=p['oil_minimum_scale_g'] if oil else p['minimum_scale_g']
        weight_term=0 if oil else p['minimum_weight_factor']*math.sqrt(m['weight_kg'])
        energy_term=target*p['animal_min_energy_fraction']/e[j] if cat in CORE_ANIMAL else 0
        minimum=math.ceil(max(scale,weight_term,energy_term)/p['quantum_g'])*p['quantum_g']
        maximum=math.floor(target*(1+tol)/e[j]/p['quantum_g'])*p['quantum_g']
        lower.append(minimum);upper.append(maximum)
        minima[f['ingredient_id']]={'minimum_amount_g':minimum,'mass_fraction_minimum':p['minimum_mass_fraction'][cat],
          'classification':'ENGINEERING_HEURISTIC','rule_ids':['ENG_MINIMUM_SCALE_G','ENG_MINIMUM_WEIGHT_FACTOR','ENG_ANIMAL_MIN_ENERGY_FRACTION','ENG_MINIMUM_MASS_FRACTION'],
          'inputs':{'body_weight_kg':m['weight_kg'],'target_kcal':target,'energy_kcal_per_g':float(e[j]),'category':cat,'scale_g':scale}}
        add('MEANINGFUL_ABSOLUTE:'+f['ingredient_id'],unit,minimum,rule='ENG_MINIMUM_SCALE_G')
        add('INGREDIENT_MAX:'+f['ingredient_id'],unit,hi=maximum,rule='ENG_ENERGY_TOLERANCE')
        add('MEANINGFUL_RELATIVE:'+f['ingredient_id'],unit-p['minimum_mass_fraction'][cat]*all_food,0,rule='ENG_MINIMUM_MASS_FRACTION')
        if core[j] and sum(core)>1:
            add('SINGLE_CORE_DOMINANCE:'+f['ingredient_id'],unit-p['core_ingredient_mass_max_when_multi']*core,hi=0,rule='ENG_CORE_INGREDIENT_MASS_MAX_WHEN_MULTI')
    add('EXCESSIVE_RECIPE_MASS',all_food,hi=target*p['max_mass_g_per_kcal'][sp],rule='ENG_MAX_MASS_G_PER_KCAL')
    return rows,np.array(lower),np.array(upper),minima

def evaluate_rows(rows,amounts,tolerance):
    out=[]
    for r in rows:
        value=math.fsum(float(a)*float(b) for a,b in zip(r['coefficients'],amounts))
        lo=r['minimum'];hi=r['maximum'];ok=math.isfinite(value) and (lo is None or value>=lo-tolerance) and (hi is None or value<=hi+tolerance)
        out.append({k:v for k,v in r.items() if k!='coefficients'}|{'value':value,'status':'PASS' if ok else 'FAIL',
          'slack_to_minimum':None if lo is None else value-lo,'slack_to_maximum':None if hi is None else hi-value})
    return out

def feasibility_diagnostic(rows,lower,upper):
    """Elastic witness only. Never return diagnostic grams as a recipe."""
    n=len(lower);a=[];b=[];labels=[]
    for row in rows:
        if row['minimum'] is not None:a.append(-np.array(row['coefficients']));b.append(-row['minimum']);labels.append(row['constraint_id'])
        if row['maximum'] is not None:a.append(np.array(row['coefficients']));b.append(row['maximum']);labels.append(row['constraint_id'])
    A=np.array(a);B=np.array(b);scale=np.maximum(np.maximum(abs(B),np.max(abs(A),axis=1)),1)
    d=linprog(np.r_[np.zeros(n),np.ones(len(B))],A_ub=np.c_[A/scale[:,None],-np.eye(len(B))],b_ub=B/scale,
        bounds=[(0,None)]*(n+len(B)),method='highs',options={'time_limit':2.0,'maxiter':10000})
    if d.status==1:raise ContractError('RECIPE_SOLVER_TIMEOUT')
    return {'affected_constraint':sorted({labels[i] for i,v in enumerate(d.x[n:]) if v>1e-7}) if d.success else ['SIMULTANEOUS_CONSTRAINTS'],
      'diagnostic_scope':'ELASTIC_CONFLICT_WITNESS_NOT_MINIMAL_UNSAT_CORE','relaxed_recipe_released':False}

class ScientificRecipeSolver:
    def __init__(self,repository):self.repo=repository

    def solve(self,foods,m):
        if sys.platform != 'emscripten':
            from .solver_boundary import solve
            return solve(foods,m,self.repo.policy)
        return self._solve_inline(foods,m)

    def _solve_inline(self,foods,m):
        foods=sorted(foods,key=lambda f:f['ingredient_id']);p=self.repo.policy;n=len(foods)
        end=time.monotonic()+p['solver_time_limit_seconds']
        rows,low,high,minima=constraints_for(foods,m,self.repo)
        if any(high<low):return {'status':'INFEASIBLE','grams':{},'constraints':rows,'meaningful_minima':minima,**feasibility_diagnostic(rows,low,high)}
        e=energy_vector(foods,m);target=m['target'];sp=m['species']
        # Continuous deviation variables are not food adoption variables.
        preferences=[('ENERGY',e,target),
          ('PROTEIN',nutrient_vector(foods,'protein'),max(m['nutrient_targets']['protein']['minimum_g_per_1000kcal'],p['protein_preference_g_per_1000kcal'][sp])*target/1000),
          ('FAT',nutrient_vector(foods,'fat'),min(m['fat_max'] if m['fat_max'] is not None else p['fat_preference_g_per_1000kcal'][sp],p['fat_preference_g_per_1000kcal'][sp])*target/1000)]
        if any(f['category']=='FIBER_VEGETABLE' for f in foods) and all(f['nutrients_per_100g']['fiber'] is not None for f in foods):
            preferences.append(('FIBER',nutrient_vector(foods,'fiber'),p['fiber_preference_g_per_1000kcal'][sp]*target/1000))
        dim=n+len(preferences);A=[np.r_[r['coefficients'],np.zeros(len(preferences))] for r in rows]
        L=[-np.inf if r['minimum'] is None else r['minimum'] for r in rows];U=[np.inf if r['maximum'] is None else r['maximum'] for r in rows]
        for j,(name,v,goal) in enumerate(preferences):
            positive=np.r_[v,np.zeros(len(preferences))];positive[n+j]=-1
            negative=np.r_[-v,np.zeros(len(preferences))];negative[n+j]=-1
            # Energy estimates do not justify searching for sub-calorie integer
            # coincidences. Zero loss inside the registered kitchen deadband.
            band=p['energy_objective_slack_fraction']*target if name=='ENERGY' else 0
            A.extend([positive,negative]);L.extend([-np.inf,-np.inf]);U.extend([goal+band,-goal+band])
        domains=Bounds(np.r_[low,np.zeros(len(preferences))],np.r_[high,np.full(len(preferences),np.inf)])
        integer=np.r_[np.ones(n),np.zeros(len(preferences))]
        objectives=[]
        c=np.zeros(dim);c[n]=1;objectives.append(('P4_ENERGY_TARGET_DEVIATION',c,0))
        c=np.zeros(dim)
        for j,(_,v,goal) in enumerate(preferences[1:],1):c[n+j]=1/max(goal,1e-12)
        objectives.append(('P5_NORMALIZED_NUTRIENT_PREFERENCE',c,p['nutrient_objective_slack']))
        skipped=[]
        for nutrient in m['soft_nutrients']:
            if any(f['nutrients_per_100g'].get(nutrient) is None for f in foods):
                skipped.append({'nutrient':nutrient,'reason':'UNKNOWN_CONCENTRATION_NOT_ZERO'});continue
            c=np.r_[nutrient_vector(foods,nutrient),np.zeros(len(preferences))]
            objectives.append(('P8_DISEASE_LOWER_'+nutrient.upper(),c,None))
        if m['soft_nutrients']:
            # P5 evidence-derived minima are hard constraints above. Optional
            # engineering preference anchors must not neutralize a disease
            # direction, so apply those anchors after disease soft objectives.
            _,preference,slack=objectives.pop(1)
            objectives.append(('P9_ENGINEERING_NUTRIENT_PREFERENCE',preference,slack))
        # All selected ingredients already satisfy relative minima and dominance
        # ceilings. Practical mass, not price or food count, is the last goal.
        objectives.append(('P10_PRACTICAL_TOTAL_MASS',np.r_[np.ones(n),np.zeros(len(preferences))],0))
        trace=[];result=None
        for name,c,allowance in objectives:
            def optimize(objective):
                remaining=end-time.monotonic()
                if remaining<=0:raise ContractError('RECIPE_SOLVER_TIMEOUT')
                options={'mip_rel_gap':0,'time_limit':remaining,'node_limit':10000,
                         'simplex_iteration_limit':10000,'ipm_iteration_limit':10000,'threads':1}
                # This engineering preference already permits an absolute loss.
                # Proving a smaller gap wastes nodes without changing its policy.
                if allowance is not None and allowance>0:options['mip_abs_gap']=allowance
                if allowance is None:
                    # A density tolerance is per kcal. Split its error budget
                    # between the fractional iteration and its inner MIP proof.
                    options['mip_abs_gap']=p['numeric_tolerance']*target*(1-p['energy_tolerance'])/2
                candidate=milp(objective,integrality=integer,bounds=domains,constraints=LinearConstraint(np.array(A),np.array(L),np.array(U)),
                        options=options)
                # HiGHS 1.8 presolve can also report false infeasibility on the
                # first objective (reproduced with a feasible integer witness).
                if candidate.status==2:
                    options['time_limit']=end-time.monotonic()
                    if options['time_limit']<=0:raise ContractError('RECIPE_SOLVER_TIMEOUT')
                    candidate=milp(objective,integrality=integer,bounds=domains,constraints=LinearConstraint(np.array(A),np.array(L),np.array(U)),
                        options={**options,'presolve':False})
                # SciPy 1.15 / HiGHS 1.8 maps a node limit to status 4 / 16,
                # not status 1. Never disguise an exhausted budget as infeasibility.
                message=str(candidate.message).lower()
                if candidate.status==1 or any(label in message for label in ('solution limit','node limit','iteration limit','time limit')):
                    raise ContractError('RECIPE_SOLVER_TIMEOUT')
                return candidate
            density=name.startswith('P8_DISEASE_LOWER_')
            density_trace=[]
            if density:
                # Dinkelbach fractional optimization: minimize nutrient/reference
                # kcal, not its absolute amount (which could just lower calories).
                energy=np.r_[e,np.zeros(len(preferences))]
                ratio=float(c@result.x/(energy@result.x))
                for _ in range(p['density_iterations']):
                    candidate=optimize(c-ratio*energy)
                    if candidate.status!=0:result=candidate;break
                    new_ratio=float(c@candidate.x/(energy@candidate.x))
                    density_trace.append(new_ratio);result=candidate
                    certificate_gap=max(0,float(candidate.fun-candidate.mip_dual_bound))
                    if abs(new_ratio-ratio)+certificate_gap/(target*(1-p['energy_tolerance']))<=p['numeric_tolerance']:break
                    ratio=new_ratio
                else:
                    return {'status':'SOLVER_UNRESOLVED','grams':{},'constraints':rows,'meaningful_minima':minima,
                      'affected_constraint':['DENSITY_CONVERGENCE'],'objectives':trace}
            else:result=optimize(c)
            if result.status!=0:
                return {'status':'INFEASIBLE' if result.status==2 and not trace else 'SOLVER_UNRESOLVED','grams':{},
                  'solver_message':result.message,'constraints':rows,'meaningful_minima':minima,'objectives':trace,
                  **feasibility_diagnostic(rows,low,high)}
            value=float(c@result.x)
            slack=abs(value)*p['disease_objective_slack'] if allowance is None else allowance
            bound=value if density else float(getattr(result,'mip_dual_bound',value))
            # Use the certified lower bound, not incumbent+allowance, so the
            # original preference envelope is never widened by the solver gap.
            ceiling=bound+slack if allowance is not None and allowance>0 else value+slack
            if value>ceiling+p['numeric_tolerance']:raise ContractError('RECIPE_SOLVER_FAILED')
            trace.append({'priority':name,'optimum':value,'allowed_objective_slack':slack,
              'certified_objective_lower_bound':None if density else bound,'certified_absolute_gap':None if density else max(0,value-bound),
              'pinned_objective_ceiling':ceiling,'optimum_is_exact':not density and abs(value-bound)<=p['numeric_tolerance'],
              'density_optimality_error_bound':None if not density else abs(new_ratio-ratio)+certificate_gap/(target*(1-p['energy_tolerance'])),
              'density_per_reference_kcal':density_trace[-1] if density_trace else None,'density_iterations':density_trace,
              'energy_deadband_kcal':p['energy_objective_slack_fraction']*target if name.startswith('P4') else None,
              'safety_constraints_relaxed':False,'engineering_rule_ids':['ENG_NUTRIENT_OBJECTIVE_SLACK','ENG_DISEASE_OBJECTIVE_SLACK']})
            A.append(c-density_trace[-1]*(1+p['disease_objective_slack'])*energy if density else c)
            L.append(-np.inf);U.append(p['numeric_tolerance'] if density else ceiling+p['numeric_tolerance'])
        amounts=np.rint(result.x[:n]);grams={f['ingredient_id']:float(amounts[j]) for j,f in enumerate(foods)}
        audit=evaluate_rows(rows,amounts,p['numeric_tolerance'])
        if any(r['status']=='FAIL' for r in audit):
            return {'status':'AUDIT_FAILED','grams':{},'constraint_audit':audit,'constraints':rows,'meaningful_minima':minima,'objectives':trace}
        why={}
        for j,f in enumerate(foods):
            probe=amounts.copy();probe[j]=100
            violations=[r['constraint_id'] for r in evaluate_rows(rows,probe,p['numeric_tolerance']) if r['status']=='FAIL']
            binding=[r['constraint_id'] for r in audit if any(v is not None and abs(v)<p['numeric_tolerance'] for v in [r['slack_to_minimum'],r['slack_to_maximum']]) and rows[audit.index(r)]['coefficients'][j]!=0]
            why[f['ingredient_id']]={'amount_g':grams[f['ingredient_id']],
              'method':'ALL_SELECTED_GRAMS_INTEGER_OPTIMIZATION','fixed_user_input':True,
              'nutrient_vector_record_sha256':f['record_sha256'],'meaningful_minimum':minima[f['ingredient_id']],
              'binding_constraints':binding,'energy_contribution_kcal':grams[f['ingredient_id']]*e[j],
              'counterfactual_100g_other_amounts_fixed':{'violated_constraints':violations,'feasible':not violations},
              'explanation':'This amount belongs to a jointly optimized selected set. It is not a unique biological requirement; feasible alternatives can differ in nutrient preferences, disease direction and practical mass.'}
        return {'status':'SOLVED','grams':grams,'constraints':rows,'constraint_audit':audit,'meaningful_minima':minima,
          'objectives':trace,'why_each_selected_ingredient_amount':why,'skipped_objectives':skipped,
          'variable_names':[f['ingredient_id']+'_g' for f in foods],'food_adoption_variables':False,
          'priority_order':PRIORITIES,'method':'SCIPY_HIGHS_FIXED_SET_INTEGER_GRAMS',
          'equal_split_used':False,'cost_objective_used':False,'simplification_used':False}

class CombinationFeasibilityCheck:
    def __init__(self,repository):self.solver=ScientificRecipeSolver(repository)
    def check(self,foods,model):return self.solver.solve(foods,model)
