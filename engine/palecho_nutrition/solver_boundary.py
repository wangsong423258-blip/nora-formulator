"""Killable, reusable native solver host; no recipes or user-state cache.

The Python parent owns deadlines, independent of HiGHS' native clock. Each
calling thread has an isolated host. Timeout/cancel kills and reaps it before
returning an error. Emscripten uses the browser Worker termination boundary.
"""
import atexit
import contextvars
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
import time
from .freshfood_contract import ContractError

REQUEST_SECONDS = 30.0
SOLVE_SECONDS = 20.0
deadline = contextvars.ContextVar('freshfood_deadline', default=None)
cancellation = contextvars.ContextVar('freshfood_cancellation', default=None)
_local = threading.local()
_hosts = set()
_hosts_lock = threading.Lock()

def checkpoint():
    signal = cancellation.get()
    if signal is not None and signal.is_set(): raise ContractError('RECIPE_SOLVER_CANCELLED')
    end = deadline.get()
    if end is not None and time.monotonic() >= end: raise ContractError('RECIPE_SOLVER_TIMEOUT')

def _stop(host):
    if host.poll() is None: host.kill()
    host.wait(timeout=2)
    host.stdin.close();host.stdout.close()
    with _hosts_lock: _hosts.discard(host)
    if getattr(_local,'host',None) is host: _local.host=None

@atexit.register
def shutdown():
    for host in list(_hosts): _stop(host)

def solve(foods, model, policy):
    checkpoint()
    end = min(deadline.get() or float('inf'), time.monotonic()+SOLVE_SECONDS)
    host = getattr(_local,'host',None)
    if host is None or host.poll() is not None:
        if host is not None: _stop(host)
        host = subprocess.Popen([sys.executable,'-m','palecho_nutrition.solver_host'],
            cwd=str(Path(__file__).resolve().parents[1]), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
            env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
        _local.host=host
        with _hosts_lock: _hosts.add(host)
    try:
        payload=(json.dumps({'foods':foods,'model':model,'policy':policy},allow_nan=False)+'\n').encode()
        os.set_blocking(host.stdin.fileno(),False)
        with selectors.DefaultSelector() as writer:
            writer.register(host.stdin,selectors.EVENT_WRITE)
            while payload:
                checkpoint()
                if time.monotonic()>=end:raise ContractError('RECIPE_SOLVER_TIMEOUT')
                if writer.select(.05):payload=payload[os.write(host.stdin.fileno(),payload):]
        data=b''
        with selectors.DefaultSelector() as selector:
            selector.register(host.stdout,selectors.EVENT_READ)
            while True:
                checkpoint()
                if time.monotonic()>=end: raise ContractError('RECIPE_SOLVER_TIMEOUT')
                if not selector.select(min(.05,end-time.monotonic())): continue
                chunk=os.read(host.stdout.fileno(),65536)
                if not chunk: raise ContractError('RECIPE_SOLVER_FAILED')
                data+=chunk
                if b'\n' in data: break
        response=json.loads(data)
        if 'error' in response: raise ContractError(response['error'])
        checkpoint()
        return response['result']
    except Exception as exc:
        _stop(host)
        if isinstance(exc,ContractError):raise
        raise ContractError('RECIPE_SOLVER_FAILED') from exc
    except BaseException:
        _stop(host)
        raise
