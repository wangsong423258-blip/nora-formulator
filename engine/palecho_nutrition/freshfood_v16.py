"""Additive API 1.6; local transactions and immutable scientific snapshots."""
from copy import deepcopy
from .freshfood_v15 import FreshFoodDailyService as PreviousService
from .freshfood import endpoint
from .freshfood_contract import require
from .practical import RECOMMENDED
from .daily_recipe_v16 import DailyRecipeEngine, ENGINE_VERSION
from .scientific_profile import normalize_profile, normalize_selection
from .scientific_ingredients import catalog, category
from .daily_recipe_v16_schema import validate_daily_model

SCIENTIFIC_FIELDS=['nutrition_design_target','supplement_decision','ingredient_selection_audit','ingredient_rationale','scientific_audit']

def daily_service(service):
    if type(service) is FreshFoodDailyService:return service
    result=FreshFoodDailyService.__new__(FreshFoodDailyService);result.__dict__.update(service.__dict__)
    return result

class FreshFoodDailyService(PreviousService):
    api_version='1.6'
    engine_version=ENGINE_VERSION
    engine_class=DailyRecipeEngine
    profile_link_table='daily_profile_links_v16'
    recipe_prefix='recipe16_'
    def _normalize_selection(self,value):return normalize_selection(value,self.store)
    def _validate_cooking(self,plan):return validate_daily_model('CookingPlan',plan)
    def _normalize_profile(self,profile):return normalize_profile(profile,self.store)
    def _validate_profile(self,profile):return validate_daily_model('PetNutritionProfile',profile)
    def _validate_result(self,result):return validate_daily_model('DailyFreshFoodRecipeV16',result)
    @endpoint
    def getIngredientCatalog(self):
        return {'status':'READY','ingredients':catalog(self.store),'warnings':[],'errors':[],
            'selection_contract':{'mode':'CANDIDATE_POOL','absent_category':'UNRESTRICTED',
                'empty_category':'DISABLED','all_selected_are_required':False,'equal_split':False}}
    @endpoint
    def setIngredientSelection(self,recipe_id,ingredient_selection,expected_version=None):
        selection=self._normalize_selection(ingredient_selection)
        def op():
            old=self._load(recipe_id,expected_version);new=self._next(old)
            new['profile']['ingredient_selection']=selection
            new['profile_version']+=1
            new['required']=[];new['excluded']=[]
            self._compute(new)
            # A constrained pool may be infeasible: retain the previous revision.
            if new['result']['status'] not in RECOMMENDED:
                return {**self._recalc_result(old,old),'status':'SELECTION_REJECTED',
                    'whole_recipe_recalculated':True,'attempted_recipe':new['result'],
                    'reason_codes':new['result']['reason_codes']}
            self._write(new)
            return {**self._recalc_result(old,new),'status':'SELECTION_ACCEPTED'}
        return self._transaction(op)
    def _replacement_profile(self,new,src,dst):
        super()._replacement_profile(new,src,dst)
        definitions=self.store.keyed('ingredients','ingredient_id')
        groups=new['profile']['ingredient_selection']['categories']
        group=category(definitions[src]);destination=category(definitions[dst])
        if group in groups:groups[group]=sorted(set(groups[group])-{src})
        if destination in groups:groups[destination]=sorted(set(groups[destination])|{dst})
    def _snapshot_details(self,body):
        return {**super()._snapshot_details(body),**{k:deepcopy(body['result'][k]) for k in SCIENTIFIC_FIELDS}}
    def _cooking(self,body,snapshot_id,batch_days):
        plan=super()._cooking(body,snapshot_id,batch_days);r=body['result']
        plan.update({k:deepcopy(r[k]) for k in SCIENTIFIC_FIELDS})
        from .recipe_consistency import check_scientific_cooking
        plan['consistency_check']=check_scientific_cooking(r,plan)
        require(plan['consistency_check']['status']=='PASS','COOKING_SCIENTIFIC_SNAPSHOT_MISMATCH')
        # The immutable audit records the original recipe; preparation has its own check.
        plan['scientific_preparation_check']={'status':'PASS','recipe_version':body['version'],
            'batch_days':batch_days,'daily_targets_multiplied_into_doses':False,
            'food_weight_basis':'PER_COMPONENT_DECLARED_STATE_AND_EDIBLE_WEIGHT','supplement_plan_applied':False}
        self._validate_cooking(plan)
        return plan
