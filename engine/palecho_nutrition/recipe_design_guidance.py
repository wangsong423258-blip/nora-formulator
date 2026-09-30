"""Explicit manufacturer-guided assurance level; not quantified completeness."""
from dataclasses import replace
COVERED={'calcium','phosphorus','ca_p','potassium','sodium','chloride','magnesium','iron','zinc','copper','manganese','iodine','selenium','vitamin_a','vitamin_d','vitamin_e','b1','b2','b6','b12','niacin','b3','b5','folate','b9','biotin','choline','taurine','vitamin_k'}
def guided_bounds(bounds):
    return [replace(b,minimum=None,dependency={}) if b.nutrient in COVERED else b for b in bounds if b.basis!='RATIO']
