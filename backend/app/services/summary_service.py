"""纪要生成业务逻辑层"""
import uuid
import logging
from datetime import date
from typing import Optional
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.meeting import Meeting
from app.models.summary import Summary
from app.models.action_item import ActionItem
from app.models.risk import Risk
from app.models.transcript import Transcript
from app.agents.meeting_graph import MeetingAgentState
logger = logging.getLogger(__name__)
USE_HARNESS_V2 = False

class SummaryService:
    """纪要生成与管理"""

    async def list_summaries(self, db: AsyncSession, skip: int=0, limit: int=20) -> tuple[list[tuple[Summary, Meeting]], int]:
        """获取所有纪要列表（附带会议信息）"""
        result = await db.execute(select(Summary, Meeting).join(Meeting, Summary.meeting_id == Meeting.id).order_by(Summary.created_at.desc()).offset(skip).limit(limit))
        rows = list(result.all())
        count_result = await db.execute(select(func.count(Summary.id)))
        total = count_result.scalar_one()
        return (rows, total)

    async def _build_transcript_text(self, db: AsyncSession, meeting_id: uuid.UUID) -> str:
        """构建转写文本（供 Agent 使用）"""
        result = await db.execute(select(Transcript).where(Transcript.meeting_id == meeting_id).order_by(Transcript.seq_index))
        transcripts = list(result.scalars().all())
        if not transcripts:
            return ''
        lines = []
        for t in transcripts:
            speaker = t.speaker or '未知'
            lines.append(f'[{speaker}]: {t.content}')
        return '\n'.join(lines)

    async def generate_summary(self, db: AsyncSession, meeting_id: uuid.UUID) -> Optional[Summary]:
        """触发 Multi-Agent 生成纪要（Harness 升级版）"""
        meeting_result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = meeting_result.scalar_one_or_none()
        if not meeting:
            return None
        transcript_text = await self._build_transcript_text(db, meeting_id)
        if not transcript_text:
            logger.warning(f'会议 {meeting_id} 无转写内容')
            return None
        await db.execute(delete(Summary).where(Summary.meeting_id == meeting_id))
        await db.execute(delete(ActionItem).where(ActionItem.meeting_id == meeting_id))
        await db.execute(delete(Risk).where(Risk.meeting_id == meeting_id))
        await db.flush()
        summary = Summary(meeting_id=meeting_id, content='', status='generating')
        db.add(summary)
        await db.flush()
        return await self._run_v1_workflow(db, meeting_id, meeting, transcript_text, summary)

    async def _run_v1_workflow(self, db: AsyncSession, meeting_id: uuid.UUID, meeting: Meeting, transcript_text: str, summary: Summary) -> Optional[Summary]:
        """执行 v1 工作流（降级用）"""
        from app.agents.meeting_graph import meeting_graph
        initial_state: MeetingAgentState = {'meeting_id': str(meeting_id), 'meeting_title': meeting.title, 'transcript_text': transcript_text, 'summary': '', 'key_points': [], 'action_items': [], 'risks': [], 'errors': []}
        try:
            final_state = await meeting_graph.ainvoke(initial_state)
            from app.agents.nodes.decision_extractor import decision_extractor_node
            from app.services.decision_graph_service import decision_graph_service
            extracted = await decision_extractor_node(initial_state)
            if extracted.get("decisions"):
                await decision_graph_service.save_decisions(db, meeting_id, extracted["decisions"])
            errors: list[str] = final_state.get('errors', [])
            if errors:
                unique_errors = list(dict.fromkeys(errors))
                error_msg = unique_errors[0]
                summary.status = 'failed'
                summary_content = final_state.get('summary', '')
                if summary_content:
                    summary.content = f'{summary_content}\n\n---\n\n⚠️ 部分内容生成失败：{error_msg}'
                else:
                    summary.content = f'⚠️ {error_msg}'
                summary.key_points = final_state.get('key_points', [])
                await self._save_action_items_and_risks(db, meeting_id, final_state)
                await db.flush()
                await db.refresh(summary)
                return summary
            summary.content = final_state.get('summary', '')
            summary.key_points = final_state.get('key_points', [])
            summary.status = 'completed'
            await self._save_action_items_and_risks(db, meeting_id, final_state)
            await db.flush()
            await db.refresh(summary)
            try:
                from app.services.knowledge_service import knowledge_service
                await knowledge_service.index_meeting_summary(db=db, meeting_id=meeting_id, meeting_title=meeting.title, summary_content=summary.content)
            except Exception as idx_err:
                logger.warning(f'知识库索引失败: {idx_err}')
            return summary
        except Exception as e:
            logger.error(f'纪要生成失败: {e}')
            summary.status = 'failed'
            summary.content = f'⚠️ 纪要生成异常：{str(e)}'
            await db.flush()
            await db.refresh(summary)
            return summary

    async def _save_action_items_and_risks(self, db: AsyncSession, meeting_id: uuid.UUID, final_state: dict) -> None:
        """保存行动项和风险（成功或部分失败时都调用）"""
        for item in final_state.get('action_items', []):
            due_date = None
            if item.get('due_date'):
                try:
                    due_date = date.fromisoformat(item['due_date'])
                except (ValueError, TypeError):
                    pass
            action_item = ActionItem(meeting_id=meeting_id, title=item.get('title', ''), assignee=item.get('assignee'), due_date=due_date, priority=item.get('priority', 'medium'), status='pending')
            db.add(action_item)
        for risk in final_state.get('risks', []):
            risk_item = Risk(meeting_id=meeting_id, description=risk.get('description', ''), severity=risk.get('severity', 'medium'), mitigation=risk.get('mitigation'))
            db.add(risk_item)

    async def get_summary(self, db: AsyncSession, meeting_id: uuid.UUID) -> Optional[Summary]:
        """获取会议纪要"""
        result = await db.execute(select(Summary).where(Summary.meeting_id == meeting_id))
        return result.scalar_one_or_none()

    async def get_action_items(self, db: AsyncSession, meeting_id: uuid.UUID) -> list[ActionItem]:
        """获取行动项"""
        result = await db.execute(select(ActionItem).where(ActionItem.meeting_id == meeting_id).order_by(ActionItem.created_at))
        return list(result.scalars().all())

    async def get_risks(self, db: AsyncSession, meeting_id: uuid.UUID) -> list[Risk]:
        """获取风险"""
        result = await db.execute(select(Risk).where(Risk.meeting_id == meeting_id).order_by(Risk.created_at))
        return list(result.scalars().all())
summary_service = SummaryService()
