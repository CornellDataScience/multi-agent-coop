"""Task registry: id -> Task instance."""

from .base import Task
from .claim import ClaimTask
from .commons import CommonsTask
from .contract import ContractTask
from .sale import SaleTask

TASKS: dict[str, Task] = {
    t.id: t for t in (CommonsTask(), SaleTask(), ContractTask(), ClaimTask())
}

TASK_ORDER = ["commons", "sale", "contract", "claim"]
