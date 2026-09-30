import argparse,json,sys,sqlite3
from pathlib import Path
from .store import Store
from .profile import assess
from .runtime import solve,substitute,audit_recipe,nutrient_food_map
from .preparation import prepare

def strict_json(path):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('Duplicate JSON key '+k)
            out[k]=v
        return out
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON '+x)))

def main():
    ap=argparse.ArgumentParser(description='PalEcho 完全离线营养规则参考实现（不含前端）')
    ap.add_argument('--db',type=Path,default=Path(__file__).parent/'data/nutrition-json',help='plain JSON data directory (or legacy SQLite database)')
    ap.add_argument('--out',type=Path)
    sub=ap.add_subparsers(dest='command',required=True)
    for name in ['assess','solve','substitute','audit','prepare','plan-adult']:
        p=sub.add_parser(name);p.add_argument('--pet',type=Path,required=True)
        if name=='substitute':p.add_argument('--old',required=True);p.add_argument('--new',required=True)
        if name in ['audit','prepare']:p.add_argument('--recipe',type=Path,required=True,help='JSON object mapping ingredient IDs to daily consumed grams')
        if name=='prepare':p.add_argument('--days',type=int,required=True);p.add_argument('--meals',type=int,required=True)
    sub.add_parser('catalog');sub.add_parser('status')
    for name in ['recommend','replace-practical']:
        p=sub.add_parser(name);p.add_argument('--pet',type=Path,required=True)
        if name=='replace-practical':
            p.add_argument('--old',required=True);p.add_argument('--new',required=True)
            p.add_argument('--baseline',type=Path)
    p=sub.add_parser('prepare-practical');p.add_argument('--recommendation',type=Path,required=True)
    p.add_argument('--days',type=int,default=3);p.add_argument('--meals',type=int)
    sub.add_parser('practical-status')
    p=sub.add_parser('validate-supplement');p.add_argument('--spec',type=Path,required=True);p.add_argument('--species',choices=['DOG','CAT'])
    p=sub.add_parser('freshfood');p.add_argument('--state',type=Path,required=True);p.add_argument('--request',type=Path,required=True)
    args=ap.parse_args()
    try:
        with Store(args.db) as store:
            pet=strict_json(args.pet) if hasattr(args,'pet') else None
            if args.command=='freshfood':
                from .freshfood import FreshFoodService
                from .freshfood_dispatch import dispatch
                with FreshFoodService(store,args.state) as service:result=dispatch(service,strict_json(args.request))
            elif args.command=='validate-supplement':
                from .user_supplements import validate_spec
                result=validate_spec(strict_json(args.spec),store,args.species)
            elif args.command=='recommend':
                from .practical import recommend
                result=recommend(pet,store)
            elif args.command=='replace-practical':
                from .practical import replace_practical
                result=replace_practical(pet,args.old,args.new,store,strict_json(args.baseline) if args.baseline else None)
            elif args.command=='prepare-practical':
                from .practical import prepare_recommendation
                result=prepare_recommendation(strict_json(args.recommendation),store,days=args.days,meals_per_day=args.meals)
            elif args.command=='practical-status':
                from .practical import practical_status
                result=practical_status(store)
            elif args.command=='plan-adult':
                from .adult_strategy import plan_adult
                result=plan_adult(pet,store)
            elif args.command=='assess':result=assess(pet,store)
            elif args.command=='solve':result=solve(pet,store)
            elif args.command=='substitute':result=substitute(pet,args.old,args.new,store)
            elif args.command=='audit':result=audit_recipe(pet,strict_json(args.recipe),store)
            elif args.command=='prepare':result=prepare(pet,strict_json(args.recipe),store,days=args.days,meals_per_day=args.meals)
            elif args.command=='catalog':result=nutrient_food_map(store)
            else:result=store.meta
        output=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
        if args.out:args.out.write_text(output)
        else:print(output,end='')
    except (ValueError,KeyError,OSError) as e:
        if args.command=='freshfood':
            from .freshfood_contract import error,API_VERSION,ENGINE_VERSION
            meta=store.meta if 'store' in locals() else {}
            print(json.dumps({'api_version':API_VERSION,'nutrition_db_version':meta.get('data_version','UNAVAILABLE'),'nutrition_rules_version':meta.get('data_content_sha256','UNAVAILABLE'),'recipe_engine_version':ENGINE_VERSION,'status':'ERROR','errors':[error('REQUEST_IO_ERROR' if isinstance(e,OSError) else 'REQUEST_INVALID',field='request',message='请求未能读取或解析，请核对JSON与本地数据路径。')],'warnings':[]},ensure_ascii=False));sys.exit(2)
        print(json.dumps({'recipe_status':'INVALID_INPUT','reasons':[str(e)]},ensure_ascii=False));sys.exit(2)
    except sqlite3.Error as e:
        if args.command=='freshfood':
            from .freshfood_contract import error,API_VERSION,ENGINE_VERSION
            meta=store.meta if 'store' in locals() else {}
            print(json.dumps({'api_version':API_VERSION,'nutrition_db_version':meta.get('data_version','UNAVAILABLE'),'nutrition_rules_version':meta.get('data_content_sha256','UNAVAILABLE'),'recipe_engine_version':ENGINE_VERSION,'status':'ERROR','errors':[error('STATE_STORAGE_ERROR',action='CHECK_LOCAL_STATE_DATABASE')],'warnings':[]},ensure_ascii=False));sys.exit(2)
        print(json.dumps({'recipe_status':'DATASET_ERROR','reasons':[str(e)]},ensure_ascii=False));sys.exit(2)

if __name__=='__main__':main()
