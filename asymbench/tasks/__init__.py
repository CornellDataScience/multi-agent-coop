"""Task registry: id -> Task instance."""

from .base import Task
from .claim import ClaimTask
from .commons import CommonsTask
from .contract import ContractTask
from .knowledge import KnowledgeRelTask, KnowledgeTask
from .sale import SaleTask

TASKS: dict[str, Task] = {
    t.id: t for t in (CommonsTask(), SaleTask(), ContractTask(), ClaimTask(),
                      KnowledgeTask(), KnowledgeRelTask())
}

TASK_ORDER = ["commons", "sale", "contract", "claim", "knowledge", "knowledge_rel"]
