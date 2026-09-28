from dataclasses import dataclass
from enum import Enum
from typing import Any


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ApprovalRequest:
    tool_call: Any
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING


@dataclass
class PendingApproval:
    approval_request: ApprovalRequest
