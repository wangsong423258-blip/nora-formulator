"""Additive API 1.5, sharing immutable version/transaction machinery with 1.4."""
from copy import deepcopy
from .freshfood_v14 import FreshFoodDailyService as ReminderService
from .daily_recipe_v15 import DailyRecipeEngine, ENGINE_VERSION
from .recipe_consistency import check_cooking
from .freshfood_contract import require


def daily_service(service):
    if type(service) is FreshFoodDailyService:return service
    result=FreshFoodDailyService.__new__(FreshFoodDailyService)
    result.__dict__.update(service.__dict__)
    return result


class FreshFoodDailyService(ReminderService):
    api_version='1.5'
    engine_version=ENGINE_VERSION
    engine_class=DailyRecipeEngine
    profile_link_table='daily_profile_links_v15'
    recipe_prefix='recipe15_'

    def _compute(self,body):
        super()._compute(body)
        self._validate_result(body['result'])
        return body

    def _validate_result(self, result):
        from .daily_recipe_v15_schema import validate_daily_model
        validate_daily_model('DailyFreshFoodRecipeV15', result)

    def _snapshot_details(self,body):
        r=body['result']
        return {**super()._snapshot_details(body),
                'presentation_mode':r['presentation_mode'],
                'nutrition_design_target':{'scope':r['nutrition_scope']},
                'supplement_recommendations':deepcopy(r['supplement_recommendations']),
                'nutrient_matrix':deepcopy(r['nutrient_matrix']),
                'energy_audit':deepcopy(r['energy_audit']),
                'consistency_check':deepcopy(r['consistency_check'])}

    def _cooking(self,body,snapshot_id,batch_days):
        plan=super()._cooking(body,snapshot_id,batch_days)
        r=body['result']
        definitions=self.store.keyed('ingredients','ingredient_id')
        oils=[c['ingredient_id'] for c in r['recipe_components'] if definitions[c['ingredient_id']]['food_category']=='OIL']
        foods=[c['ingredient_id'] for c in r['recipe_components'] if c['ingredient_id'] not in oils]
        mixing=[{'step':1,'ingredient_ids':foods,
                 'instruction':'各食材按指定方式熟制并按方案的可食熟重称量，处理成适合当前咀嚼能力的形态，在清洁容器内混合均匀；不把生重或未核算肉汤当作熟食克数。'}]
        if oils:mixing.append({'step':2,'ingredient_ids':oils,'instruction':'按方案克数另行称取列出的食用油，拌入已称好的熟食；不额外添加油脂。'})
        for note in r['daily_feeding_plan']['hydration_notes']:
            mixing.append({'step':len(mixing)+1,'ingredient_ids':[],'instruction':note})
        feeding=r['daily_feeding_plan']
        mixing.append({'step':len(mixing)+1,'ingredient_ids':[],
            'instruction':f"混匀后按每日 {feeding['daily_total_food_g']:g}g 食物分装，每天 {feeding['meals_per_day']} 餐，每餐约 {feeding['food_g_per_meal']:g}g；标注日期和份量，另加清水不计入食材克重。"})
        plan.update(presentation_mode=r['presentation_mode'],
                    mixing_steps=mixing,
                    supplement_recommendations=deepcopy(r['supplement_recommendations']),
                    nutrient_matrix=deepcopy(r['nutrient_matrix']),energy_audit=deepcopy(r['energy_audit']),
                    nutrition_supplement_notes=['目标仅表示营养成分参考量；未绑定和核验实际产品，不换算克数、毫升或粒数。']+
                    [x['title']+'：目标有效成分见营养补充建议；'+x['user_message'] for x in r['supplement_recommendations']])
        plan['consistency_check']=check_cooking(r,plan)
        require(plan['consistency_check']['status']=='PASS','COOKING_PLAN_CONSISTENCY_FAILED')
        return plan
