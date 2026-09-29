from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class ExecutionContext:
    user_id: str
    run_id: str = field(default_factory=lambda: str(uuid4()))
