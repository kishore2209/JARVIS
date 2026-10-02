"""Single-owner HTTP gateway for knowledge and durable read-only tasks."""
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from market.review import ReviewNote


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=100000)
    source: str = Field(min_length=1, max_length=500)
    identifier: str | None = None
    expected_version: int | None = None
    expires_at: str | None = None
    parent_ids: list[str] = Field(default_factory=list, max_length=20)


class RetrievalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10, strict=True)
    max_chars: int = Field(default=6000, ge=500, le=12000, strict=True)


class TaskInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: str
    payload: dict
    idempotency_key: str = Field(min_length=1, max_length=128)
    seconds: int = Field(default=120, ge=1, le=300, strict=True)
    tool_budget: int = Field(default=100, ge=1, le=100, strict=True)


def build_control_router(runtime):
    router = APIRouter(prefix='/api/v1')

    @router.get('/paper/review')
    def review(period: str = 'daily', as_of: str | None = None):
        return {'status': 'OK', 'result': runtime.reviews.report(period, datetime.fromisoformat(as_of) if as_of else None)}

    @router.post('/paper/review-notes')
    def review_note(body: ReviewNote, expected_version: int = 0):
        return {'status': 'OK', 'note': runtime.reviews.annotate(body.model_dump(), expected_version)}

    @router.get('/paper/review-notes/{position_id}')
    def review_history(position_id: str):
        return {'status': 'OK', 'history': runtime.reviews.history(position_id)}

    @router.get('/knowledge')
    def documents():
        return {'status': 'OK', 'documents': runtime.knowledge.list('owner')}

    @router.post('/knowledge')
    def ingest(body: DocumentInput):
        return {'status': 'OK', 'document': runtime.knowledge.ingest(**body.model_dump(), readers=['owner'])}

    @router.post('/knowledge/search')
    def search(body: RetrievalInput):
        return {'status': 'OK', 'result': runtime.knowledge.retrieve(**body.model_dump(), principal='owner')}

    @router.post('/knowledge/revoke')
    def revoke(body: dict):
        if set(body) != {'source'}:
            raise ValueError('Only source is accepted')
        runtime.knowledge.revoke(body['source'])
        return {'status': 'OK'}

    @router.delete('/knowledge/{identifier}')
    def delete(identifier: str, expected_version: int):
        runtime.knowledge.delete(identifier, expected_version)
        return {'status': 'OK'}

    @router.post('/tasks', status_code=202)
    def submit(body: TaskInput, request: Request):
        if runtime.store is None:
            raise ValueError('Durable tasks require JARVIS_DB_ENABLED=true')
        task = runtime.tasks.submit(**body.model_dump(), correlation_id=request.state.correlation_id)
        return {'status': 'ACCEPTED', 'task': runtime.tasks.public(task)}

    @router.get('/tasks')
    def task_list():
        return {'status': 'OK', 'tasks': runtime.tasks.list()}

    @router.get('/tasks/{identifier}')
    def task_get(identifier: str):
        return {'status': 'OK', 'task': runtime.tasks.public(runtime.tasks.get(identifier))}

    @router.post('/tasks/{identifier}/cancel')
    def task_cancel(identifier: str):
        return {'status': 'OK', 'task': runtime.tasks.cancel(identifier)}

    return router
