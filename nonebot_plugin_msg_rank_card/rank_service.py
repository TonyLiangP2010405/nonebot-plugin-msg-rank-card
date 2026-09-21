import asyncio

from nonebot import get_driver

from .card_generator import MemberInfo, RankCardGenerator, download_avatar
from .config import Config
from .data_source import get_period_rank_data

PERIOD_TITLES = {
    "daily": "今日水群排行榜",
    "weekly": "本周水群排行榜",
    "monthly": "本月水群排行榜",
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


async def generate_rank_card(rank_data: list[dict], period: str = "daily") -> bytes:
    avatars = await asyncio.gather(*(download_avatar(info["user_id"]) for info in rank_data))
    members = [
        MemberInfo(
            name=info["name"],
            msg_count=info["msg_count"],
            time_seconds=info["time_seconds"],
            head_pic=avatar,
        )
        for info, avatar in zip(rank_data, avatars)
    ]
    generator = RankCardGenerator()
    title = get_plugin_config().msg_rank_title if period == "daily" else PERIOD_TITLES[period]
    return await asyncio.to_thread(generator.generate_card_bytes, members, title)
