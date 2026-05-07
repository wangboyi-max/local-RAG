import json
import logging
import time
from abc import ABC, abstractmethod

import jieba.analyse
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 常见中文停用词
STOP_WORDS = set(
    "的 了 是 在 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 已经 如果 这 那 他 她 它 们 中 与 及 等 而 但 或 被 把 从 向 对 于 以 关于".split()
)

LLM_SYSTEM_PROMPT = """你是一个信息抽取助手。请从给定文本中提取关键实体（名词、专有名词、概念、人物、组织、技术等），以 JSON 格式返回。

要求：
1. 每个实体包含 name（实体名称）和 type（类型，如 concept/person/organization/technology/product/location/other）
2. 实体应是文本中有实际意义的关键词或短语
3. 最多返回 {max_entities} 个实体
4. 只返回 JSON 数组，不要其他解释

输出格式：
[
  {{"name": "实体1", "type": "concept"}},
  {{"name": "实体2", "type": "organization"}}
]"""

MAX_RETRIES = 2
RETRY_DELAY = 1  # 秒


class EntityExtractor(ABC):
    """实体提取基类。"""

    @abstractmethod
    def extract(self, text: str) -> list[dict]:
        """从文本中提取实体，返回 [{"name": "...", "type": "..."}]。"""
        ...

    @abstractmethod
    def close(self):
        ...


class JiebaEntityExtractor(EntityExtractor):
    """使用 jieba TF-IDF 关键词提取。"""

    def extract(self, text: str) -> list[dict]:
        keywords = jieba.analyse.extract_tags(
            text, topK=settings.graph_max_entities, withWeight=False
        )
        return [
            {"name": kw, "type": "keyword"}
            for kw in keywords
            if kw not in STOP_WORDS and len(kw) > 1
        ]

    def close(self):
        pass


class LLMEntityExtractor(EntityExtractor):
    """使用 LLM API（OpenAI 兼容格式）从文本中提取实体。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.llm_api_key
        self.base_url = (base_url or settings.llm_api_base).rstrip("/")
        self.model = model or settings.llm_model
        self.max_entities = settings.graph_max_entities
        self._client = httpx.Client(timeout=30.0)

    def extract(self, text: str) -> list[dict]:
        """从单条文本中提取实体列表，返回 [{"name": "...", "type": "..."}]。"""
        prompt = LLM_SYSTEM_PROMPT.format(max_entities=self.max_entities)
        # 截断过长文本，控制 token 用量
        if len(text) > 2000:
            text = text[:2000] + "..."

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": text},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                entities = self._parse_entities(content)

                if entities:
                    logger.debug("extracted %d entities on attempt %d", len(entities), attempt)
                    return entities

                # 解析失败，记录并决定是否重试
                logger.warning(
                    "LLM returned content but no entities parsed (attempt %d/%d). "
                    "Content preview: %s",
                    attempt,
                    MAX_RETRIES,
                    content[:100],
                )
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "LLM API HTTP error: %s (attempt %d/%d)",
                    e.response.status_code,
                    attempt,
                    MAX_RETRIES,
                )
            except Exception as e:
                logger.warning(
                    "LLM API call failed: %s (attempt %d/%d)",
                    e,
                    attempt,
                    MAX_RETRIES,
                )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        logger.error("entity extraction failed after %d attempts, returning empty", MAX_RETRIES)
        return []

    def _parse_entities(self, content: str) -> list[dict]:
        """从 LLM 返回的文本中解析 JSON 实体列表。"""
        # 跳过推理模型的 <think>...</think> 标签
        think_end = content.find("</think>")
        if think_end != -1:
            content = content[think_end + len("</think>"):]

        # 找到第一个 [ 或 { 的位置
        first_bracket = content.find("[")
        if first_bracket != -1:
            first_char = "["
            first_pos = first_bracket
        else:
            first_brace = content.find("{")
            if first_brace == -1:
                return []
            first_char = "{"
            first_pos = first_brace

        # 找到匹配的闭合括号
        depth = 0
        end = first_pos
        open_c, close_c = ("[", "]") if first_char == "[" else ("{", "}")
        for i in range(first_pos, len(content)):
            if content[i] == open_c:
                depth += 1
            elif content[i] == close_c:
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        json_str = content[first_pos:end]
        try:
            entities = json.loads(json_str)
            if isinstance(entities, list):
                return [
                    {"name": e["name"], "type": e.get("type", "other")}
                    for e in entities
                    if isinstance(e, dict) and "name" in e and e["name"]
                ]
            elif isinstance(entities, dict) and "name" in entities:
                return [{"name": entities["name"], "type": entities.get("type", "other")}]
        except (json.JSONDecodeError, KeyError):
            pass
        return []

    def close(self):
        self._client.close()


def create_extractor() -> EntityExtractor:
    """根据配置创建实体提取器。"""
    method = settings.graph_entity_extractor
    if method == "llm":
        return LLMEntityExtractor()
    elif method == "jieba":
        return JiebaEntityExtractor()
    else:
        raise ValueError(f"未知的实体提取方法: {method}，可选值: jieba, llm")
