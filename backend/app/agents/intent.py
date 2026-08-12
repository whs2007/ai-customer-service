"""意图分类规则（08 §4.4 / 03 §7）。

默认关键词规则 + settings(group=intent) 覆盖；未配置时使用默认规则。
"""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import get_intent_rules

DEFAULT_INTENT_RULES: dict = {
    "keywords": {
        "transfer": ["转人工", "人工客服", "转接人工", "找人工", "人工处理"],
        "complaint": ["投诉", "不满意", "举报", "差评", "态度差", "太过分了", "太差了"],
        "order_query": ["订单", "物流", "运单", "快递", "到哪了", "发货了没", "发货"],
        "policy_query": [
            "退货", "退款", "换货", "政策", "运费", "保修", "售后", "签收",
            "到账", "激活", "卸载", "多久", "怎么", "可以吗", "怎么办", "吗",
        ],
    },
    "order_no_pattern": r"\b\d{15}\b",
}

INTENT_ORDER = ["transfer", "complaint", "order_query", "policy_query"]


def classify_intent(text: str, rules: dict) -> tuple[str, str | None]:
    """返回 (intent, order_no)。优先级：转人工 > 投诉 > 订单 > 政策 > 其他。"""
    keywords = rules.get("keywords", DEFAULT_INTENT_RULES["keywords"])
    order_no = None
    pattern = rules.get("order_no_pattern") or DEFAULT_INTENT_RULES["order_no_pattern"]
    match = re.search(pattern, text)
    if match:
        order_no = match.group(0)

    for intent in INTENT_ORDER:
        for kw in keywords.get(intent, []):
            if kw and kw in text:
                return intent, order_no
    # 出现 15 位订单号但无关键词命中 → 视为订单查询（表单提交场景）
    if order_no:
        return "order_query", order_no
    return "other", order_no


async def classify_with_rules(db: AsyncSession, text: str) -> tuple[str, str | None]:
    rules = await get_intent_rules(db)
    return classify_intent(text, rules)
