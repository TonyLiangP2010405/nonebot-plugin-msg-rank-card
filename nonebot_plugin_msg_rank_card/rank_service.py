from __future__ import annotations

import asyncio
from typing import NamedTuple

from nonebot import get_driver
from nonebot.log import logger
from nonebot.plugin import get_plugin_by_module_name

from .card_generator import MemberInfo, RankCardGenerator, download_avatar
from .config import Config
from .data_source import get_period_rank_data

RANK_NOTE_SCENE = "msg_rank_card.rank"

PERIOD_TITLES = {
    "daily": "今日水群排行榜",
    "weekly": "本周水群排行榜",
    "monthly": "本月水群排行榜",
}
PERIOD_BROADCASTS = {
    "daily": "正在放送日报。。。",
    "weekly": "正在放送周报。。。",
    "monthly": "正在放送月报。。。",
}


def get_plugin_config() -> Config:
    try:
        driver_config = get_driver().config
        if hasattr(driver_config, "model_dump"):
            return Config.model_validate(driver_config.model_dump())
        return Config.parse_obj(driver_config.dict())
    except Exception:
        return Config()


def get_max_count() -> int:
    return max(1, min(get_plugin_config().msg_rank_max_count, 10))


def get_rank_for_period(group_id: str, period: str) -> list[dict]:
    return get_period_rank_data(group_id, period, max_count=get_max_count())


def get_broadcast_text(period: str) -> str:
    try:
        return PERIOD_BROADCASTS[period]
    except KeyError as e:
        raise ValueError(f"不支持的排行榜周期: {period}") from e


class AffectionDisplay(NamedTuple):
    """排行榜上展示的馒头好感度信息"""

    affection: int
    title: str
    note: str


async def _get_affection_display(group_id: str | None, user_id: str) -> AffectionDisplay | None:
    if not group_id or get_plugin_by_module_name("nonebot_plugin_mantou_affection") is None:
        return None
    try:
        from nonebot_plugin_mantou_affection import get_affection_snapshot

        snapshot = await get_affection_snapshot(group_id, user_id)
    except Exception as error:
        logger.debug(f"[msg-rank-card] 读取馒头好感度失败: {error}")
        return None
    note = await _get_affection_note(group_id, user_id)
    return AffectionDisplay(affection=snapshot.affection, title=snapshot.title, note=note)


async def _get_affection_note(group_id: str, user_id: str) -> str:
    """读取当前好感阶段的馒头短评，读取失败或没有文案时返回空字符串。"""
    try:
        from nonebot_plugin_mantou_affection import get_affection_response

        response = await get_affection_response(RANK_NOTE_SCENE, group_id, user_id)
        return (response.text or "").strip()
    except Exception as error:
        logger.debug(f"[msg-rank-card] 读取馒头短评失败: {error}")
        return ""


async def generate_rank_card(
    rank_data: list[dict], period: str = "daily", group_id: str | None = None
) -> bytes:
    avatars = await asyncio.gather(*(download_avatar(info["user_id"]) for info in rank_data))
    affections = await asyncio.gather(
        *(_get_affection_display(group_id, str(info["user_id"])) for info in rank_data)
    )
    members = [
        MemberInfo(
            name=info["name"],
            msg_count=info["msg_count"],
            time_seconds=info["time_seconds"],
            head_pic=avatar,
            affection=affection.affection if affection else None,
            affection_title=affection.title if affection else "",
            affection_note=affection.note if affection else "",
        )
        for info, avatar, affection in zip(rank_data, avatars, affections)
    ]
    generator = RankCardGenerator()
    title = get_plugin_config().msg_rank_title if period == "daily" else PERIOD_TITLES[period]
    return await asyncio.to_thread(generator.generate_card_bytes, members, title)
