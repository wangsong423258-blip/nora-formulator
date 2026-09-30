"""Label-mixture energy envelopes, never measured animal ME concentrations.

The Junior-specific model is versioned in Master. It accounts for disjoint
inorganic anion mass only while the named complete bulk-ingredient declaration
matches. Unknown nutrient contributions remain untouched.
"""
import math


METHOD_ID = 'JUNIOR_DECLARED_INORGANIC_MASS_REFERENCE_V1'


def junior_reference_envelope(spec, policy, elemental_mass):
    """Return a qualified model or None (caller keeps its wider envelope)."""
    if not policy or policy.get('method_id') != METHOD_ID:
        return None
    if spec.get('supplement_id') != policy.get('supplement_id') or spec.get('source_id') != policy.get('label_source_id'):
        return None
    if spec.get('archive_sha256') != policy.get('label_archive_sha256') or spec.get('carrier') != policy.get('required_carrier_declaration'):
        return None
    values = spec.get('amount_per_g', {})
    if any(values.get(n) != v for n, v in policy.get('required_label_amount_per_g', {}).items()):
        return None
    records = {r['nutrient']: r for r in spec.get('nutrient_records', [])}
    if any(records.get(n, {}).get('chemical_form') != form for n, form in policy.get('required_declared_forms', {}).items()):
        return None
    if any('calcium' in (r.get('chemical_form') or '').lower() and n not in {'calcium', 'b5'} for n, r in records.items()):
        return None
    # Reserve the ENTIRE mass of mass-declared vitamins as potential Ca/P
    # bearing material. In particular, calcium pantothenate is not silently
    # counted as calcium carbonate. IU-declared A and D are not invented grams;
    # the applicability declaration requires no additional Ca/P bulk carrier.
    reserve = 0.
    for nutrient in policy['reserve_mass_declared_vitamins']:
        r = records.get(nutrient)
        if r is None:
            r = next((r for r in spec.get('additional_label_declarations', []) if r['nutrient'] == nutrient), None)
        if r is None or r.get('evidence_type') != 'LABEL_DECLARED':
            return None
        scale = {'g': 1., 'mg': .001, 'ug': .000001}.get(r.get('unit'))
        if scale is None or not math.isfinite(r['amount_per_g']) or r['amount_per_g'] < 0:
            return None
        reserve += scale * r['amount_per_g']
    atom = policy['atomic_mass_choices_g_mol']
    ca_hi, p_lo, p_hi, o_lo, c_lo = (atom[k] for k in ['Ca_high', 'P_low', 'P_high', 'O_low', 'C_low'])
    if any(not math.isfinite(v) or v <= 0 for v in [ca_hi, p_lo, p_hi, o_lo, c_lo]):
        return None
    phosphorus_for_phosphate = max(0., values['phosphorus'] - reserve)
    oxygen_in_phosphate = phosphorus_for_phosphate * 4 * o_lo / p_hi
    # Use ALL declared P to reserve the largest nominal DCP Ca amount, even
    # though only the residual P receives phosphate-oxygen credit above.
    calcium_in_dcp_reserve = values['phosphorus'] * ca_hi / p_lo
    calcium_for_carbonate = max(0., values['calcium'] - calcium_in_dcp_reserve - reserve)
    carbonate_oxygen_carbon = calcium_for_carbonate * (c_lo + 3 * o_lo) / ca_hi
    nonenergy = elemental_mass + oxygen_in_phosphate + carbonate_oxygen_carbon
    if not math.isfinite(nonenergy) or not 0 <= elemental_mass <= nonenergy <= 1:
        return None
    high = 9. * (1. - nonenergy)
    return {
        'type': 'DECLARED_INORGANIC_MIXTURE_REFERENCE_ENERGY_ENVELOPE',
        'method_id': METHOD_ID, 'method_version': policy['version'],
        'source_id': spec['source_id'], 'chemical_source_ids': policy['chemical_source_ids'],
        'low_kcal_per_g': 0., 'high_kcal_per_g': high,
        'nominal_label_element_mass_g_per_g': elemental_mass,
        'full_vitamin_mass_reserved_for_possible_ca_p_g_per_g': reserve,
        'phosphorus_allocated_to_phosphate_g_per_g': phosphorus_for_phosphate,
        'additional_phosphate_oxygen_mass_g_per_g': oxygen_in_phosphate,
        'calcium_reserved_for_dcp_g_per_g': calcium_in_dcp_reserve,
        'calcium_allocated_to_carbonate_g_per_g': calcium_for_carbonate,
        'additional_carbonate_carbon_oxygen_mass_g_per_g': carbonate_oxygen_carbon,
        'nominal_nonenergy_mass_g_per_g': nonenergy,
        'equation': policy['equation'],
        'measured_energy': False, 'not_a_batch_guaranteed_energy_bound': True,
        'nutrient_concentrations_modified': False, 'chloride_inferred': False,
        'unknowns_are_zero': False,
        'limitations': policy['limitations'],
    }
