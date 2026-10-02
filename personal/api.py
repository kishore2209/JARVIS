"""Typed local-record APIs behind the application-wide owner boundary."""
from datetime import datetime
from fastapi import APIRouter, Query
from pydantic import ValidationError
from personal.models import MODELS


def build_router(service):
    router = APIRouter(prefix='/api/v1/personal')

    @router.get('/finance-summary')
    def finance_summary(): return {'status':'OK','result':service.finance_summary()}

    @router.get('/daily-plan')
    def daily_plan(): return {'status':'OK','result':service.daily_plan()}

    @router.get('/export')
    def export(): return {'schema_version':1,'records':{kind:service.all(kind) for kind in MODELS}}

    @router.get('/{kind}')
    def records(kind:str, limit:int=Query(100,ge=1,le=500), offset:int=Query(0,ge=0)):
        return {'status':'OK','records':service.list(kind,limit,offset),'limit':limit,'offset':offset}

    @router.post('/{kind}')
    def save(kind:str,payload:dict,expected_version:int|None=Query(None,ge=0)):
        try: result=service.save(kind,payload,expected_version)
        except ValidationError as exc: raise ValueError('Invalid personal record: '+', '.join('.'.join(map(str,e['loc'])) for e in exc.errors())) from None
        return {'status':'OK','record':result}

    @router.delete('/{kind}/{identifier}')
    def delete(kind:str,identifier:str,expected_version:int=Query(...,ge=1)):
        return {'status':'OK',**service.delete(kind,identifier,expected_version)}

    @router.post('/tasks/{identifier}/complete')
    def complete(identifier:str,expected_version:int=Query(...,ge=1)):
        return {'status':'OK','record':service.complete_task(identifier,expected_version)}

    return router
