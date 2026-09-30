"""Explicit same-product ownership for household execution, not stock proof.

Catalogue tokens identify the archived formulation the user must compare with
their own product. They are neither authenticity certificates nor batch COAs.
No network or purchasing action occurs in this module.
"""
from copy import deepcopy
import hashlib
import json

from .practical_sources import supplement_catalog


LABEL_FIELDS = (
    'supplement_id', 'source_type', 'brand', 'manufacturer', 'product_name', 'country',
    'version', 'source_id', 'source_url', 'archive_sha256', 'amount_unit',
    'declared_per_g', 'amount_per_g', 'nutrient_records', 'additional_label_declarations',
    'chemical_form', 'purity', 'carrier', 'unlisted_nutrients', 'matrix_scope',
    'species_allowed', 'life_stage_allowed', 'v1_use_scope', 'usage_tables',
    'usage_table_source_ids', 'usage_tables_scope', 'upper_total_taurine_policy',
    'usage_rule', 'raw_meat_guide', 'min_usage', 'max_usage', 'precision_requirement',
    'addition_instruction', 'addition_source_id', 'storage', 'daily_solver_eligible',
)


def _label_hash(spec):
    static = {key: spec.get(key) for key in LABEL_FIELDS}
    return hashlib.sha256(json.dumps(static, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def selection_catalog(store):
    """Return reviewable identities and formulation tokens from static specs."""
    result = []
    for spec in sorted(supplement_catalog(store), key=lambda row: row['supplement_id']):
        eligible = bool(spec.get('v1_usable') and spec.get('v1_evidence_status') == 'ACCEPTED_LABEL_REFERENCE'
                        and all(spec.get(k) for k in ('product_name', 'version', 'source_id', 'archive_sha256')))
        result.append({
            **{key: deepcopy(spec.get(key)) for key in (
                'supplement_id', 'product_name', 'brand', 'manufacturer', 'country', 'source_type',
                'version', 'source_id', 'source_url', 'archive_sha256', 'species_allowed',
                'life_stage_allowed', 'amount_unit', 'carrier', 'amount_per_g',
                'nutrient_records', 'additional_label_declarations', 'china_availability',
                'daily_solver_eligible', 'v1_evidence_status')},
            'label_spec_hash': _label_hash(spec), 'eligible_for_selection': eligible,
            'china_stock_verified': False,
            'confirmation_instruction': '仅在您已持有相同产品，并核对名称、物种/阶段、每克/粒/毫升含量、单位和本版标签一致后确认；同品牌其他配方不能代替。',
            'confirmation_scope': 'USER_OWNED_SAME_FORMULATION; NOT_AUTHENTICITY_OR_BATCH_COA_OR_PROFESSIONAL_SIGNOFF',
        })
    return result


product_selection_catalog = selection_catalog
inventory_catalog = selection_catalog


def validate_selection(pet, store):
    """None means no selection submitted; empty set explicitly means no products.

    Only strict true declarations count. A stale or unknown token never falls
    back to unrestricted catalogue use. Species/stage/dose eligibility remains
    independently enforced by the recommendation's source selection.
    """
    if not isinstance(pet, dict):
        raise ValueError('Pet input must be an object')
    if 'user_owned_supplements' not in pet:
        return None
    rows = pet['user_owned_supplements']
    if not isinstance(rows, list):
        raise ValueError('user_owned_supplements must be a list')
    catalog = {s['supplement_id']: s for s in selection_catalog(store)}
    selected = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('OWNED_SUPPLEMENT_SELECTION_MUST_BE_OBJECT')
        sid = row.get('supplement_id')
        if not isinstance(sid, str) or sid not in catalog:
            raise ValueError('UNKNOWN_OWNED_SUPPLEMENT_ID')
        if sid in selected:
            raise ValueError('DUPLICATE_OWNED_SUPPLEMENT_ID:' + sid)
        spec = catalog[sid]
        if not spec['eligible_for_selection']:
            raise ValueError('SUPPLEMENT_NOT_ACCEPTED_FOR_V1:' + sid)
        if row.get('owned') is not True or row.get('label_match_confirmed') is not True:
            raise ValueError('EXPLICIT_OWNERSHIP_AND_LABEL_MATCH_REQUIRED:' + sid)
        if row.get('label_spec_hash') != spec['label_spec_hash']:
            raise ValueError('SUPPLEMENT_LABEL_VERSION_MISMATCH:' + sid)
        selected.add(sid)
    return selected


def execution_readiness(pet, used_supplements, store):
    """Assess a concrete result against explicitly user-owned exact products."""
    selected = validate_selection(pet, store)
    if not isinstance(used_supplements, (list, tuple)):
        raise ValueError('USED_SUPPLEMENTS_MUST_BE_LIST')
    ids = []
    for row in used_supplements:
        sid = row if isinstance(row, str) else row.get('supplement_id') if isinstance(row, dict) else None
        if not isinstance(sid, str) or not sid:
            raise ValueError('USED_SUPPLEMENT_ID_REQUIRED')
        ids.append(sid)
    used = sorted(set(ids))
    catalog = {s['supplement_id']: s for s in selection_catalog(store)}
    ineligible = [sid for sid in used if sid not in catalog or not catalog[sid]['eligible_for_selection']]
    unverified = [sid for sid in used if selected is None or sid not in selected]
    executable = not unverified and not ineligible
    mode = ('NO_SUPPLEMENTS_REQUIRED' if not used else
            'USER_CONFIRMED_SAME_VERSION_PRODUCTS' if executable else 'REFERENCE_ONLY_UNCONFIRMED_SUPPLEMENTS')
    detail = {'supply_mode': mode, 'consumer_executable': executable,
              'selected_ids': sorted(selected) if selected is not None else None,
              'used_ids': used, 'unverified_ids': unverified, 'ineligible_ids': ineligible,
              'china_stock_verified': False,
              'confirmation_scope': 'USER_DECLARED_OWNERSHIP_AND_LABEL_MATCH_ONLY',
              'requires_laboratory': False, 'requires_batch_coa': False,
              'requires_professional_signature': False}
    return {'consumer_executable': executable, 'supply_mode': mode,
            'unverified_ids': unverified, 'china_stock_verified': False,
            'supply_readiness': detail}
