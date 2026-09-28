"""闲聊轨道：问候/客套/寒暄的规则兜底，不上 LLM。

职责：
    1. 识别轻量闲聊（你好/谢谢/夸奖/告别），返回自然回复。
    2. 业务意图、手册知识不走这里；认不出则返回 None，交给能力说明。

设计：
    1. 短语包含即可命中（中文口语），但必须排除业务/知识关键词，避免抢走任务。
    2. 回复话术对齐架构文档 2.3：自我介绍 + 可办事项，语气比 CAPABILITY_TIP 更口语。
"""

from __future__ import annotations

import re
from typing import Optional

# 业务/知识词：句子里出现则不当成闲聊（防止「你好，帮我查保修」被闲聊吞掉）
_BUSINESS_HINTS = (
    "保修", "质保", "warranty",
    "报修", "建单", "工单", "维修单",
    "进度", "物流", "修到哪",
    "转人工", "人工客服", "人工",
    "手册", "说明书", "怎么配", "怎么设置", "怎么用", "怎么使用",
    "如何配置", "如何设置", "如何使用", "VLAN",
    "DEV-", "TKT-",
)

_GREETING = (
    "你好，这里是设备售后助手。我可以帮你查手册、查保修、创建维修工单，或转接人工。",
)
_THANKS = (
    "不客气，很高兴帮到您。还有其他设备问题随时找我。",
    "没事，这是我应该做的。需要查保修或报修也可以直接说。",
)
_PRAISE = (
    "谢谢夸奖！我先专注把设备问题处理好。要查保修、报修或问手册吗？",
    "过奖啦。您说设备相关的事就行，我来帮您跟进。",
)
_FAREWELL = (
    "再见，祝您使用顺利。设备有问题随时回来找我。",
    "好的，再见。需要时喊我一声就行。",
)
_SMALL_TALK = (
    "我这边主要帮您处理设备售后：查保修、报修、维修进度、查手册，或转人工。",
)

_GREETING_WORDS = (
    "你好", "您好", "哈喽", "hello", "hi ", "hi！", "hi!", "嗨", "嘿",
    "在吗", "在么", "在不在",
    "早上好", "早安", "早", "下午好", "晚上好", "晚安",
    "good morning", "good afternoon", "good evening",
)
_THANKS_WORDS = ("谢谢", "多谢", "感谢", "谢啦", "谢了", "thx", "thanks", "thank you", "3q")
_PRAISE_WORDS = ("聪明", "厉害", "真棒", "好棒", "挺好的", "不错不错", "牛", "给力", "点赞")
_FAREWELL_WORDS = ("再见", "拜拜", "告辞", "bye", "goodbye", "回头见", "下次见")


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(w in text or w in lowered for w in words)


def reply(text: str) -> Optional[str]:
    """闲聊回复；非闲聊返回 None。

    步骤：
        1. 空句、含业务/知识词 → None（不抢任务/知识轨道）。
        2. 按告别 > 感谢 > 夸奖 > 问候 > 一般寒暄 的顺序命中。
        3. 都不中则 None，由上层给能力说明。

    Args:
        text: 用户原文。

    Returns:
        Optional[str]: 闲聊话术；不该闲聊时 None。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if _contains_any(raw, _BUSINESS_HINTS):
        return None

    if _contains_any(raw, _FAREWELL_WORDS):
        return _FAREWELL[0]
    if _contains_any(raw, _THANKS_WORDS):
        return _THANKS[0]
    if _contains_any(raw, _PRAISE_WORDS):
        return _PRAISE[0]
    if _contains_any(raw, _GREETING_WORDS):
        return _GREETING[0]

    # 极短闲句（无业务词）给引导，避免冷冰冰的清单
    if len(raw) <= 8 and not re.search(r"[？?。！!]", raw[-1:] or ""):
        return _SMALL_TALK[0]
    if raw.endswith(("？", "?")) and len(raw) <= 12:
        return _SMALL_TALK[0]
    return None
