"""NRC 2006 total-dietary-fibre prediction on the FINAL edible mixture.

Calvez et al. 2019, doi:10.1371/journal.pone.0223099, with 2025 correction
reviewed. The correction concerns measured-trial urinary losses, not the
predictive 1.04 / 0.77 factors. USDA carbohydrate-by-difference includes fibre;
it supplies NFE + CF to predicted GE without relabelling TDF as crude fibre.
Ingredient contributions use the mixture's digestibility, so they sum exactly.
"""
import math
from copy import deepcopy

METHOD='NRC_2006_TDF_PREDICTED_GE'
INPUTS=('protein','fat','carbohydrate','fiber','water','ash')
SOURCE='https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0223099'

def metadata(species):
    return dict(method_id=METHOD,species=species,source=SOURCE,source_ids=['NRC2006_TDF_CALVEZ2019','CALVEZ_CORRECTION2025'],
      version='NRC 2006; Calvez 2019; correction checked 2025-03-19',year=2006,
      unit='kcal',basis='FINAL_EDIBLE_MIXTURE_AS_FED',life_stage='MONITORED_ESTIMATE_NOT_LIFE_STAGE_SPECIFIC_DIGESTIBILITY',
      disease='NOT_VALIDATED_FOR_INDIVIDUAL_MALDIGESTION',me_source_type='PREDICTED_NOT_MEASURED',
      formula='GE=5.7*protein_g+9.4*fat_g+4.1*total_carbohydrate_g; TDF_DM=100*TDF_g/dry_matter_g; '+
        ('ME=GE*(96.6-0.95*TDF_DM)/100-1.04*protein_g' if species=='DOG' else 'ME=GE*(95.6-0.89*TDF_DM)/100-0.77*protein_g'),
      applicability='PREDICTIVE_STARTING_ESTIMATE_FOR_COOKED_EDIBLE_MIXTURE',
      evidence_scope='VALIDATED_ON_COMPLETE_DRY_AND_WET_DOG_CAT_FOODS; EXTRAPOLATION_TO_HOMEMADE_QUICK_MEAL',
      assumptions=['Official same-food/state average composition, not measured analysis of this prepared batch.',
        'USDA total carbohydrate includes dietary fibre; recorded carbohydrate is not NFE alone.',
        'Reported analytical averages need not close to 100 g; no normalization, negative NFE clamp or missing-value zero.',
        'Mixture TDF predicts energy digestibility; each ingredient contribution is diet-conditioned, not intrinsic measured ME.',
        'Prediction uncertainty is not the solver rounding tolerance; neither is an animal-specific absorption guarantee.',
        'Fresh-food performance varies; feline homemade, growth and disease-specific digestibility remain unvalidated.'])

def input_issues(n):
    missing=[k for k in INPUTS if n.get(k) is None]
    invalid=[k for k in INPUTS if n.get(k) is not None and
             (type(n[k]) not in (int,float) or not math.isfinite(n[k]) or not 0<=n[k]<=100)]
    if not missing and not invalid:
        if n['water']>=100 or n['fiber']>100-n['water']:invalid.append('DRY_MATTER_OR_TDF')
    return missing,invalid

def predict(species,n,mass_g=100):
    """n: g/100 g final edible mixture, never guaranteed minimum analysis."""
    if species not in {'DOG','CAT'}:raise ValueError('Unsupported species')
    out=metadata(species);missing,invalid=input_issues(n)
    out.update(value=None,missing_inputs=missing,invalid_inputs=invalid,status='UNAVAILABLE')
    if missing or invalid:return out
    if type(mass_g) not in (int,float) or not math.isfinite(mass_g) or mass_g<=0:raise ValueError('Invalid mixture mass')
    ge=5.7*n['protein']+9.4*n['fat']+4.1*n['carbohydrate']
    tdf_dm=n['fiber']*100/(100-n['water'])
    digest=(96.6-.95*tdf_dm) if species=='DOG' else (95.6-.89*tdf_dm)
    urinary=1.04 if species=='DOG' else .77
    me=(ge*digest/100-urinary*n['protein'])*mass_g/100
    if not 0<digest<=100 or not math.isfinite(me) or me<=0:
        out['invalid_inputs']=['NONPHYSICAL_ME_PREDICTION'];return out
    total=sum(n[k] for k in ('protein','fat','carbohydrate','water','ash'))
    out.update(value=me,status='PREDICTED_WITH_APPLICABILITY_LIMITATIONS',gross_energy_kcal=ge*mass_g/100,
      tdf_dry_matter_percent=tdf_dm,predicted_digestibility_percent=digest,urinary_factor=urinary,
      proximate_sum_g_per_100g=total,composition_closure_error_g_per_100g=total-100,
      mass_g=mass_g,analytical_inputs_per_100g={k:n[k] for k in INPUTS})
    return out

def recipe_me(foods,grams):
    mass=math.fsum(grams[f['ingredient_id']] for f in foods)
    composition={k:math.fsum(grams[f['ingredient_id']]*f['nutrients_per_100g'][k] for f in foods)/mass
                 if all(f['nutrients_per_100g'].get(k) is not None for f in foods) else None for k in INPUTS}
    out={}
    for sp in ('DOG','CAT'):
        row=predict(sp,composition,mass);coefficients={};contributions={}
        if row['value'] is not None:
            d=row['predicted_digestibility_percent']/100;u=row['urinary_factor']
            for f in foods:
                n=f['nutrients_per_100g'];iid=f['ingredient_id']
                coefficients[iid]=(5.7*n['protein']+9.4*n['fat']+4.1*n['carbohydrate'])*d-u*n['protein']
                contributions[iid]=coefficients[iid]*grams[iid]/100
            if any(v<=0 or not math.isfinite(v) for v in contributions.values()):
                row.update(value=None,status='UNAVAILABLE',invalid_inputs=['NONPOSITIVE_INGREDIENT_CONTRIBUTION'])
        row.update(coefficients_per_100g=coefficients,ingredient_contributions_kcal=contributions)
        out[sp]=row
    return out

def solve_with_me(foods,m,repo):
    """Bounded coefficient updates; the unchanged MILP keeps all food variables.

    Only a final-mixture constraint audit can accept an iteration. Approximate
    linearization never authorizes publication or a reference-kcal fallback.
    """
    from .ingredient_first_solver import CombinationFeasibilityCheck,constraints_for,evaluate_rows
    from .solver_boundary import checkpoint
    trace=[];last=None
    for iteration in range(1,7):
        checkpoint()
        solution=CombinationFeasibilityCheck(repo).check(foods,m)
        if solution['status']!='SOLVED':return solution,None
        grams=solution['grams']
        # Corrupted output must go to the normal fail-closed final audit.
        if set(grams)!=set(f['ingredient_id'] for f in foods) or any(type(g) not in (float,int) or not math.isfinite(g) or g<=0 for g in grams.values()):
            return {'status':'AUDIT_FAILED','grams':{},'affected_constraint':['ME_INVALID_FINAL_GRAMS']},None
        prior_rows,_,_,_=constraints_for(foods,m,repo)
        if any(r['status']=='FAIL' for r in evaluate_rows(prior_rows,[grams[f['ingredient_id']] for f in foods],repo.policy['numeric_tolerance'])):
            return {'status':'AUDIT_FAILED','grams':{},'affected_constraint':['CORRUPTED_SOLVER_GRAMS']},None
        both=recipe_me(foods,grams);actual=both[m['species']]
        if any(row['value'] is None for row in both.values()):
            return {'status':'AUDIT_FAILED','grams':{},'affected_constraint':['ME_DATA_OR_APPLICABILITY']},None
        m['pet_me_coefficients']=actual['coefficients_per_100g']
        rows,_,_,minima=constraints_for(foods,m,repo)
        audit=evaluate_rows(rows,[grams[f['ingredient_id']] for f in foods],repo.policy['numeric_tolerance'])
        failed=[r['constraint_id'] for r in audit if r['status']=='FAIL']
        trace.append({'iteration':iteration,'whole_recipe_me_kcal':actual['value'],'failed_final_constraints':failed})
        if not failed:
            solution.update(constraints=rows,constraint_audit=audit,meaningful_minima=minima,me_iterations=trace)
            for iid,why in solution.get('why_each_selected_ingredient_amount',{}).items():
                why['energy_contribution_kcal']=actual['ingredient_contributions_kcal'][iid]
                why['meaningful_minimum']=deepcopy(minima[iid])
                why['energy_basis']=METHOD
                j=next(j for j,f in enumerate(foods) if f['ingredient_id']==iid)
                why['binding_constraints']=[row['constraint_id'] for k,row in enumerate(audit)
                  if rows[k]['coefficients'][j]!=0 and any(v is not None and abs(v)<repo.policy['numeric_tolerance']
                    for v in [row['slack_to_minimum'],row['slack_to_maximum']])]
                probe={**grams,iid:100.0}
                probe_me=recipe_me(foods,probe)[m['species']]
                if probe_me['value'] is None:
                    violations=['ME_DATA_OR_APPLICABILITY']
                else:
                    probe_model={**m,'pet_me_coefficients':probe_me['coefficients_per_100g']}
                    probe_rows,_,_,_=constraints_for(foods,probe_model,repo)
                    violations=[r['constraint_id'] for r in evaluate_rows(probe_rows,[probe[f['ingredient_id']] for f in foods],repo.policy['numeric_tolerance']) if r['status']=='FAIL']
                why['counterfactual_100g_other_amounts_fixed']={'violated_constraints':violations,'feasible':not violations,
                    'method':'FINAL_MIXTURE_RECOMPUTED_NO_RESOLVE','whole_recipe_pet_me_kcal':probe_me['value']}
            return solution,both
        last=solution
    return {'status':'SOLVER_UNRESOLVED','grams':{},'affected_constraint':['ME_FINAL_MIXTURE_CONVERGENCE'],
            'me_iterations':trace,'silent_fallback':False},None
