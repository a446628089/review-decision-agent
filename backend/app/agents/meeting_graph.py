"""Multi-Agent 会议纪要生成编排

基于 LangGraph 构建 Agent 协作流程：
1. 摘要 Agent：提炼会议核心内容（Markdown）
2. 行动项 Agent：提取待办事项、负责人、截止日期
3. 风险识别 Agent：识别风险点与严重程度
4. 综合输出：汇总所有结果

三个 Agent 并行执行，最后汇总。
"""
import json
import logging
import re
import operator
from typing import Annotated, TypedDict, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from app.config import settings
logger = logging.getLogger(__name__)

def _extract_json(text: str) -> list | dict | None:
    """从 LLM 响应中稳健地提取 JSON

    处理常见问题：
    1. ```json ... ``` 代码块包裹
    2. 前后多余的解释文本
    3. 尾部多余逗号
    """
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    code_block = re.search('```(?:json)?\\s*\\n?(.*?)\\n?```', text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass
    for start_char, end_char in [('[', ']'), ('{', '}')]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and (end > start):
            candidate = text[start:end + 1]
            candidate = re.sub(',\\s*([}\\]])', '\\1', candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
    return None

async def _invoke_with_retry(llm: ChatOpenAI, messages: list, max_retries: int=2) -> tuple[Optional[str], Optional[str]]:
    """带重试的 LLM 调用

    处理瞬时错误（网络、限流）。
    返回 (content, error_msg)，成功时 error_msg=None，失败时 content=None。

    成功时顺便把 token usage 累计到 BudgetGuard（如果上下文中有）。
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await llm.ainvoke(messages)
            return (response.content, None)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.debug(f'LLM 调用失败 (attempt {attempt + 1}/{max_retries + 1}): {e}')
            else:
                logger.error(f'LLM 调用最终失败（重试 {max_retries} 次后）: {e}')
    return (None, _classify_llm_error(last_error) if last_error else 'LLM 调用失败')

def _classify_llm_error(err: Exception) -> str:
    """将 LLM 错误分类为用户友好的提示"""
    err_str = str(err).lower()
    if 'freequota' in err_str or 'quota' in err_str or 'freetier' in err_str:
        return 'AI 模型免费额度已用尽，请检查 DashScope 控制台额度或开通付费'
    if 'rate_limit' in err_str or 'rate limit' in err_str:
        return 'AI 模型调用频率超限，请稍后重试'
    if 'timeout' in err_str or 'timed out' in err_str:
        return 'AI 模型调用超时，请稍后重试'
    if 'authentication' in err_str or 'api key' in err_str or 'unauthorized' in err_str:
        return 'AI 服务认证失败，请检查 OPENAI_API_KEY 配置'
    return f'AI 模型调用失败：{err}'

class ActionItemResult(TypedDict):
    """行动项结构"""
    title: str
    assignee: Optional[str]
    due_date: Optional[str]
    priority: str

class RiskResult(TypedDict):
    """风险结构"""
    description: str
    severity: str
    mitigation: Optional[str]

class MeetingAgentState(TypedDict):
    """Multi-Agent 共享状态"""
    meeting_id: str
    meeting_title: str
    transcript_text: str
    summary: str
    key_points: list[str]
    action_items: list[ActionItemResult]
    risks: list[RiskResult]
    errors: Annotated[list[str], operator.add]

def get_llm() -> ChatOpenAI:
    """获取 LLM 实例（通义千问，兼容 OpenAI 接口）"""
    return ChatOpenAI(model=settings.LLM_MODEL, temperature=0.3, api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
SUMMARY_SYSTEM_PROMPT = '你是一位专业的会议纪要撰写助手。\n根据提供的会议转写文本，生成结构化的会议纪要。\n\n输出要求：\n1. 使用 Markdown 格式\n2. 包含以下部分：\n   - 会议概述（简短描述会议目的与主要议题）\n   - 关键讨论点（按议题分组，每个议题 2-3 句话总结）\n   - 主要结论（会议达成的共识与决定）\n3. 语言简洁专业，避免冗余\n4. 如果转写文本为空或无效，返回"无法生成纪要：转写内容为空"\n'
ACTION_ITEMS_SYSTEM_PROMPT = '你是一位会议行动项提取助手。\n从会议转写文本中识别所有的待办事项、行动项和后续任务。\n\n输出要求：\n1. 返回 JSON 数组，每个元素包含：\n   - title: 任务标题（简洁明确）\n   - assignee: 负责人姓名（如未明确提及则为 null）\n   - due_date: 截止日期（YYYY-MM-DD 格式，如未提及则为 null）\n   - priority: 优先级（"high" / "medium" / "low"）\n2. 只返回 JSON 数组，不要包含其他文字\n3. 如果没有识别到行动项，返回空数组 []\n4. 优先级判断标准：\n   - high: 涉及关键决策、紧急事项、明确截止日期临近\n   - medium: 常规任务\n   - low: 可选或长期任务\n\n示例输出：\n[\n  {"title": "完成产品需求文档", "assignee": "张三", "due_date": "2024-12-31", "priority": "high"},\n  {"title": "安排下次评审会议", "assignee": null, "due_date": null, "priority": "medium"}\n]\n'
RISKS_SYSTEM_PROMPT = '你是一位会议风险识别助手。\n从会议转写文本中识别潜在的风险点、问题与障碍。\n\n输出要求：\n1. 返回 JSON 数组，每个元素包含：\n   - description: 风险描述（清晰具体）\n   - severity: 严重程度（"high" / "medium" / "low"）\n   - mitigation: 缓解措施建议（如无则为 null）\n2. 只返回 JSON 数组，不要包含其他文字\n3. 如果没有识别到风险，返回空数组 []\n4. 严重程度判断标准：\n   - high: 可能导致项目延期、成本超支或关键目标无法达成\n   - medium: 需要关注但不立即威胁目标\n   - low: 次要问题，影响有限\n\n示例输出：\n[\n  {"description": "前端开发资源不足，可能影响上线时间", "severity": "high", "mitigation": "考虑外包或调整排期"}\n]\n'

async def summary_agent(state: MeetingAgentState) -> dict:
    """摘要 Agent：生成 Markdown 纪要"""
    llm = get_llm()
    messages = [SystemMessage(content=SUMMARY_SYSTEM_PROMPT), HumanMessage(content=f"会议标题：{state['meeting_title']}\n\n转写文本：\n{state['transcript_text']}")]
    try:
        content, error_msg = await _invoke_with_retry(llm, messages)
        if content is None:
            return {'summary': '', 'key_points': [], 'errors': [error_msg or 'LLM 调用失败']}
        summary_content = content.strip()
        key_points = []
        for line in summary_content.split('\n'):
            line = line.strip()
            if line.startswith('- ') or line.startswith('* '):
                key_points.append(line[2:])
        return {'summary': summary_content, 'key_points': key_points[:10]}
    except Exception as e:
        logger.error(f'摘要 Agent 失败: {e}')
        return {'summary': '', 'key_points': [], 'errors': [_classify_llm_error(e)]}

async def action_items_agent(state: MeetingAgentState) -> dict:
    """行动项 Agent：提取待办事项"""
    llm = get_llm()
    messages = [SystemMessage(content=ACTION_ITEMS_SYSTEM_PROMPT), HumanMessage(content=f"会议标题：{state['meeting_title']}\n\n转写文本：\n{state['transcript_text']}")]
    try:
        content, error_msg = await _invoke_with_retry(llm, messages)
        if content is None:
            return {'action_items': [], 'errors': [error_msg or 'LLM 调用失败']}
        items = _extract_json(content)
        if not isinstance(items, list):
            logger.warning(f'行动项解析失败，原始响应: {content[:200]}')
            items = []
        return {'action_items': items}
    except Exception as e:
        logger.error(f'行动项 Agent 失败: {e}')
        return {'action_items': [], 'errors': [_classify_llm_error(e)]}

async def risks_agent(state: MeetingAgentState) -> dict:
    """风险识别 Agent"""
    llm = get_llm()
    messages = [SystemMessage(content=RISKS_SYSTEM_PROMPT), HumanMessage(content=f"会议标题：{state['meeting_title']}\n\n转写文本：\n{state['transcript_text']}")]
    try:
        content, error_msg = await _invoke_with_retry(llm, messages)
        if content is None:
            return {'risks': [], 'errors': [error_msg or 'LLM 调用失败']}
        risks = _extract_json(content)
        if not isinstance(risks, list):
            logger.warning(f'风险解析失败，原始响应: {content[:200]}')
            risks = []
        return {'risks': risks}
    except Exception as e:
        logger.error(f'风险 Agent 失败: {e}')
        return {'risks': [], 'errors': [_classify_llm_error(e)]}

def build_meeting_graph():
    """构建 Multi-Agent 编排图

    流程：
        START → [summary, action_items, risks]（并行）→ END
    """
    workflow = StateGraph(MeetingAgentState)
    workflow.add_node('summary_agent', summary_agent)
    workflow.add_node('action_items_agent', action_items_agent)
    workflow.add_node('risks_agent', risks_agent)
    workflow.set_entry_point('summary_agent')
    workflow.add_edge('summary_agent', 'action_items_agent')
    workflow.add_edge('summary_agent', 'risks_agent')
    workflow.add_edge('action_items_agent', END)
    workflow.add_edge('risks_agent', END)
    return workflow.compile()
meeting_graph = build_meeting_graph()
