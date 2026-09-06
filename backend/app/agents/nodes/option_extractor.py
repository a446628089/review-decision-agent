"""OptionExtractor：两步流水线 Step 2 - 结构化抽取候选方案/理由/反对意见

Q4 决策：对每个 DecisionSegment 抽取结构化选项

输入：DecisionSegment + 完整转写文本（用于取上下文）
输出：ExtractedDecision（含 options / chosen / reasons / objections / decided_by）
"""
import json
import logging
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from app.config import settings
from app.agents.nodes.decision_detector import DecisionSegment
logger = logging.getLogger(__name__)

class DecisionOption(BaseModel):
    """决策候选方案"""
    name: str = Field(..., max_length=30)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    proposed_by: str | None = None

class Objection(BaseModel):
    """反对意见（保留少数派观点）"""
    model_config = ConfigDict(populate_by_name=True)
    frm: str = Field(..., alias='from', description='反对人')
    content: str = Field(..., description='反对意见内容')

class ExtractedDecision(BaseModel):
    """OptionExtractor 输出的结构化决策"""
    title: str = Field(..., max_length=50, description='决策标题（动词开头）')
    context: str = Field(..., max_length=300, description='决策上下文')
    options: list[DecisionOption] = Field(..., min_length=1, max_length=5)
    chosen: str = Field(..., description='最终选定方案名')
    reasons: list[str] = Field(default_factory=list)
    objections: list[Objection] = Field(default_factory=list)
    decided_by: list[str] = Field(default_factory=list)
EXTRACTOR_PROMPT = '你是评审会议决策结构化专家。从以下决策段抽取候选方案、理由、反对意见、最终决议。\n\n【决策段】\n{snippet}\n\n【上下文（前后内容）】\n{context}\n\n【输出 JSON】\n{{\n  "title": "决策标题（≤50 字，动词开头）",\n  "context": "决策上下文（≤300 字）",\n  "options": [\n    {{"name": "方案名", "pros": ["优点"], "cons": ["缺点"], "proposed_by": "提议人"}}\n  ],\n  "chosen": "最终选定方案名",\n  "reasons": ["选择理由"],\n  "objections": [{{"from": "反对人", "content": "反对意见"}}],\n  "decided_by": ["决策人"]\n}}\n\n约束：\n- options 1~5 个\n- 无反对意见时 objections 为 []\n- decided_by 必须从转写标签抽取，不能臆造\n- chosen 必须等于 options 中某个 name\n'

async def extract_options(segment: DecisionSegment, full_transcript: str) -> ExtractedDecision | None:
    """对单个决策段抽取结构化选项

    Args:
        segment: DecisionDetector 输出的决策段
        full_transcript: 完整转写文本（用于取上下文）

    Returns:
        结构化决策对象；解析失败返回 None
    """
    idx = full_transcript.find(segment.snippet)
    if idx >= 0:
        start = max(0, idx - 500)
        end = min(len(full_transcript), idx + len(segment.snippet) + 500)
        context = full_transcript[start:end]
    else:
        context = segment.snippet
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    try:
        resp = await client.chat.completions.create(model=settings.LLM_MODEL, messages=[{'role': 'system', 'content': '你只输出 JSON 对象，不要任何解释、不要 markdown 代码块。'}, {'role': 'user', 'content': EXTRACTOR_PROMPT.format(snippet=segment.snippet, context=context)}], temperature=0.0, response_format={'type': 'json_object'})
    except Exception as e:
        logger.error(f'[OptionExtractor] LLM 调用失败: {e}')
        return None
    raw = resp.choices[0].message.content or ''
    try:
        data = json.loads(raw)
        decision = ExtractedDecision.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning(f'[OptionExtractor] 解析失败: {e} | raw={raw[:200]}')
        return None
    option_names = [opt.name for opt in decision.options]
    if decision.chosen not in option_names:
        logger.warning(f'[OptionExtractor] chosen={decision.chosen!r} 不在 options={option_names}，自动取第一个 option 作为 chosen')
        if decision.options:
            decision = decision.model_copy(update={'chosen': decision.options[0].name})
    return decision
