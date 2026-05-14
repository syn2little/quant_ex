"""Agent strategy iteration dashboard endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from web.api.services.agent_service import (
    create_agent_run,
    execute_agent_run_approved,
    execute_agent_run_safe,
    generate_agent_run_feedback,
    get_agent_run,
    list_agent_runs,
    regenerate_approval_template,
    update_command_approval,
)
from web.api.services.task_manager import get_task_manager

router = APIRouter()


class CreateAgentRunRequest(BaseModel):
    objective: str
    run_id: str | None = None
    use_llm: bool = False
    propose_actions: bool = True
    write_approval_template: bool = True
    append_memory: bool = False


class ApprovalUpdateRequest(BaseModel):
    approved: bool
    approved_by: str = "web"
    reason: str = ""


class ExecuteCommandsRequest(BaseModel):
    command_ids: list[str] | None = None


class ExecuteApprovedRequest(BaseModel):
    include_safe: bool = False
    command_ids: list[str] | None = None


class GenerateFeedbackRequest(BaseModel):
    control_csv: str | None = None
    rank_metric: str | None = None


@router.get("/runs")
def runs() -> list[dict]:
    return list_agent_runs()


@router.get("/runs/{run_id}")
def run_detail(run_id: str) -> dict:
    return get_agent_run(run_id)


@router.post("/runs")
async def create_run(request: CreateAgentRunRequest) -> dict:
    kwargs = {
        "objective": request.objective,
        "run_id": request.run_id,
        "use_llm": request.use_llm,
        "propose_actions": request.propose_actions,
        "write_approval_template": request.write_approval_template,
        "append_memory": request.append_memory,
    }
    if request.use_llm:
        task_id = await get_task_manager().start_sync_task(
            "agent_create",
            create_agent_run,
            page_key="agents",
            action_key="agents.create",
            **kwargs,
        )
        return {"task_id": task_id, "run_id": request.run_id}
    return create_agent_run(**kwargs)


@router.post("/runs/{run_id}/approval-template")
def approval_template(run_id: str) -> dict:
    return regenerate_approval_template(run_id)


@router.post("/runs/{run_id}/approvals/{command_id}")
def update_approval(run_id: str, command_id: str, request: ApprovalUpdateRequest) -> dict:
    return update_command_approval(
        run_id,
        command_id,
        approved=request.approved,
        approved_by=request.approved_by,
        reason=request.reason,
    )


@router.post("/runs/{run_id}/execute-safe")
async def execute_safe(run_id: str, request: ExecuteCommandsRequest | None = None) -> dict:
    task_id = await get_task_manager().start_sync_task(
        "agent_execute_safe",
        execute_agent_run_safe,
        run_id,
        page_key="agents",
        action_key="agents.execute_safe",
        command_ids=(request.command_ids if request else None),
    )
    return {"task_id": task_id, "run_id": run_id}


@router.post("/runs/{run_id}/execute-approved")
async def execute_approved(run_id: str, request: ExecuteApprovedRequest) -> dict:
    task_id = await get_task_manager().start_sync_task(
        "agent_execute_approved",
        execute_agent_run_approved,
        run_id,
        page_key="agents",
        action_key="agents.execute_approved",
        include_safe=request.include_safe,
        command_ids=request.command_ids,
    )
    return {"task_id": task_id, "run_id": run_id}


@router.post("/runs/{run_id}/feedback/{command_id}")
async def generate_feedback_from_candidate(run_id: str, command_id: str, request: GenerateFeedbackRequest) -> dict:
    task_id = await get_task_manager().start_sync_task(
        "agent_feedback",
        generate_agent_run_feedback,
        run_id,
        command_id,
        page_key="agents",
        action_key="agents.feedback",
        control_csv=request.control_csv,
        rank_metric=request.rank_metric,
    )
    return {"task_id": task_id, "run_id": run_id}
