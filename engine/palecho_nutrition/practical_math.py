"""Deterministic rounded-food / precise-powder V1 reference screening.

This is NOT the advanced ME or interval certifier. Minimum screening credits
known food and declared supplement contributions only. Upper screening reports
unquantified background explicitly and must not be called a total assay.
"""
import math
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint, linprog

TOL=.05

def _legal_limit(b):return 'EU_LEGAL_POLICY_CEILING' in b.id

def _declared_adders(sources,n):
    # FEDIAF2025 §3.1.3 p11: the EU legal maximum applies when that
    # specific nutrient is added as an additive; then it covers total content.
    # Other additives do not trigger a legal limit on naturally occurring Se.
    return [i for i,s in enumerate(sources) if s['type']!='FOOD' and (s['values'].get(n) or 0)>0]

def _v(sources,n,upper=False):
    # Zero here means zero CREDIT to a subtotal, not a zero concentration.
    return np.array([(s['upper' if upper else 'values'].get(n) or 0)/100 for s in sources])

def _den(sources,basis,upper=False):
    if basis=='PER_1000_KCAL_ME':return np.array([s['energy_high' if upper else 'energy_low']/1000 for s in sources])
    if basis=='PER_100G_DM':return np.array([s['dm_low']/100 for s in sources])
    if basis=='PER_KG_DM':return np.array([s['dm_low']/1000 for s in sources])
    if basis=='PER_DAY':return np.ones(len(sources))*0
    raise ValueError('Unsupported practical reference basis '+basis)


def solve_reference(sources,bounds,target,required=(),price_map=None,budget=None,species='DOG',continuity_reference=None,*,design_policy=None):
    n=len(sources)
    composition=(design_policy or {}).get('recipe_composition_policy')
    if not n:return {'status':'INFEASIBLE','blockers':['NO_ELIGIBLE_SOURCES']}
    ids={s['id'] for s in sources}
    if not set(required)<=ids:return {'status':'INFEASIBLE','blockers':['REQUIRED_FOOD_UNAVAILABLE:'+x for x in required if x not in ids]}
    missing=sorted({b.nutrient for b in bounds if b.minimum is not None and b.minimum>0 and b.basis!='RATIO' and not any((s['values'].get(b.nutrient) or 0)>0 for s in sources)})
    if missing:
        return {'status':'INFEASIBLE','blockers':['NO_RELIABLE_MINIMUM_CONTRIBUTION:'+n for n in missing],
                'diagnostic_scope':'No eligible source currently supplies a quantified positive contribution; unquantified food content is not claimed absent.',
                'relaxed_recipe_released':False}
    q=np.array([s['quantum'] for s in sources]);rows=[];lower=[];upper=[];labels=[]
    def add(v,lo=-np.inf,hi=np.inf,label='',binary=None):
        rows.append(np.r_[v*q,np.zeros(n) if binary is None else binary]);lower.append(lo);upper.append(hi);labels.append(label)
    food=np.array([s['type']=='FOOD' for s in sources],float);supp=1-food
    food_count_max=n if (design_policy or {}).get('soft_component_count_only') else 7
    add(np.zeros(n),1 if composition else 2,food_count_max,'HOUSEHOLD_FOOD_COUNT',food)
    if design_policy:
        animal_categories={'MEAT','POULTRY','FISH'}
        add(np.zeros(n),lo=1,label='DESIGN_ANIMAL_PROTEIN',binary=np.array([float(s['category'] in animal_categories) for s in sources]))
        if species=='DOG' and not composition:
            add(np.zeros(n),lo=1,label='DESIGN_FIBER_VEGETABLE',binary=np.array([float(s['category']=='VEGETABLE') for s in sources]))
        for typ in sorted({s.get('supplement_type') for s in sources if s.get('supplement_type')}):
            add(np.zeros(n),hi=1,label='DESIGN_NO_DUPLICATE:'+typ,binary=np.array([float(s.get('supplement_type')==typ) for s in sources]))
    for j,s in enumerate(sources):
        u=np.eye(n)[j];add(u,hi=0,label='AMOUNT_CAP:'+s['id'],binary=-u*s['cap']);add(u,lo=0,label='DISPENSING_QUANTUM:'+s['id'],binary=-u*s.get('minimum_portion_g',q[j]))
        if s['id'] in required:add(u,lo=q[j],label='REQUIRED:'+s['id'])
        if s.get('fixed_dose') is not None:add(u,lo=s['fixed_dose'],hi=s['fixed_dose'],label='LABEL_DAILY_DOSE:'+s['id'])
        if s.get('food_dose_factor') is not None:add(u-s['food_dose_factor']*food,lo=0,hi=0,label='LABEL_FOOD_MASS_DOSE:'+s['id'])
    el=np.array([s['energy_low'] for s in sources]);eh=np.array([s['energy_high'] for s in sources])
    add(el,lo=target*(1-TOL),label='REFERENCE_ENERGY_MIN');add(eh,hi=target*(1+TOL),label='REFERENCE_ENERGY_MAX_WITH_POWDER_ENVELOPE')
    dm=np.array([s['dm_low'] for s in sources]);add(dm,lo=.001,label='POSITIVE_FOOD_DRY_MATTER')
    for b in bounds:
        if b.minimum is None and b.maximum is None:continue
        if b.basis=='RATIO':
            lo_v=hi_v=_v(sources,'calcium');dl=dh=_v(sources,'phosphorus');add(dl,lo=.001,label='POSITIVE_PHOSPHORUS')
        else:
            lo_v=_v(sources,b.nutrient);hi_v=_v(sources,b.nutrient,True)
            dl=_den(sources,b.basis);dh=_den(sources,b.basis,True)
        if b.minimum is not None:
            add(lo_v-b.minimum*dh,lo=0,label=b.id+':MIN')
            if b.basis=='PER_1000_KCAL_ME':add(lo_v,lo=b.minimum*target/1000,label=b.id+':DAILY_FLOOR')
            if b.dependency:
                d=b.dependency;pv=_v(sources,d['nutrient_id'],True);slope=d['slope'];base=b.minimum-slope*d['baseline']
                add(lo_v-slope*pv-base*dh,lo=0,label=b.id+':PROTEIN_DEPENDENCY')
                add(lo_v-slope/(1-TOL)*pv,lo=base*target/1000,label=b.id+':DEPENDENT_DAILY_FLOOR')
        if b.maximum is not None:
            v=hi_v-b.maximum*dl
            if _legal_limit(b):
                for adder in _declared_adders(sources,b.nutrient):
                    big_m=sum(max(0,float(a))*s['cap'] for a,s in zip(v,sources))
                    trigger=np.eye(n)[adder]*big_m
                    add(v,hi=big_m,label=b.id+':MAX_IF_SPECIFIC_ADDITIVE:'+sources[adder]['id'],binary=trigger)
            else:add(v,hi=0,label=b.id+':MAX')
    # API 1.5: reserve a feasible target range BEFORE choosing food. A daily
    # micronutrient requirement cannot exceed its reference dry-matter ceiling
    # after planned addition. No product concentration or dose is fabricated.
    completion=(design_policy or {}).get('completion_reference_bounds',[])
    for low in completion:
        if low['minimum'] is None or low['basis']=='RATIO':continue
        for high in completion:
            if high['maximum'] is None or high['basis']=='RATIO':continue
            if (low['nutrient'],low['unit'])!=(high['nutrient'],high['unit']):continue
            maximum_vector=high['maximum']*_den(sources,high['basis'])
            minimum_vector=low['minimum']*_den(sources,low['basis'],True)
            add(maximum_vector-minimum_vector,lo=0,label='COMPLETION_DENSITY_CAPACITY:'+low['nutrient'])
            if low['basis']=='PER_1000_KCAL_ME':
                add(maximum_vector,lo=low['minimum']*target/1000,label='COMPLETION_DAILY_CAPACITY:'+low['nutrient'])
    # Household selection policies, not invented nutrient requirements. Avoid
    # relying on oil, organs or large amounts of fish to force micronutrients.
    for cat,share in [('FISH',.15),('OIL',.10),('EGG',.25),('ORGAN',.05)]:
        share=(design_policy or {}).get('food_energy_share_limits',{}).get(cat,share)
        v=np.array([s['energy_high'] if s['category']==cat else 0 for s in sources])
        add(v,hi=target*share,label='HOUSEHOLD_ENERGY_SHARE:'+cat)
    # Explicit household practicality policy: prevent the cost optimizer from
    # satisfying cat minima with a bowl dominated by vegetables or starch.
    # These are recipe-structure preferences, never therapeutic carbohydrate ULs.
    for cat,share in [('VEGETABLE',.10 if species=='CAT' else .20),('STARCH',.15 if species=='CAT' else .45),('ORGAN',.05)]:
        add(np.array([float(s['category']==cat)-share*float(s['type']=='FOOD') for s in sources]),hi=0,label='HOUSEHOLD_MASS_SHARE:'+cat)
    animal=np.array([(s['values'].get('protein') or 0)/100 if s['category'] in ['MEAT','POULTRY','EGG','FISH','ORGAN'] else 0 for s in sources])
    add(animal-(.8 if species=='CAT' else .6)*_v(sources,'protein'),lo=0,label='HOUSEHOLD_ANIMAL_PROTEIN_PRIORITY')
    for j,s in enumerate(sources):
        for category in s.get('required_food_categories',[]):
            binary=np.array([1. if item['category']==category else 0. for item in sources]);binary[j]=-1.
            add(np.zeros(n),lo=0,label='USER_LABEL_FOOD_CATEGORY:'+category,binary=binary)
    premix=np.array([s['type']=='MULTI_NUTRIENT_PREMIX' for s in sources],float)
    add(np.zeros(n),hi=1,label='NO_PREMIX_STACKING',binary=premix)
    if budget is not None:
        if any(s['unit']!='g' for s in sources):return {'status':'INFEASIBLE','blockers':['PRICE_PER_UNIT_REQUIRED_FOR_NONMASS_SUPPLEMENTS']}
        if not price_map or any(s['id'] not in price_map for s in sources):return {'status':'INFEASIBLE','blockers':['PRICE_DATA_REQUIRED_FOR_HARD_CNY_BUDGET']}
        add(np.array([price_map[s['id']]/1000 for s in sources]),hi=budget,label='USER_PRICE_BUDGET')
    continuity_extra=n if continuity_reference else 0
    # 1.2 alone has continuous hinge variables for its SOFT composition goals.
    # Deficits may remain positive when restrictions or disease direction make
    # a smaller recipe preferable. They never relax nutrition or safety rows.
    structure_categories=(design_policy or {}).get('soft_structure_categories', ['STARCH','VEGETABLE'] if composition and species=='DOG' else [])
    composition_extra=2+len(structure_categories) if composition else 0
    extra=continuity_extra+composition_extra;dimension=2*n+extra
    if extra:rows=[np.r_[row,np.zeros(extra)] for row in rows]
    if continuity_extra:
        for j,s in enumerate(sources):
            u=np.eye(n)[j];desired=continuity_reference.get(s['id'],0.)
            rows.extend([np.r_[u*q,np.zeros(n),-u,np.zeros(composition_extra)],np.r_[-u*q,np.zeros(n),-u,np.zeros(composition_extra)]])
            lower.extend([-np.inf,-np.inf]);upper.extend([desired,-desired]);labels.extend(['CONTINUITY_ABSOLUTE_DEVIATION']*2)
    if composition:
        main_food=np.array([s['type']=='FOOD' and s['category'] not in {'OIL','ORGAN'} for s in sources],float)
        minimum,maximum=composition.get('target_component_count',[3,6] if species=='DOG' else [2,5])
        offset=2*n+continuity_extra
        row=np.zeros(dimension);row[n:2*n]=main_food;row[offset]=1
        rows.append(row);lower.append(minimum);upper.append(np.inf);labels.append('SOFT_MAIN_COMPONENT_DEFICIT')
        row=np.zeros(dimension);row[n:2*n]=main_food;row[offset+1]=-1
        rows.append(row);lower.append(-np.inf);upper.append(maximum);labels.append('SOFT_MAIN_COMPONENT_EXCESS')
        for index,category in enumerate(structure_categories):
            row=np.zeros(dimension);row[n:2*n]=[float(s['category']==category) for s in sources];row[offset+2+index]=1
            rows.append(row);lower.append(1);upper.append(np.inf);labels.append('SOFT_FOOD_CATEGORY:'+category)
    domain=Bounds(np.zeros(dimension),np.r_[np.floor([s['cap']/s['quantum'] for s in sources]),np.ones(n),np.full(extra,np.inf)])
    fixed=[];presolve_retries=[]
    def run(objective):
        constraints=LinearConstraint(np.array(rows+[a[0] for a in fixed]),np.array(lower+[a[1] for a in fixed]),np.array(upper+[a[2] for a in fixed]))
        args=dict(integrality=np.r_[np.ones(2*n),np.zeros(extra)],bounds=domain,constraints=constraints)
        result=milp(objective,**args,options={'mip_rel_gap':0,'time_limit':12})
        if result.status==2 and (design_policy or {}).get('retry_infeasible_without_presolve'):
            # HiGHS presolve can incorrectly reject a later lexicographic
            # stage even though the preceding solution remains feasible.
            # Retry the IDENTICAL rows/objective; never relax a safety bound.
            result=milp(objective,**args,options={'mip_rel_gap':0,'time_limit':12,'presolve':False})
            presolve_retries.append({'stage':len(fixed),'status':int(result.status),'constraints_unchanged':True})
        return result
    objectives=[('SOFT_DISLIKES',np.r_[[s.get('preference_penalty',0)*s['quantum'] for s in sources],np.zeros(n)]),
                ('MINIMUM_NECESSARY_ORGAN_AMOUNT',np.r_[[s['quantum'] if s['category']=='ORGAN' else 0 for s in sources],np.zeros(n)]),
                ('COMMON_FOOD_COST_TIER',np.r_[[s['cost']*s['quantum'] if s['type']=='FOOD' else 0 for s in sources],np.zeros(n)]),
                ('SUPPLEMENT_TYPES',np.r_[np.zeros(n),supp]),('SUPPLEMENT_AMOUNT',np.r_[q*supp,np.zeros(n)]),
                ('FOOD_COUNT',np.r_[np.zeros(n),food]),('STABLE_TIE_BREAK',np.r_[q*np.arange(1,n+1),np.arange(1,n+1)/1000])]
    if extra:objectives=[(name,np.r_[c,np.zeros(extra)]) for name,c in objectives]
    if continuity_extra:
        continuity=np.r_[np.zeros(2*n),[1/max(continuity_reference.get(s['id'],0.),s['quantum']) for s in sources],np.zeros(composition_extra)]
        # Preferences remain soft; all original nutrition/energy/dispensing constraints remain hard.
        objectives.insert(1,('PRESERVE_PREVIOUS_COMPOSITION_WHEN_FEASIBLE',continuity))
    if design_policy:
        # Directional disease objectives never relax a nutrient minimum/maximum.
        for nutrient in reversed(design_policy.get('minimize_nutrients',[])):
            objectives.insert(1,('DISEASE_MINIMIZE_'+nutrient.upper(),np.r_[_v(sources,nutrient)*q,np.zeros(n+extra)]))
        if design_policy.get('prefer_low_known_plant_fiber'):
            # Compare available starches per unit of energy. The lowest-fiber
            # acceptable starch has zero *ranking penalty*, not zero nutrients.
            # This avoids turning a low-fiber direction into a zero-fiber goal.
            starches=[s for s in sources if s['category']=='STARCH']
            baseline=min((s['values']['dietary_fiber']/100/s['energy_low'] for s in starches),default=0)
            penalty=np.array([max(0,s['values']['dietary_fiber']/100-baseline*s['energy_low']) if s['category']=='STARCH' else 0 for s in sources])
            objectives.insert(1,('DISEASE_MINIMIZE_HIGHER_FIBER_STARCH_EXPOSURE',np.r_[penalty*q,np.zeros(n+extra)]))
        if composition and design_policy.get('prefer_moist_food') and not design_policy.get('hydration_via_preparation'):
            position=1+len(design_policy.get('minimize_nutrients',[]))
            objectives.insert(position,('DISEASE_MINIMIZE_NEGATIVE_FOOD_WATER',np.r_[-_v(sources,'water')*q,np.zeros(n+extra)]))
        # Household simplicity is a preference, not a fixed meat/rice ratio.
        position=next(i for i,(name,_) in enumerate(objectives) if name=='COMMON_FOOD_COST_TIER')
        if composition:
            c=np.zeros(dimension);c[2*n+continuity_extra:2*n+continuity_extra+2]=1
            objectives.insert(position,('RECIPE_DIVERSITY_SOFT_TARGET',c));position+=1
            if structure_categories:
                c=np.zeros(dimension);c[2*n+continuity_extra+2:]=1
                objectives.insert(position,('SPECIES_FOOD_STRUCTURE_SOFT_TARGET',c));position+=1
            if species=='CAT':
                c=np.r_[[s['quantum']*s['energy_high'] if s['category'] in {'STARCH','VEGETABLE'} else 0 for s in sources],np.zeros(n+extra)]
                objectives.insert(position,('CAT_AVOID_UNNECESSARY_CARBOHYDRATE',c));position+=1
            objectives.insert(position,('DESIGN_SIMPLE_FOOD_STRUCTURE',np.r_[np.zeros(n),food,np.zeros(extra)]))
        else:objectives.insert(position,('DESIGN_SIMPLE_FOOD_STRUCTURE',np.r_[np.zeros(n),food,np.zeros(extra)]))
    if (design_policy or {}).get('objective_priority')=='SAFETY_NUTRITION_AVAILABILITY_COST_PREPARATION_PREFERENCE':
        # API 1.3 only. Feasibility/nutrient bounds are always hard; preference
        # must not override disease direction, availability or cost.
        preference=next(item for item in objectives if item[0]=='SOFT_DISLIKES')
        objectives=[item for item in objectives if item[0]!='SOFT_DISLIKES']
        cost_position=next(i for i,(name,_) in enumerate(objectives) if name=='COMMON_FOOD_COST_TIER')
        availability=np.r_[[s['quantum'] if s['type']=='FOOD' and s['definition'].get('china_availability') not in {'HIGH','COMMON','EASY','COMMON_USER_PRIORITY'} else 0 for s in sources],np.zeros(n+extra)]
        objectives.insert(cost_position,('CHINA_FOOD_AVAILABILITY',availability))
        if design_policy.get('prefer_compact_food_portion'):
            objectives.insert(cost_position,('BODY_CONDITION_COMPACT_FOOD_PORTION',np.r_[q*food,np.zeros(n+extra)]))
        # Structural variety is a nutrition-design preference, while food-count
        # simplicity comes after availability/cost, before owner dislikes.
        simple=[item for item in objectives if item[0]=='DESIGN_SIMPLE_FOOD_STRUCTURE']
        objectives=[item for item in objectives if item[0]!='DESIGN_SIMPLE_FOOD_STRUCTURE']
        objectives[-1:-1]=simple+[preference]
    if (design_policy or {}).get('objective_priority') == 'SAFETY_NUTRITION_DISEASE_AVAILABILITY_COMPLEXITY_COST_PREFERENCE':
        # Opt-in API 1.5 order. No feasibility row or nutrient bound is changed.
        by_name = dict(objectives)
        availability = np.r_[[s['quantum'] if s['type']=='FOOD' and s['definition'].get('china_availability') not in {'HIGH','COMMON','EASY','COMMON_USER_PRIORITY'} else 0 for s in sources], np.zeros(n+extra)]
        order = [name for name, _ in objectives if name.startswith('DISEASE_MINIMIZE_')]
        order += ['MINIMUM_NECESSARY_ORGAN_AMOUNT', 'CAT_AVOID_UNNECESSARY_CARBOHYDRATE']
        objectives = [(name, by_name[name]) for name in order if name in by_name]
        objectives.append(('CHINA_FOOD_AVAILABILITY', availability))
        for name in ['RECIPE_DIVERSITY_SOFT_TARGET', 'SPECIES_FOOD_STRUCTURE_SOFT_TARGET']:
            if name in by_name: objectives.append((name, by_name[name]))
        objectives.append(('RECIPE_COMPLEXITY_PENALTY', np.r_[np.zeros(n), food, np.zeros(extra)]))
        objectives += [(name, by_name[name]) for name in ['COMMON_FOOD_COST_TIER', 'SUPPLEMENT_TYPES', 'SUPPLEMENT_AMOUNT', 'SOFT_DISLIKES', 'STABLE_TIE_BREAK']]
    if (design_policy or {}).get('diversity_after_cost'):
        # Complexity is distance outside the usual species count range, then
        # a small preference for fewer items within it. Counts remain soft.
        range_objective=next(c for name,c in objectives if name=='RECIPE_DIVERSITY_SOFT_TARGET')
        objectives=[(name,range_objective+.05*c if name=='RECIPE_COMPLEXITY_PENALTY' else c) for name,c in objectives]
        diversity=[item for item in objectives if item[0]=='RECIPE_DIVERSITY_SOFT_TARGET']
        objectives=[item for item in objectives if item[0]!='RECIPE_DIVERSITY_SOFT_TARGET']
        position=next(i for i,(name,_) in enumerate(objectives) if name=='STABLE_TIE_BREAK')
        objectives[position:position]=diversity
    steps=[];r=None
    for name,c in objectives:
        r=run(c)
        if r.status!=0:break
        x=np.r_[np.rint(r.x[:2*n]),r.x[2*n:]];value=float(c@x)
        # Disease direction is a soft optimization preference. A 0.5% objective
        # allowance avoids numerical pinning of decimal nutrient coefficients;
        # all nutritional, safety and dispensing constraints remain exact.
        if design_policy and name.startswith('DISEASE_MINIMIZE_'):
            fixed.append((c,-np.inf,value+max(1e-5,abs(value)*design_policy.get('disease_objective_relative_slack',.005))))
        elif design_policy:
            fixed.append((c,-np.inf,value+max(1e-5,abs(value)*1e-6)))
        else:fixed.append((c,value-1e-7,value+1e-7))
        steps.append({'objective':name,'value':value})
    if r.status!=0:
        # A linear elastic diagnostic identifies unresolved constraints without
        # returning a relaxed meal or presenting diagnostic values as intake.
        a=[];b=[];ll=[]
        for row,lo,hi,label in zip(rows,lower,upper,labels):
            if math.isfinite(lo):a.append(-row);b.append(-lo);ll.append(label)
            if math.isfinite(hi):a.append(row);b.append(hi);ll.append(label)
        A=np.array(a);B=np.array(b);scale=np.maximum(np.max(abs(A),axis=1),np.maximum(abs(B),1e-3));m=len(B)
        diag=linprog(np.r_[np.zeros(dimension),np.ones(m)],A_ub=np.c_[A/scale[:,None],-np.eye(m)],b_ub=B/scale,bounds=list(zip(domain.lb,domain.ub))+[(0,None)]*m,method='highs')
        blockers=[ll[i] for i,v in enumerate(diag.x[dimension:]) if v>1e-7] if diag.success else ['SIMULTANEOUS_CONSTRAINTS_INFEASIBLE']
        return {'status':'INFEASIBLE' if r.status==2 else 'SOLVER_UNRESOLVED','blockers':blockers,
                'diagnostic_scope':'Elastic feasibility witness only, not a minimal conflict set, actual intake, or proof of dietary deficiency. Includes engineering label/rounding/structure limits.',
                'relaxed_recipe_released':False,'solver_message':r.message,**({'objectives':steps,'failed_objective':name} if design_policy else {}),
                **({'presolve_retries':presolve_retries} if presolve_retries else {})}
    grams={s['id']:round(float(x[i]*q[i]),6) for i,s in enumerate(sources) if x[i]>0}
    # Check rounded solution against EVERY exact matrix constraint independently
    # of solver success. This also covers ingredient count, dose and budgets.
    # Python fsum also avoids platform BLAS spurious floating warnings and is
    # an independent numerical path from the solver matrix multiplication.
    observed=[math.fsum(float(a)*float(b) for a,b in zip(row,x)) for row in rows]
    if any(not math.isfinite(v) or v<lo-1e-6 or v>hi+1e-6 for v,lo,hi in zip(observed,lower,upper)):
        return {'status':'AUDIT_FAILED','blockers':['ROUNDED_SOLUTION_CONSTRAINT_FAILURE']}
    ranges={};active_food=[i for i,s in enumerate(sources) if s['type']=='FOOD' and s['id'] in grams]
    for i in active_food:
        g=grams[sources[i]['id']];radius=min(5.,g*.05)
        for row,lo,hi,obs in zip(rows,lower,upper,observed):
            coefficient=abs(float(row[i])/q[i])
            if coefficient<=1e-12:continue
            slack=min(obs-lo if math.isfinite(lo) else math.inf,hi-obs if math.isfinite(hi) else math.inf)
            radius=min(radius,max(0.,slack)/coefficient/max(1,len(active_food)))
        radius=math.floor(max(0.,radius-1e-7)*10)/10
        ranges[sources[i]['id']]={'amount_min_g':round(g-radius,6),'amount_max_g':round(g+radius,6),'scope':'SIMULTANEOUS_REFERENCE_CONSTRAINT_BOX_FIXED_SUPPLEMENTS','recalculation_required_outside_range':True}
    audit=audit_reference(sources,bounds,grams,target)
    return {'status':'REFERENCE_PASS' if audit['pass'] else 'AUDIT_FAILED','grams':grams,'audit':audit,'objectives':steps,'food_amount_ranges':ranges,'rounding_reaudited':True,'constraints_checked':len(rows),'relaxed_recipe_released':False,
            **({'presolve_retries':presolve_retries} if presolve_retries else {})}


def audit_reference(sources,bounds,grams,target):
    active=[(s,grams[s['id']]) for s in sources if grams.get(s['id'],0)>0]
    def total(n,upper=False):return sum((s['upper' if upper else 'values'].get(n) or 0)*g/100 for s,g in active)
    el=sum(s['energy_low']*g for s,g in active);eh=sum(s['energy_high']*g for s,g in active)
    dm=sum(s['dm_low']*g for s,g in active);rows=[];ok=el>=target*(1-TOL)-1e-6 and eh<=target*(1+TOL)+1e-6
    for b in bounds:
        known=total(b.nutrient);upper=total(b.nutrient,True)
        unknown=[s['id'] for s,g in active if s['values'].get(b.nutrient) is None]
        parts=[{'id':s['id'],'source_type':s['type'],'amount':g,'contribution':None if s['values'].get(b.nutrient) is None else s['values'][b.nutrient]*g/100,'source':s['provenance'].get(b.nutrient)} for s,g in active]
        if b.basis=='RATIO':
            den=total('phosphorus');observed=total('calcium')/den;observed_upper=observed
            unknown=[s['id'] for s,g in active if any(s['values'].get(n) is None for n in ['calcium','phosphorus'])];parts=[]
        else:
            dl={'PER_1000_KCAL_ME':el/1000,'PER_100G_DM':dm/100,'PER_KG_DM':dm/1000,'PER_DAY':1}[b.basis]
            dh=eh/1000 if b.basis=='PER_1000_KCAL_ME' else dl
            observed=known/dh;observed_upper=upper/dl
        minimum=b.minimum
        added_sources=[s['id'] for s,g in active if s['type']!='FOOD' and (s['values'].get(b.nutrient) or 0)>0]
        upper_applies=b.maximum is not None and (not _legal_limit(b) or bool(added_sources))
        if minimum is not None and b.dependency:
            d=b.dependency;minimum+=max(0,total(d['nutrient_id'],True)/(el/1000)-d['baseline'])*d['slope']
        floor=minimum*target/1000 if minimum is not None and b.basis=='PER_1000_KCAL_ME' else None
        status='NOT_ESTABLISHED' if minimum is None and b.maximum is None else 'PASS_REFERENCE_SCREEN'
        if minimum is not None and observed<minimum-1e-6 or upper_applies and observed_upper>b.maximum+1e-6 or floor is not None and known<floor-1e-6:status='FAIL';ok=False
        if _legal_limit(b) and not upper_applies and minimum is None:status='LEGAL_LIMIT_NOT_TRIGGERED_NO_DECLARED_ADDITION'
        rows.append({'constraint_id':b.id,'nutrient_id':b.nutrient,'unit':b.unit,'source_basis':b.basis,
                     'screening_basis':b.basis.replace('KCAL_ME','KCAL_FOOD_REFERENCE'),
                     'known_subtotal_daily':known if b.basis!='RATIO' else None,'total_actual_daily':None,
                     'minimum_credit_per_basis':observed,'upper_reference_subtotal_per_basis':observed_upper,
                     'minimum':minimum,'maximum':b.maximum,'daily_minimum_reference':floor,'unquantified_background':unknown,
                     'upper_applies':upper_applies,'declared_additive_sources':added_sources,
                     'upper_applicability_source':'FEDIAF2025 §3.1.3 p11' if _legal_limit(b) else 'NUTRITIONAL_REQUIREMENT',
                     'reference_upper_headroom_fraction':(b.maximum-observed_upper)/b.maximum if upper_applies and b.maximum else None,
                     'minimum_check':('PASS_KNOWN_CONTRIBUTION' if status!='FAIL' else 'FAIL') if minimum is not None else 'NOT_ESTABLISHED',
                     'upper_check':('PASS_REPRESENTATIVE_SUBTOTAL_WITH_UNQUANTIFIED_BACKGROUND' if unknown else 'PASS_REFERENCE_SCREEN') if upper_applies and status!='FAIL' else ('FAIL' if upper_applies else 'NOT_APPLICABLE_OR_NOT_ESTABLISHED'),
                     'source_id':b.source_id,'source_locator':b.source_locator,'status':status,'contributions':parts})
    return {'pass':bool(ok),'rows':rows,'reference_energy_kcal_interval':[el,eh],'target_kcal':target,'food_dry_matter_lower_g':dm,
            'energy_method':'FOOD_ENERGY_REFERENCE_AAHA_USDA','energy_source_id':'V1_AAHA_NUTRITION2021',
            'me_measured':False,'complete_balanced_claim':False,'unknowns_are_zero':False,
            'scope':'Representative-food and label-declared screening; unknown trace background remains unquantified. This is not an upper-confidence-bound or laboratory complete-diet certificate.'}
