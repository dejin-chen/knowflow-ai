from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.schemas.agent import AgentExecutionStep


class AgentRunRepository:
    """负责 Agent 调度记录与步骤记录的持久化。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        conversation_id: int,
        knowledge_base_id: int,
        assistant_message_id: int,
        intent: str,
        steps: list[AgentExecutionStep],
    ) -> AgentRun:
        agent_run = AgentRun(
            conversation_id=conversation_id,
            knowledge_base_id=knowledge_base_id,
            assistant_message_id=assistant_message_id,
            intent=intent,
        )
        self.db.add(agent_run)
        self.db.flush()
        self.db.add_all(
            [
                AgentStep(
                    agent_run_id=agent_run.id,
                    step_order=step.step_order,
                    name=step.name,
                    tool_name=step.tool_name,
                    status=step.status,
                    detail=step.detail,
                )
                for step in steps
            ]
        )
        self.db.commit()
        self.db.refresh(agent_run)
        return agent_run

    def get_by_assistant_message_ids(
        self,
        assistant_message_ids: list[int],
    ) -> dict[int, AgentRun]:
        if not assistant_message_ids:
            return {}

        statement = (
            select(AgentRun)
            .where(AgentRun.assistant_message_id.in_(assistant_message_ids))
            .options(selectinload(AgentRun.steps))
        )
        agent_runs = self.db.scalars(statement).all()
        return {agent_run.assistant_message_id: agent_run for agent_run in agent_runs}
