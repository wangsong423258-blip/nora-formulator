"""FreshFood 1.2: pet profile → daily recipe → immutable cooking snapshot.

Only the append-only local journal is shared with earlier API versions. Product
labels belong to a recipe revision, never to the Step 1 nutrition profile.
"""
from copy import deepcopy
import uuid

from .freshfood import FreshFoodService, endpoint
from .freshfood_contract import ContractError, require
from .practical import RECOMMENDED
from .recipe_design import COMPONENTS
from .practical_preparation import prepare_practical
from .user_supplements import validate_spec
from .daily_profile import normalize_daily_profile
from .daily_recipe import DailyRecipeEngine, ENGINE_VERSION
from .daily_recipe_schema import validate_daily_model


def daily_service(service):
    """Borrow the owning service's connection and transaction lock."""
    if isinstance(service, FreshFoodDailyService):
        return service
    result = FreshFoodDailyService.__new__(FreshFoodDailyService)
    result.__dict__.update(service.__dict__)
    return result


class FreshFoodDailyService(FreshFoodService):
    def versions(self):
        return {**super().versions(), 'api_version': '1.2',
                'recipe_engine_version': ENGINE_VERSION}

    def generatePracticalRecipe(self, profile):
        from .freshfood_v11 import FreshFoodV1Adapter
        return FreshFoodV1Adapter(self).generatePracticalRecipe(profile)

    @endpoint
    def getDiseaseCatalog(self):
        from .daily_disease import DISEASE_CATEGORIES, disease_category
        from .daily_profile import DISEASE_ID_ALIASES
        from .practical_disease import CLASSIFICATIONS, SPECIES_ALIASES, ALIASES, DIRECTIONS
        names = ['肾脏 / 泌尿', '肠胃 / 消化', '胰腺', '肝胆', '心脏 / 循环',
                 '糖尿病 / 内分泌', '肥胖 / 代谢', '皮肤 / 过敏', '骨骼 / 关节',
                 '口腔 / 牙齿', '神经系统', '呼吸系统', '感染 / 寄生虫', '其他']
        return {'status': 'READY',
                'categories': [{'category_id': code, 'display_name': name}
                               for code, name in zip(DISEASE_CATEGORIES, names)],
                'diseases': [{'disease_id': row['disease_id'], 'display_name': row['name_zh'],
                              'category': disease_category(row['disease_id'], row['category']),
                              'species': row['species'],
                              'nutrition_action_level': CLASSIFICATIONS[DIRECTIONS.get(
                                  row['disease_id'], (row['nutrition_effect_level'],))[0]]}
                             for row in self.store.rows('diseases')],
                'accepted_id_aliases': {**ALIASES, **DISEASE_ID_ALIASES,
                                       **{key: {'DOG': value[0], 'CAT': value[1]}
                                          for key, value in SPECIES_ALIASES.items()}},
                'warnings': [], 'errors': []}

    @endpoint
    def validateProfile(self, profile):
        validate_daily_model('PetNutritionProfile', profile)
        normalized, check, warnings = normalize_daily_profile(profile, self.store)
        return {'status': check['status'], 'normalized': normalized,
                'warnings': warnings, 'errors': []}

    def _compute(self, body):
        design = DailyRecipeEngine(self.store).design(
            body['profile'], specs=body['specs'],
            excluded=body['excluded'], required=body['required'])
        body.update(profile=design['profile'], specs=design['specs'],
                    raw=design['raw'], nutrition_design_target=design['target'])
        body['result'] = {**design['result'], **self.versions(),
                          'recipe_id': body['recipe_id'],
                          'recipe_version': body['version'],
                          'profile_version': body['profile_version']}
        return body

    @endpoint
    def designDailyFreshFoodRecipe(self, profile):
        validate_daily_model('PetNutritionProfile', profile)
        normalized, _, _ = normalize_daily_profile(profile, self.store)

        def op():
            self.db.execute('CREATE TABLE IF NOT EXISTS daily_profile_links('
                            'profile_id TEXT PRIMARY KEY, recipe_id TEXT NOT NULL '
                            'UNIQUE REFERENCES recipes(id))')
            row = self.db.execute('SELECT recipe_id FROM daily_profile_links WHERE profile_id=?',
                                  (normalized['profile_id'],)).fetchone()
            if row:
                old = self._load(row[0])
                require(old['profile']['species'] == normalized['species'],
                        'PROFILE_SPECIES_IMMUTABLE', 'species')
                if old['profile'] == normalized and all(
                        old['result'][key] == value for key, value in self.versions().items()):
                    return old['result']
                body = self._next(old)
                body['profile'] = normalized
                body['profile_version'] += 1
            else:
                body = {'recipe_id': 'recipe12_' + uuid.uuid4().hex,
                        'version': 1, 'profile_version': 1, 'profile': normalized,
                        'specs': [], 'excluded': [], 'required': []}
            self._compute(body)
            self._write(body)
            if not row:
                self.db.execute('INSERT INTO daily_profile_links VALUES (?,?)',
                                (normalized['profile_id'], body['recipe_id']))
            return body['result']
        return self._transaction(op)

    def _recalc_result(self, old, new):
        return {**self.versions(), 'recipe_id': new['recipe_id'],
                'previous_version': old['version'], 'new_version': new['version'],
                'status': new['result']['status'], 'recipe': new['result'],
                'whole_recipe_recalculated': True,
                'warnings': new['result']['warnings'], 'errors': []}

    @endpoint
    def getRecipe(self, recipe_id, recipe_version=None):
        require(isinstance(recipe_id, str), 'RECIPE_ID_INVALID', 'recipe_id')
        require(recipe_version is None or type(recipe_version) is int and recipe_version > 0,
                'RECIPE_VERSION_INVALID', 'recipe_version')
        return super().getRecipe(recipe_id, recipe_version)

    @endpoint
    def updatePetNutritionProfile(self, recipe_id, profile, expected_version=None):
        # Preserve the ID when a caller sends only the biological profile fields.
        require(isinstance(profile, dict), 'PROFILE_OBJECT_REQUIRED', 'profile')
        validate_daily_model('PetNutritionProfile', profile)

        def op():
            old = self._load(recipe_id, expected_version)
            incoming = deepcopy(profile)
            incoming.setdefault('profile_id', old['profile']['profile_id'])
            normalized, _, _ = normalize_daily_profile(incoming, self.store)
            require(normalized['profile_id'] == old['profile']['profile_id'], 'PROFILE_ID_CONFLICT')
            require(normalized['species'] == old['profile']['species'], 'PROFILE_SPECIES_IMMUTABLE')
            new = self._next(old)
            new['profile'] = normalized
            new['profile_version'] += 1
            self._compute(new)
            self._write(new)
            return self._recalc_result(old, new)
        return self._transaction(op)

    @endpoint
    def setUserSupplementSpec(self, recipe_id, userSupplementSpec, expected_version=None):
        from .daily_recipe_schema import validate_daily_model
        validate_daily_model('UserSupplementSpec', userSupplementSpec)

        def op():
            old = self._load(recipe_id, expected_version)
            result = validate_spec(userSupplementSpec, self.store, old['profile']['species'],
                                   old['raw'].get('life_stage'))
            if result['status'] == 'INVALID':
                raise ContractError('INVALID_PRODUCT_SPEC', 'userSupplementSpec',
                                    '补剂规格不满足计算要求：' + ','.join(result['errors']))
            spec = deepcopy(userSupplementSpec)
            for existing in old['specs']:
                if existing['id'] == spec['id']:
                    require(existing['supplement_type'] == spec['supplement_type'],
                            'SUPPLEMENT_TYPE_CONFLICT', 'userSupplementSpec.supplement_type')
            spec.setdefault('created_at', self.clock())
            spec['updated_at'] = self.clock()
            new = self._next(old)
            # A newly purchased product replaces the previous product of its type.
            new['specs'] = sorted(
                [s for s in new['specs'] if s['supplement_type'] != spec['supplement_type']] + [spec],
                key=lambda s: s['id'])
            self._compute(new)
            self._write(new)
            return self._recalc_result(old, new)
        return self._transaction(op)

    @endpoint
    def replaceIngredient(self, request):
        from .daily_recipe_schema import validate_daily_model
        validate_daily_model('IngredientReplacementRequest', request)

        def op():
            old = self._load(request['recipe_id'], request.get('expected_version'))
            src, dst = request['source_ingredient_id'], request['target_ingredient_id']
            defs = self.store.keyed('ingredients', 'ingredient_id')
            reasons = []
            if old['result']['status'] not in RECOMMENDED:
                reasons.append('BASELINE_NOT_RECOMMENDED')
            if src not in {x['ingredient_id'] for x in old['result']['recipe_components']}:
                reasons.append('SOURCE_INGREDIENT_NOT_IN_RECIPE')
            if dst not in defs:
                reasons.append('UNKNOWN_INGREDIENT_ID')
            elif defs[dst]['toxicity_flag']:
                reasons.append('UNSAFE_INGREDIENT')
            elif src in defs and COMPONENTS.get(defs[src]['food_category']) != COMPONENTS.get(defs[dst]['food_category']):
                reasons.append('COMPONENT_TYPE_CONFLICT')
            if src == dst:
                reasons.append('IDENTICAL_INGREDIENT')
            if request.get('user_requested_amount') is not None:
                reasons.append('FIXED_WEIGHT_REQUIRES_REDESIGN_CONSTRAINT')

            def reject(codes):
                return {**self._recalc_result(old, old), 'status': 'REPLACEMENT_REJECTED',
                        'reason_codes': codes, 'whole_recipe_recalculated': False}
            if reasons:
                return reject(reasons)
            new = self._next(old)
            new['excluded'] = sorted((set(new['excluded']) | {src}) - {dst})
            new['required'] = sorted((set(new['required']) - {src}) | {dst})
            if 'available_ingredient_ids' in new['profile']:
                new['profile']['available_ingredient_ids'] = sorted(
                    (set(new['profile']['available_ingredient_ids']) - {src}) | {dst})
            self._compute(new)
            if new['result']['status'] not in RECOMMENDED:
                return {**reject(['NO_SAFE_REDESIGN']),
                        'attempted_status': new['result']['status'],
                        'diagnostic_reason_codes': new['result']['reason_codes'],
                        'whole_recipe_recalculated': True}
            self._write(new)
            return {**self._recalc_result(old, new), 'status': 'REPLACEMENT_ACCEPTED',
                    'equal_weight_swap': False, 'reason_codes': []}
        return self._transaction(op)

    def _snapshot_details(self, body):
        return {'recipe_goal': 'DAILY_FRESH_FOOD_RECIPE',
                'nutrition_design_target': deepcopy(body['nutrition_design_target'])}

    def _cooking(self, body, snapshot_id, batch_days):
        rebuilt = DailyRecipeEngine(self.store).design(
            body['profile'], specs=body['specs'],
            excluded=body['excluded'], required=body['required'])
        require(rebuilt['raw'].get('recipe_hash') == body['raw'].get('recipe_hash')
                and rebuilt['raw']['recipe_status'] in RECOMMENDED, 'COOKING_PLAN_RECHECK_FAILED')
        raw = body['raw']
        prepared = prepare_practical({**raw, 'confirmed': True}, self.store,
                                     days=batch_days, meals_per_day=raw['meals_per_day'])
        # Compatibility is confined to the existing cooking renderer adapter.
        legacy = deepcopy(body)
        legacy['profile']['feeding_goal'] = 'FULL_DAILY_DIET'
        legacy['result']['safe_general_guidance'] = raw['disease_advice']['daily_care']
        plan = super()._cooking(legacy, snapshot_id, batch_days, prepared=prepared)
        plan['daily_feeding_plan'].update(deepcopy(body['result']['daily_feeding_plan']))
        plan['daily_feeding_plan']['diet_scope'] = 'DAILY_FRESH_FOOD_RECIPE'
        plan['daily_feeding_plan'].pop('remaining_complete_food_energy_kcal', None)
        plan['daily_feeding_plan'].pop('fresh_food_energy_fraction_max', None)
        plan['disease_lifestyle_notes'] = deepcopy(body['result']['disease_adaptations'])
        return plan
