"""Additive API 1.7, immutable recipes and verified preparation snapshots."""
from copy import deepcopy
from .freshfood_v16 import FreshFoodDailyService as PreviousService
from .freshfood import endpoint
from .daily_recipe_v17 import DailyRecipeEngine,ENGINE_VERSION
from .scientific_profile_v17 import normalize_profile,normalize_selection,CATEGORY_MAP,PUBLIC_CATEGORIES
from .scientific_ingredients import catalog
from .daily_recipe_v17_schema import validate_daily_model
from .recipe_consistency import check_scientific_cooking
from .freshfood_contract import require

def daily_service(service):
    if type(service) is FreshFoodDailyService:return service
    result=FreshFoodDailyService.__new__(FreshFoodDailyService);result.__dict__.update(service.__dict__);return result

class FreshFoodDailyService(PreviousService):
    api_version='1.7';engine_version=ENGINE_VERSION;engine_class=DailyRecipeEngine
    profile_link_table='daily_profile_links_v17';recipe_prefix='recipe17_'
    def _normalize_profile(self,p):return normalize_profile(p,self.store)
    def _normalize_selection(self,p):return normalize_selection(p,self.store)
    def _validate_profile(self,p):return validate_daily_model('PetNutritionProfile',p)
    def _validate_result(self,r):return validate_daily_model('DailyFreshFoodRecipeV17',r)
    def _validate_cooking(self,p):return validate_daily_model('CookingPlan',p)
    @endpoint
    def getIngredientCatalog(self):
        definitions=self.store.keyed('ingredients','ingredient_id');rows=[]
        for row in catalog(self.store):
            if row['ingredient_id'] not in definitions:continue
            row['category']=CATEGORY_MAP.get(row['category'],row['category'] or 'OTHER')
            row['user_selectable']=row['category'] in PUBLIC_CATEGORIES
            # Legacy density field was generated through the feline vitamin-A
            # conversion. Identify that basis rather than present it as universal.
            row['nutrient_density']['species_basis']='CAT_REFERENCE_CONVERSION'
            rows.append(row)
        return dict(status='READY',ingredients=[r for r in rows if r['user_selectable']],
            supporting_ingredients=[r for r in rows if not r['user_selectable']],
            categories=['ANIMAL_PROTEIN','SECONDARY_ANIMAL_FOOD','ENERGY_SOURCE','FIBER_SOURCE','ORGAN','OIL','OTHER'],
            selection_contract={'mode':'CANDIDATE_POOL','selectable_categories':sorted(PUBLIC_CATEGORIES),'absent_category':'UNRESTRICTED','empty_category':'DISABLED','all_selected_are_required':False,'equal_split':False},warnings=[],errors=[])
    def _snapshot_details(self,body):
        return {**super()._snapshot_details(body),'complexity_review':deepcopy(body['result']['complexity_review'])}
    def _cooking(self,body,snapshot_id,batch_days):
        plan=super()._cooking(body,snapshot_id,batch_days)
        r=body['result']
        feeding=r['daily_feeding_plan']
        portions='、'.join(f'{g:g}g' for g in feeding['meal_portions_g'])
        plan['mixing_steps'][-1]['instruction']=f"混匀后按每日 {feeding['daily_total_food_g']:g}g 分装，每天 {feeding['meals_per_day']} 餐，各餐为 {portions}。标注日期，另加清水不计入食材克重。"
        plan['complexity_review']=deepcopy(r['complexity_review'])
        plan['nutrition_supplement_notes']=['未绑定产品，不输出补剂粒数、克数或毫升数。']+[x['title']+'：'+x['user_message'] for x in r['supplement_recommendations']]
        plan['scientific_preparation_check']['meal_portions_g']=deepcopy(r['daily_feeding_plan']['meal_portions_g'])
        plan['consistency_check']=check_scientific_cooking(r,plan)
        require(plan['consistency_check']['status']=='PASS','COOKING_SCIENTIFIC_SNAPSHOT_MISMATCH')
        plan['scientific_audit']['required_checks']['COOKING_VALID']=plan['consistency_check']['status']
        for row in plan['scientific_audit']['checks']:
            if row['check']=='COOKING_VALID':row['status']=plan['consistency_check']['status']
        validate_daily_model('CookingPlan',plan)
        return plan
