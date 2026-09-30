"""Versioned consumer Quick Meal service, sharing only the immutable journal."""
from copy import deepcopy
import json
import uuid
from .freshfood import FreshFoodService, endpoint
from .freshfood_contract import require
from .practical import digest
from .quick_meal import QuickMealEngine, ENGINE_VERSION, normalize_input
from .practical_preparation import KINDS
from .scientific_ingredients import category
from .scientific_profile_v17 import CATEGORY_MAP
from .quick_meal_schema import validate_quick_model


def quick_service(service):
    if type(service) is FreshFoodQuickMealService:
        return service
    result=FreshFoodQuickMealService.__new__(FreshFoodQuickMealService)
    result.__dict__.update(service.__dict__)
    return result


class FreshFoodQuickMealService(FreshFoodService):
    def versions(self):
        return {'api_version':'1.8','nutrition_db_version':self.store.meta['data_version'],
                'nutrition_rules_version':self.store.meta['data_content_sha256'],'recipe_engine_version':ENGINE_VERSION}

    def _design(self,profile,selection,meal_id,version):
        state=QuickMealEngine(self.store).design(profile,selection)
        result={**self.versions(),**state['result'],'meal_id':meal_id,'version':version}
        validate_quick_model('QuickFreshMealResult',result)
        body={'recipe_id':meal_id,'version':version,'profile':state['profile'],'result':result}
        self._write(body)
        return result

    @endpoint
    def designQuickFreshMeal(self,profile,ingredientSelection=None):
        return self._transaction(lambda:self._design(profile,ingredientSelection,'meal18_'+uuid.uuid4().hex,1))

    @endpoint
    def getQuickFreshMeal(self,meal_id,version=None):
        if version is None:
            return self._load(meal_id)['result']
        require(isinstance(meal_id,str) and type(version) is int and version>0,'MEAL_VERSION_INVALID')
        row=self.db.execute('SELECT body,hash FROM recipe_versions WHERE recipe_id=? AND version=?',(meal_id,version)).fetchone()
        require(row is not None,'MEAL_VERSION_NOT_FOUND')
        body=json.loads(row[0]);require(digest(body)==row[1],'STATE_INTEGRITY_FAILURE')
        require(body['result']['api_version']=='1.8','RECIPE_API_VERSION_MISMATCH')
        validate_quick_model('QuickFreshMealResult',body['result'])
        return body['result']

    @endpoint
    def recalculateQuickFreshMeal(self,meal_id,profile=None,ingredientSelection=None,expected_version=None):
        def run():
            old=self._load(meal_id,expected_version)
            p=deepcopy(old['profile'] if profile is None else profile)
            if ingredientSelection is not None:
                require(isinstance(p,dict),'PROFILE_OBJECT_REQUIRED')
                p.pop('ingredient_selection',None)
            return self._design(p,ingredientSelection,meal_id,old['version']+1)
        return self._transaction(run)

    @endpoint
    def getQuickMealCookingPlan(self,meal_id,version=None):
        result=self.getQuickFreshMeal(meal_id,version)
        if result['status']=='ERROR':return result
        return {**self.versions(),'meal_id':result['meal_id'],'version':result['version'],
                'status':'READY' if result['cooking_plan'] else result['status'],
                'cooking_plan':deepcopy(result['cooking_plan']),'support_result':deepcopy(result['support_result'])}

    @endpoint
    def validateQuickMealProfile(self,profile):
        normalized,_,warnings=normalize_input(profile,None,self.store)
        return {'status':'VALID','profile':normalized,'warnings':warnings,'errors':[]}

    @endpoint
    def getIngredientCatalog(self):
        rows=[]
        for d in self.store.rows('ingredients'):
            if d['ingredient_id'] not in KINDS or d['toxicity_flag']:continue
            group=category(d);public=CATEGORY_MAP.get(group,group)
            rows.append({'ingredient_id':d['ingredient_id'],'display_name':d['name_zh'],'category':public,
                         'user_selectable':group in {'ANIMAL_PROTEIN','ENERGY_SOURCE','FIBER_SOURCE'},
                         'food_state':d['food_state'],'weight_basis':d['weight_basis'],
                         'species':[s for s in ['DOG','CAT'] if d[s.lower()+'_allowed']],
                         'availability':'COMMON_HOUSEHOLD','selection_requires_profile_check':True})
        return {'status':'READY','ingredients':[r for r in rows if r['user_selectable']],
                'supporting_ingredients':[r for r in rows if not r['user_selectable']],
                'selection_contract':{'mode':'CANDIDATE_POOL','all_selected_are_required':False,'equal_split':False,
                    'absent_category':'UNRESTRICTED','empty_category':'DISABLED'},'warnings':[],'errors':[]}

    @endpoint
    def getDiseaseCatalog(self):
        from .freshfood_v17 import daily_service
        result=daily_service(self).getDiseaseCatalog()
        return {**result,**self.versions()}
