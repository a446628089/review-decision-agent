"""DecisionDetector：两步流水线 Step 1 - 全量扫描定位决策段

Q6 决策：LLM 全量扫描 + 严格 Prompt 约束（明确区分决策/提议/推迟）

输入：带说话人标签的转写文本（Q3 决策）
输出：list[DecisionSegment]，只保留 type=decision 且 confidence >= 0.7
"""
import json
import logging
from typing import Literal
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError
from app.config import settings
logger = logging.getLogger(__name__)

class DecisionSegment(BaseModel):
    """决策段：DecisionDetector 输出的最小单元"""
    snippet: str = Field(..., max_length=200, description='决策段原文（≤200 字）')
    type: Literal['decision', 'proposal', 'deferred'] = Field(..., description='decision=已拍板 / proposal=提议未定 / deferred=推迟')
    confidence: float = Field(..., ge=0.0, le=1.0, description='置信度')
DETECTOR_PROMPT = '你是评审会议决策识别专家。请扫描以下会议转写，找出所有「明确的决策」。\n\n【决策的定义】\n- 必须有最终拍板：「我们定...」「那就...」「拍板...」「一致同意...」\n- 必须有具体方案：不是「下次再讨论」，而是「选 PostgreSQL」\n\n【不算决策的情况】\n- 提议但未拍板：「我觉得可以试试 X」 → type=proposal\n- 推迟到下次：「这个下次再聊」 → type=deferred\n- 单纯讨论：「X 的优点是...」 → 不输出\n\n【输出 JSON】\n{{\n  "items": [\n    {{"snippet": "决策段原文（≤200 字）", "type": "decision|proposal|deferred", "confidence": 0.0~1.0}}\n  ]\n}}\n\n【转写文本】\n{transcript}\n'

async def detect_decisions(transcript_text: str) -> list[DecisionSegment]:
    """全量扫描转写文本，定位所有决策段

    Args:
        transcript_text: 带说话人标签的完整转写文本

    Returns:
        过滤后的决策段列表（仅 type=decision 且 confidence >= 0.7）
    """
    if not transcript_text or not transcript_text.strip():
        return []
    transcript_truncated = transcript_text[:8000]
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    try:
        resp = await client.chat.completions.create(model=settings.LLM_MODEL, messages=[{'role': 'system', 'content': '你只输出 JSON 对象，不要任何解释、不要 markdown 代码块。'}, {'role': 'user', 'content': DETECTOR_PROMPT.format(transcript=transcript_truncated)}], temperature=0.0, response_format={'type': 'json_object'})
    except Exception as e:
        logger.error(f'[DecisionDetector] LLM 调用失败: {e}')
        return []
    raw = resp.choices[0].message.content or ''
    segments = _parse_segments(raw)
    if not segments:
        logger.warning(f'[DecisionDetector] JSON 解析失败: {raw[:200]}')
        return []
    filtered = [s for s in segments if s.type == 'decision' and s.confidence >= 0.7]
    logger.info(f'[DecisionDetector] 识别 {len(segments)} 段，过滤后 {len(filtered)} 段')
    return filtered

def _parse_segments(raw: str) -> list[DecisionSegment]:
    """解析 LLM 返回的 JSON，兼容 {items: [...]} / {decisions: [...]} / [...] 三种格式"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get('items') or data.get('decisions') or data.get('segments') or []
        if isinstance(items, dict):
            items = items.get('items', [])
    else:
        return []
    segments: list[DecisionSegment] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            segments.append(DecisionSegment(**item))
        except ValidationError as e:
            logger.debug(f'[DecisionDetector] 跳过无效项: {item} - {e}')
    return segments
