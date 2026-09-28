from types import SimpleNamespace

from hitl import ApprovalRequest, ApprovalStatus, PendingApproval


def test_pending_approval_preserves_request_and_tool_call():
    tool_call = SimpleNamespace(call_id="call-1")
    request = ApprovalRequest(tool_call=tool_call, reason="approval required")
    pending = PendingApproval(approval_request=request)

    assert request.status is ApprovalStatus.PENDING
    assert request.tool_call is tool_call
    assert pending.approval_request is request
