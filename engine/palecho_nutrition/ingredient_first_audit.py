"""Independent final-grams audit. Solver success alone cannot publish a meal."""
from collections import Counter
import math
from .ingredient_first_solver import constraints_for,evaluate_rows
from .ingredient_first_cooking import cooking_consistent

CHECKS=['ENERGY','PROTEIN','FAT','SPECIES','LIFE_STAGE','DISEASE','FOOD_SAFETY',
        'ALL_USER_SELECTED_USED','MEANINGFUL_AMOUNT','CATEGORY_DOMINANCE','PRACTICAL_GRAMS','DATA_PROVENANCE']

def food_facts(foods,grams):
    nutrients=foods[0]['nutrients_per_100g'] if foods else {}
    facts={}
    for n in nutrients:
        missing=[f['ingredient_id'] for f in foods if f['nutrients_per_100g'][n] is None]
        subtotal=math.fsum(grams.get(f['ingredient_id'],0)*f['nutrients_per_100g'][n]/100 for f in foods if f['nutrients_per_100g'][n] is not None)
        facts[n]={'amount':None if missing else subtotal,'known_subtotal':subtotal,'unit':foods[0]['nutrient_units'][n],
          'unquantified_food_ids':missing,'basis':'SELECTED_PORTION_EDIBLE_REFERENCE'}
    ca=facts.get('calcium',{}).get('amount');ph=facts.get('phosphorus',{}).get('amount')
    facts['ca_p_ratio']=ca/ph if ca is not None and ph is not None and ph>0 else None
    return facts

class QuickMealScientificAudit:
    def __init__(self,repository):self.repo=repository

    def run(self,selected,components,m,eligibility,plan):
        checks={k:'PASS' for k in CHECKS};issues=[];p=self.repo.policy
        expected=Counter(selected);actual=Counter(c['ingredient_id'] for c in components)
        missing=sorted(set(selected)-set(actual));added=sorted(set(actual)-set(selected))
        if actual!=expected:
            checks['ALL_USER_SELECTED_USED']='FAIL';issues.append({'code':'USER_SELECTED_INGREDIENT_MISSING' if missing else 'UNSELECTED_INGREDIENT_ADDED','missing':missing,'unexpected':added})
        valid_amounts=all(type(c.get('amount_g')) in (int,float) and math.isfinite(c['amount_g']) and c['amount_g']>0 and c['amount_g']%p['quantum_g']==0 for c in components)
        if not valid_amounts:checks['PRACTICAL_GRAMS']='FAIL';issues.append({'code':'PRACTICAL_GRAMS_INVALID'})
        byid={r['ingredient_id']:r for r in eligibility}
        known=all(c['ingredient_id'] in self.repo.records for c in components)
        foods=[self.repo.records[i] for i in sorted(selected) if i in self.repo.records]
        if not known or not foods:
            checks['DATA_PROVENANCE']='FAIL';checks['FOOD_SAFETY']='FAIL'
        for c in components:
            f=self.repo.records.get(c['ingredient_id'])
            if not f:continue
            if self.repo.provenance_errors(f):checks['DATA_PROVENANCE']='FAIL'
            if f['toxicity'] or byid.get(c['ingredient_id'],{}).get('eligibility')=='DISABLED':checks['FOOD_SAFETY']='FAIL'
            if m['species'] not in f['species_allowed']:checks['SPECIES']='FAIL'
            if any(c.get(k)!=f[k] for k in ['food_state','weight_basis','category','record_sha256']):checks['DATA_PROVENANCE']='FAIL'
        if 'UNWEANED' in m['life_stage'] or m['growth'] and m['energy']['modifiers']['body_condition_and_trend']<1:checks['LIFE_STAGE']='FAIL'
        numerical=[];dominance=[]
        if known and foods and valid_amounts:
            grams={c['ingredient_id']:c['amount_g'] for c in components}
            rows,_,_,minima=constraints_for(foods,m,self.repo)
            numerical=evaluate_rows(rows,[grams.get(f['ingredient_id'],0) for f in foods],p['numeric_tolerance'])
            for row in numerical:
                name=row['constraint_id'];which='CATEGORY_DOMINANCE'
                if name=='ENERGY':which='ENERGY'
                elif name.startswith('PROTEIN'):which='PROTEIN'
                elif name.startswith('FAT') and name!='FAT_DOMINANCE':which='FAT'
                elif name.startswith('DISEASE'):which='DISEASE'
                elif name.startswith('ANIMAL'):which='SPECIES'
                elif name.startswith('MEANINGFUL'):which='MEANINGFUL_AMOUNT'
                if row['status']=='FAIL':
                    checks[which]='FAIL';issues.append({'code':name,'rule_id':row['rule_id'],'classification':row['classification']})
                if which=='CATEGORY_DOMINANCE':dominance.append(row)
            mass=sum(grams.values())
            if len(foods)>1 and any(g/mass>p['single_mass_warn'] for g in grams.values()) and checks['CATEGORY_DOMINANCE']!='FAIL':
                checks['CATEGORY_DOMINANCE']='WARN';issues.append({'code':'SINGLE_INGREDIENT_DOMINANCE','classification':'ENGINEERING_LIMIT','rule_id':'ENG_SINGLE_MASS_WARN'})
            # A reference-energy band is auditable; actual pet ME is unknown.
            if checks['ENERGY']=='PASS' and not m.get('pet_me_coefficients'):checks['ENERGY']='WARN';issues.append({'code':'PET_ME_UNQUANTIFIED_REFERENCE_ENERGY_ONLY'})
            if m['diseases'] and checks['DISEASE']=='PASS':checks['DISEASE']='WARN'
        if not cooking_consistent(components,plan,m):
            checks['PRACTICAL_GRAMS']='FAIL';issues.append({'code':'COOKING_PLAN_INCONSISTENT'})
        categories={
          'ENERGY_SOURCE_DOMINANCE':['CATEGORY_MASS_MAX:ENERGY_SOURCE','CATEGORY_ENERGY_MAX:ENERGY_SOURCE'],
          'FAT_DOMINANCE':['FAT_DOMINANCE','CATEGORY_ENERGY_MAX:FAT_OIL'],
          'ORGAN_EXCESS':['CATEGORY_MASS_MAX:ORGAN','CATEGORY_ENERGY_MAX:ORGAN'],
          'SINGLE_INGREDIENT_DOMINANCE':['SINGLE_CORE_DOMINANCE:'],
          'EXCESSIVE_RECIPE_MASS':['EXCESSIVE_RECIPE_MASS'],
          'IMPLAUSIBLE_RECIPE_STRUCTURE':['CATEGORY_MASS_MAX:','CATEGORY_ENERGY_MAX:','ANIMAL_PROTEIN_CORE'],
        }
        category_checks={code:('FAIL' if any(row['status']=='FAIL' and any(row['constraint_id'].startswith(k) for k in prefixes) for row in numerical)
          else 'WARN' if any(i['code']==code for i in issues) else 'PASS') for code,prefixes in categories.items()}
        return {'checks':checks,'status':'FAIL' if 'FAIL' in checks.values() else 'WARN' if 'WARN' in checks.values() else 'PASS',
          'issues':issues,'constraint_audit':numerical,'category_dominance_audit':dominance,
          'category_dominance_checks':category_checks,
          'scope':'QUICK_MEAL_NOT_LONG_TERM_COMPLETE_DIET','complete_balanced_claim':False,
          'selected_set_verified':actual==expected,'all_failed_constraints_block_ordinary_recipe':True}
