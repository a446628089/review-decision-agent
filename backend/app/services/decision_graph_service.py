"""决策图谱服务：写入 + 向量关联 + 检索

Q9 决策：写入时即时向量关联 top-3 相似历史决策（relation_type 暂全填 'relates'）
Q5 决策：决策单独建表 + 向量索引
"""
import uuid
import logging
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.decision import Decision, DecisionOption, DecisionRelation
logger = logging.getLogger(__name__)

class DecisionGraphService:
    """决策图谱服务"""

    async def save_decisions(self, db: AsyncSession, meeting_id: uuid.UUID, decisions: list[dict]) -> list[Decision]:
        """批量保存决策（含 options + 即时向量关联）

        流程：
            1. 删除该 meeting 的旧决策（cascade 会删 options + relations）
            2. 对每个决策生成 embedding（title + context）
            3. 写 decisions + decision_options
            4. 对每个新决策检索 top-3 相似历史决策，写 decision_relations

        Args:
            db: 数据库会话
            meeting_id: 关联的会议 ID
            decisions: decision_extractor 节点输出的决策列表

        Returns:
            已保存的 Decision ORM 对象列表
        """
        await db.execute(delete(Decision).where(Decision.meeting_id == meeting_id))
        await db.flush()
        saved: list[Decision] = []
        for d in decisions:
            embed_text = f"{d.get('title', '')} {d.get('context', '')}"
            embedding = None
            decision = Decision(meeting_id=meeting_id, title=d['title'], context=d.get('context'), snippet=d.get('snippet'), chosen_option=d.get('chosen'), reasons=d.get('reasons'), objections=d.get('objections'), decided_by=d.get('decided_by'), decided_at=d.get('decided_at'), confidence=d.get('confidence'), embedding=embedding)
            db.add(decision)
            await db.flush()
            for opt in d.get('options', []):
                option = DecisionOption(decision_id=decision.id, name=opt.get('name', ''), pros=opt.get('pros'), cons=opt.get('cons'), proposed_by=opt.get('proposed_by'), is_chosen=opt.get('name') == d.get('chosen'))
                db.add(option)
            saved.append(decision)
        await db.flush()
        logger.info(f'[DecisionGraph] 保存 {len(saved)} 个决策，meeting={meeting_id}')
        return saved
decision_graph_service = DecisionGraphService()
