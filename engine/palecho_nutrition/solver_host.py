"""Private pipe protocol. Only computes grams; never accesses the state DB."""
import json
import sys
from types import SimpleNamespace
from .ingredient_first_solver import ScientificRecipeSolver
from .freshfood_contract import ContractError

def main():
    for line in sys.stdin:
        try:
            request=json.loads(line)
            result=ScientificRecipeSolver(SimpleNamespace(policy=request['policy']))._solve_inline(request['foods'],request['model'])
            response={'result':result}
        except ContractError as exc: response={'error':exc.detail['code']}
        except Exception: response={'error':'RECIPE_SOLVER_FAILED'}
        print(json.dumps(response,allow_nan=False),flush=True)

if __name__=='__main__': main()
