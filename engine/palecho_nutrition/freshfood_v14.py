"""FreshFood 1.4: pet profile → daily recipe → immutable cooking snapshot.

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
from .daily_profile_v13 import normalize_daily_profile
from .daily_recipe_v14 import DailyRecipeEngine, ENGINE_VERSION
from .daily_recipe_v14_schema import validate_daily_model


def daily_service(service):
    """Borrow the owning service's connection and transaction lock."""
    if type(service) is FreshFoodDailyService:
        return service
    result = FreshFoodDailyService.__new__(FreshFoodDailyService)
    result.__dict__.update(service.__dict__)
    return result


class FreshFoodDailyService(FreshFoodService):
    api_version = '1.4'
    engine_version = ENGINE_VERSION
    engine_class = DailyRecipeEngine
    profile_link_table = 'daily_profile_links_v14'
    recipe_prefix = 'recipe14_'

    def _normalize_profile(self, profile):
        return normalize_daily_profile(profile, self.store)

    def _validate_profile(self, profile):
        return validate_daily_model('PetNutritionProfile', profile)

    def versions(self):
        return {**super().versions(), 'api_version': self.api_version,
                'recipe_engine_version': self.engine_version}

    def generatePracticalRecipe(self, profile):
        from .freshfood_v11 import FreshFoodV1Adapter
        return FreshFoodV1Adapter(self).generatePracticalRecipe(profile)

    @endpoint
    def getDiseaseCatalog(self):
        from .daily_disease_v13 import DISEASE_CATEGORIES, disease_category
        from .daily_profile_v13 import DISEASE_ID_ALIASES
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
                              'nutrition_action_level': 'GENERAL_DISEASE_ADAPTED_RECIPE'}
                             for row in self.store.rows('diseases')],
                'accepted_id_aliases': {**ALIASES, **DISEASE_ID_ALIASES,
                                       **{key: {'DOG': value[0], 'CAT': value[1]}
                                          for key, value in SPECIES_ALIASES.items()}},
                'warnings': [], 'errors': []}

    @endpoint
    def validateProfile(self, profile):
        self._validate_profile(profile)
        normalized, check, warnings = self._normalize_profile(profile)
        return {'status': check['status'], 'normalized': normalized,
                'warnings': warnings, 'errors': []}

    def _compute(self, body):
        design = self.engine_class(self.store).design(
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
        self._validate_profile(profile)
        normalized, _, _ = self._normalize_profile(profile)

        def op():
            self.db.execute(f'CREATE TABLE IF NOT EXISTS {self.profile_link_table}('
                            'profile_id TEXT PRIMARY KEY, recipe_id TEXT NOT NULL '
                            'UNIQUE REFERENCES recipes(id))')
            row = self.db.execute(f'SELECT recipe_id FROM {self.profile_link_table} WHERE profile_id=?',
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
                body = {'recipe_id': self.recipe_prefix + uuid.uuid4().hex,
                        'version': 1, 'profile_version': 1, 'profile': normalized,
                        'specs': [], 'excluded': [], 'required': []}
            self._compute(body)
            self._write(body)
            if not row:
                self.db.execute(f'INSERT INTO {self.profile_link_table} VALUES (?,?)',
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
        self._validate_profile(profile)

        def op():
            old = self._load(recipe_id, expected_version)
            incoming = deepcopy(profile)
            incoming.setdefault('profile_id', old['profile']['profile_id'])
            normalized, _, _ = self._normalize_profile(incoming)
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
    def setUserSupplementSpec(self, *args, **kwargs):
        require(False, 'ADVANCED_SUPPLEMENT_LAYER_USE_API_1_3', 'supplements')

    @endpoint
    def replaceIngredient(self, request):
        from .daily_recipe_v14_schema import validate_daily_model
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
            self._replacement_profile(new, src, dst)
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

    def _replacement_profile(self, new, src, dst):
        if 'available_ingredient_ids' in new['profile']:
            new['profile']['available_ingredient_ids'] = sorted(
                (set(new['profile']['available_ingredient_ids']) - {src}) | {dst})

    def recalculateDailyRecipe(self, recipe_id, expected_version=None):
        return self.recalculateRecipe(recipe_id, expected_version)

    def _snapshot_details(self, body):
        return {'recipe_goal': 'DAILY_FRESH_FOOD_RECIPE',
                'nutrition_design_target': {'scope':'FOOD_CORE_WITH_NUTRIENT_REMINDERS'},
                'presentation_mode':'PRACTICAL_REMINDER',
                'nutrient_reminders':deepcopy(body['result']['nutrient_reminders'])}

    def _cooking(self, body, snapshot_id, batch_days):
        rebuilt = self.engine_class(self.store).design(
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
        prepared['mass_note']='食物总量仅包含本方案中的食材。'
        prepared['mixing_order']=[x for x in prepared['mixing_order'] if '补剂' not in x]+['按每餐分装，标注制作日期及份量。']
        prepared['storage']['reheating']='需复热时将食物中心加热至74°C，再冷至可安全进食；不给烫食。'
        plan = super()._cooking(legacy, snapshot_id, batch_days, prepared=prepared)
        plan['daily_feeding_plan'].update(deepcopy(body['result']['daily_feeding_plan']))
        plan['daily_feeding_plan']['diet_scope'] = 'DAILY_FRESH_FOOD_RECIPE'
        plan['daily_feeding_plan'].pop('remaining_complete_food_energy_kcal', None)
        plan['daily_feeding_plan'].pop('fresh_food_energy_fraction_max', None)
        plan['disease_lifestyle_notes'] = deepcopy(body['result']['disease_adaptations'])
        plan.pop('supplement_steps',None)
        plan.update(nutrient_reminders=deepcopy(body['result']['nutrient_reminders']),
                    presentation_mode='PRACTICAL_REMINDER',complete_balanced_claim=False,
                    long_term_feeding_note=body['result']['long_term_feeding_note'])
        plan['daily_feeding_plan']['amount_per_meal_basis']='FOOD_ONLY'
        return plan
