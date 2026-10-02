"""Version-one contracts. No account credentials or implicit external access."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.-]+$')
    source: str = Field(default='USER_ENTERED', min_length=1, max_length=200)
    observed_at: datetime

    @field_validator('observed_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None: raise ValueError('Timestamp must include timezone')
        return value.astimezone(timezone.utc)


class Balance(Record):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal['CASH', 'INVESTMENT', 'MUTUAL_FUND', 'LIABILITY']
    value: Decimal = Field(ge=0, max_digits=20, decimal_places=4, allow_inf_nan=False)
    currency: Literal['INR'] = 'INR'
    connected: bool = True


class Expense(Record):
    account_id: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=4, allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=80)
    categorization: Literal['USER_CONFIRMED', 'INFERRED'] = 'USER_CONFIRMED'
    description: str = Field(default='', max_length=500)


class Budget(Record):
    category: str = Field(min_length=1, max_length=80)
    month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    limit: Decimal = Field(gt=0, max_digits=20, decimal_places=4, allow_inf_nan=False)


class Bill(Record):
    title: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=4, allow_inf_nan=False)
    due_at: datetime
    paid: bool = False
    kind: Literal['BILL', 'EMI'] = 'BILL'

    @field_validator('due_at')
    @classmethod
    def due_aware(cls, value): return cls.aware(value)


class Goal(Record):
    title: str = Field(min_length=1, max_length=120)
    target: Decimal = Field(gt=0, max_digits=20, decimal_places=4, allow_inf_nan=False)
    saved: Decimal = Field(default=0, ge=0, max_digits=20, decimal_places=4, allow_inf_nan=False)
    due_at: datetime

    @field_validator('due_at')
    @classmethod
    def due_aware(cls, value): return cls.aware(value)


class Task(Record):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime
    status: Literal['OPEN', 'DONE', 'CANCELLED'] = 'OPEN'
    kind: Literal['TASK', 'REMINDER', 'LEARNING', 'HABIT'] = 'TASK'
    recurrence_days: int | None = Field(default=None, ge=1, le=366)

    @field_validator('due_at')
    @classmethod
    def due_aware(cls, value): return cls.aware(value)


class CalendarEvent(Record):
    title: str = Field(min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime

    @field_validator('start_at', 'end_at')
    @classmethod
    def event_aware(cls, value): return cls.aware(value)

    @model_validator(mode='after')
    def chronology(self):
        if self.end_at <= self.start_at: raise ValueError('Event end must follow start')
        return self


class Note(Record):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(max_length=10000)


class Draft(Note):
    recipient: str = Field(default='', max_length=200)
    channel: Literal['EMAIL', 'MESSAGE'] = 'MESSAGE'


MODELS = {'balances': Balance, 'expenses': Expense, 'budgets': Budget, 'bills': Bill,
          'goals': Goal, 'tasks': Task, 'events': CalendarEvent, 'notes': Note, 'drafts': Draft}
