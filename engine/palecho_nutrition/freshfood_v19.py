"""Recommended Ingredient-First API; old version adapters remain frozen."""
from copy import deepcopy
import json
import uuid
from .freshfood import FreshFoodService,endpoint
from .freshfood_contract import require
from .practical import digest
from .ingredient_first import IngredientFirstQuickMealEngine,ENGINE_VERSION,READY
from .ingredient_first_repository import IngredientRepository,CATEGORIES
from .ingredient_first_schema import validate_result

def ingredient_first_service(service):
    if type(service) is FreshFoodIngredientFirstService:return service
    result=FreshFoodIngredientFirstService.__new__(FreshFoodIngredientFirstService)
    result.__dict__.update(service.__dict__)
    return result

class FreshFoodIngredientFirstService(FreshFoodService):
    def _transaction(self,operation):
        import threading,time
        from . import solver_boundary as boundary
        from .freshfood_contract import ContractError
        end=time.monotonic()+boundary.REQUEST_SECONDS
        if not self.lock.acquire(timeout=boundary.REQUEST_SECONDS):raise ContractError('RECIPE_SOLVER_TIMEOUT')
        signal=threading.Event();self.calculation_control['active']=signal
        token=boundary.deadline.set(end);cancel=boundary.cancellation.set(signal)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                result=operation();boundary.checkpoint();self.db.execute('COMMIT');return result
            except BaseException:
                self.db.execute('ROLLBACK');raise
        finally:
            self.calculation_control['active']=None
            boundary.deadline.reset(token);boundary.cancellation.reset(cancel);self.lock.release()

    @endpoint
    def cancelQuickFreshMeal(self):
        signal=self.calculation_control['active']
        if signal is not None:signal.set()
        return {'status':'CANCEL_REQUESTED' if signal is not None else 'IDLE','errors':[],'warnings':[]}

    def versions(self):
        return {'api_version':'1.9','nutrition_db_version':self.store.meta['data_version'],
          'nutrition_rules_version':self.store.meta['data_content_sha256'],'recipe_engine_version':ENGINE_VERSION,
          'ingredient_first_data_version':'1.9.1'}

    def _design(self,profile,selection,meal_id,version):
        state=IngredientFirstQuickMealEngine(self.store).design(profile,selection)
        ready=state['result']['status'] in READY
        r={**self.versions(),**state['result'],'meal_id':meal_id if ready or version>1 else None,
           'version':version if ready else version-1,'persisted':ready}
        validate_result(r)
        if ready:self._write({'recipe_id':meal_id,'version':version,'profile':state['profile'],'result':r})
        return r

    @endpoint
    def designQuickFreshMeal(self,profile,ingredientSelection=None):
        return self._transaction(lambda:self._design(profile,ingredientSelection,'meal19_'+uuid.uuid4().hex,1))

    @endpoint
    def getQuickFreshMeal(self,meal_id,version=None):
        require(isinstance(meal_id,str),'MEAL_ID_INVALID')
        if version is None:r=self._load(meal_id)['result']
        else:
            require(type(version) is int and version>0,'MEAL_VERSION_INVALID')
            row=self.db.execute('SELECT body,hash FROM recipe_versions WHERE recipe_id=? AND version=?',(meal_id,version)).fetchone()
            require(row is not None,'MEAL_VERSION_NOT_FOUND')
            body=json.loads(row[0]);require(digest(body)==row[1],'STATE_INTEGRITY_FAILURE')
            r=body['result'];require(r['api_version']=='1.9','RECIPE_API_VERSION_MISMATCH')
        validate_result(r);return r

    @endpoint
    def recalculateQuickFreshMeal(self,meal_id,profile=None,ingredientSelection=None,expected_version=None):
        def run():
            old=self._load(meal_id,expected_version)
            p=deepcopy(old['profile'] if profile is None else profile)
            require(isinstance(p,dict),'PROFILE_OBJECT_REQUIRED')
            # Profile changes retain the actual previous chosen set by default.
            if ingredientSelection is None:p.setdefault('ingredient_selection',old['profile']['ingredient_selection'])
            else:p.pop('ingredient_selection',None)
            return self._design(p,ingredientSelection,meal_id,old['version']+1)
        return self._transaction(run)

    @endpoint
    def getQuickMealCookingPlan(self,meal_id,version=None):
        r=self.getQuickFreshMeal(meal_id,version)
        if r['status']=='ERROR':return r
        return {**self.versions(),'status':'READY','meal_id':meal_id,'version':r['version'],'cooking_plan':r['cooking_plan']}

    @endpoint
    def resolveQuickMealLifeStage(self,profile):
        """Intake preview: deliberately does not build a nutrition model."""
        from .ingredient_first_input import validate_types
        from .life_stage_resolver import LifeStageResolver
        from .freshfood_contract import ContractError
        validate_types(profile, partial=True)
        require(profile.get('species') in {'DOG','CAT'},'INVALID_ENUM','species')
        try: age=LifeStageResolver.profile_age(profile)
        except ValueError as exc: raise ContractError(str(exc),'birth_date' if profile.get('birth_date') else 'age_years') from exc
        return {'status':'VALID','age':age,
          'growth_context_required':LifeStageResolver.growth_context_required(profile['species'],age,profile),
          'validation_scope':'LIFE_STAGE_PREVIEW_ONLY','full_profile_validated':False,'errors':[],'warnings':[]}

    @endpoint
    def validateQuickMealProfile(self,profile):
        p,_,_,warnings,_,_=IngredientFirstQuickMealEngine(self.store).context(profile)
        return {'status':'VALID','profile':p,'warnings':warnings,'errors':[]}

    @endpoint
    def getIngredientCatalog(self,profile):
        engine=IngredientFirstQuickMealEngine(self.store)
        p,_,_,warnings,m,eligibility=engine.context(profile)
        byid={e['ingredient_id']:e for e in eligibility}
        return {'status':'READY','categories':CATEGORIES,
          'catalog_statistics':deepcopy(engine.repo.document['catalog_statistics']),
          'ingredients':[engine.repo.public(f)|{'eligibility_result':byid[i],'user_selectable':byid[i]['selectable']} for i,f in engine.repo.records.items()],
          'disabled_safety_sentinels':[e for e in eligibility if e['ingredient_id'].startswith('TOX_')],
          'deferred_candidates':deepcopy(engine.repo.document['deferred_candidates']),
          'selection_contract':{'mode':'USER_SELECTED_SET','absent_category':'NOT_SELECTED','empty_category':'NOT_SELECTED',
            'all_and_only_selected_are_inputs':True,'equal_split':False,'profile_required':True},
          'warnings':warnings,'errors':[]}

    @endpoint
    def getIngredientEligibility(self,profile):
        _,_,_,warnings,_,eligibility=IngredientFirstQuickMealEngine(self.store).context(profile)
        return {'status':'READY','ingredients':eligibility,'warnings':warnings,'errors':[]}

    @endpoint
    def checkIngredientCombination(self,profile,ingredientSelection):
        def run():
            r=IngredientFirstQuickMealEngine(self.store).design(profile,ingredientSelection)['result']
            return {**self.versions(),**r,'meal_id':None,'version':0,'persisted':False}
        return self._transaction(run)

    @endpoint
    def getScientificSourceRegistry(self):
        repo=IngredientRepository()
        return {'status':'READY','data_hash':repo.data_hash,'registry':deepcopy(repo.registry)}

    @endpoint
    def upgradeQuickFreshMeal(self,meal_id,ingredientSelection):
        # Explicit selected-set submission is required. Old candidate pools are
        # never silently promoted to a decision already made by the user.
        from .freshfood_v18 import quick_service
        old=quick_service(self).getQuickFreshMeal(meal_id)
        require(old['status']!='ERROR','LEGACY_MEAL_NOT_FOUND')
        p=deepcopy(old['pet_summary']);p.pop('ingredient_selection',None)
        return self.designQuickFreshMeal(p,ingredientSelection)

    @endpoint
    def getDiseaseCatalog(self):
        from .freshfood_v17 import daily_service
        r=daily_service(self).getDiseaseCatalog()
        return {**r,**self.versions(),'ingredient_first_disease_rule_note':'Eligibility is profile-aware; not all disease directions are ingredient bans.'}
