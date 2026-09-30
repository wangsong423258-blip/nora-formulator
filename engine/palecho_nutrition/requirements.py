"""Independent completeness contract, FEDIAF 2025 Tables III-3/4 and footnotes.

This registry is deliberately independent of editable spreadsheet rows. It lists
identities and applicability, never substitutes an invented nutrient allowance.
"""
import json
COMMON=frozenset('protein arginine histidine isoleucine leucine lysine methionine methionine_cystine phenylalanine phenylalanine_tyrosine threonine tryptophan valine fat linoleic calcium phosphorus ca_p_ratio potassium sodium chloride magnesium iron copper zinc manganese selenium iodine vitamin_a vitamin_d vitamin_e b1 b2 b3 b5 b6 b9 b12 choline'.split())
REQUIRED_NUTRIENTS_BY_SPECIES={
    'DOG':COMMON|{'me_dog'},
    'CAT':COMMON|{'me_cat','taurine','arachidonic','biotin'},
}
GROWTH_EXTRA={'DOG':frozenset(['arachidonic','alpha_linolenic','epa_dha']),
              'CAT':frozenset(['alpha_linolenic','epa_dha'])}
CONDITIONAL_NUTRIENTS_BY_SPECIES={'DOG':frozenset(['taurine','biotin','vitamin_k','vitamin_e']),
                                 'CAT':frozenset(['vitamin_k','vitamin_e','b6'])}
EXPECTED_PROFILES=frozenset(['DOG_ADULT_95','DOG_ADULT_110','DOG_GROWTH_EARLY','DOG_GROWTH_LATE_SMALL',
                            'DOG_GROWTH_LATE_LARGE_U6','DOG_GROWTH_LATE_LARGE_O6','CAT_GROWTH','CAT_ADULT_75','CAT_ADULT_100'])

def required_nutrients(species,profile):
    return REQUIRED_NUTRIENTS_BY_SPECIES[species] | (GROWTH_EXTRA[species] if 'GROWTH' in profile else frozenset())

def profile_coverage_issues(rows,profile):
    species=profile.split('_')[0]
    if profile not in EXPECTED_PROFILES:return ['PROFILE_NOT_SUPPORTED:'+profile]
    issues=[]
    for n in sorted(required_nutrients(species,profile)-{'me_dog','me_cat'}):
        candidates=[r for r in rows if r['profile_id']==profile and r['nutrient_id']==n and r['enforced'] and r['basis']==('RATIO' if n=='ca_p_ratio' else 'PER_1000_KCAL_ME') and json.loads(r['condition_json'])=={}]
        if not any(r['minimum'] is not None and r['minimum_status']=='ESTABLISHED' for r in candidates):issues.append('REQUIRED_MINIMUM_MISSING:'+profile+':'+n)
    return issues
