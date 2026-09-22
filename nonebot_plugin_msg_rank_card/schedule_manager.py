import asyncio
import json
from datetime import datetime
from typing import Any, Optional

from nonebot import get_bot, get_bots, get_driver
from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler

from .data_source import clean_old_data, get_data_dir
from .rank_service import generate_rank_card, get_broadcast_text, get_rank_for_period

_SCHEDULE_FILE = "rank-schedules.json"
_JOB_PREFIX = "msg-rank-card"
_SCHEDULE_FIELDS = {
    "daily": "daily_interval_hours",
    "weekly": "weekly_time",
    "monthly": "monthly_time",
}


def normalize_clock(value: str) -> str:
    """校验并规范化 HH:MM 时间"""
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as e:
        raise ValueError("时间格式应为 HH:MM，例如 20:30") from e
    return parsed.strftime("%H:%M")


def _settings_path():
    return get_data_dir() / _SCHEDULE_FILE


def load_schedule_settings() -> dict[str, dict[str, Any]]:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("定时任务配置格式错误")
        return {
            str(group_id): settings
            for group_id, settings in data.items()
            if isinstance(settings, dict)
        }
    except Exception as e:
        logger.warning(f"加载排行榜定时配置失败: {e}")
        return {}


def _save_schedule_settings(settings: dict[str, dict[str, Any]]):
    path = _settings_path()
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    temp_path.replace(path)


def get_group_schedule(group_id: str) -> dict[str, Any]:
    return load_schedule_settings().get(group_id, {})


def get_schedule_value(group_id: str, period: str) -> Optional[Any]:
    field = _SCHEDULE_FIELDS[period]
    return get_group_schedule(group_id).get(field)


def _job_id(group_id: str, period: str) -> str:
    return f"{_JOB_PREFIX}:{group_id}:{period}"


def _remove_job(group_id: str, period: str):
    job = scheduler.get_job(_job_id(group_id, period))
    if job:
        scheduler.remove_job(job.id)


def _add_job(group_id: str, period: str, value: Any, bot_id: str):
    common = {
        "id": _job_id(group_id, period),
        "kwargs": {"group_id": group_id, "period": period, "bot_id": bot_id},
        "replace_existing": True,
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 300,
    }
    if period == "daily":
        scheduler.add_job(_run_scheduled_rank, "interval", hours=int(value), **common)
        return

    hour, minute = (int(part) for part in str(value).split(":"))
    scheduler.add_job(_run_scheduled_rank, "cron", hour=hour, minute=minute, **common)


def configure_group_schedule(
    group_id: str,
    period: str,
    value: Optional[Any],
    bot_id: str,
):
    """保存并立即应用指定群的定时任务。"""
    field = _SCHEDULE_FIELDS[period]
    all_settings = load_schedule_settings()
    group_settings = all_settings.setdefault(group_id, {})

    if value is None:
        group_settings.pop(field, None)
    else:
        group_settings[field] = value
        group_settings["bot_id"] = bot_id

    if not any(name in group_settings for name in _SCHEDULE_FIELDS.values()):
        all_settings.pop(group_id, None)

    _save_schedule_settings(all_settings)
    _remove_job(group_id, period)
    if value is not None:
        _add_job(group_id, period, value, bot_id)


def _find_bot(bot_id: str) -> Optional[OneBotV11Bot]:
    try:
        bot = get_bot(bot_id)
        if isinstance(bot, OneBotV11Bot):
            return bot
    except Exception:
        pass

    return next(
        (bot for bot in get_bots().values() if isinstance(bot, OneBotV11Bot)),
        None,
    )


async def _run_scheduled_rank(group_id: str, period: str, bot_id: str):
    bot = _find_bot(bot_id)
    if bot is None:
        logger.warning(f"排行榜定时发送跳过：未找到 OneBot V11 机器人，群 {group_id}")
        return

    try:
        rank_data = get_rank_for_period(group_id, period)
        if not rank_data:
            logger.info(f"排行榜定时发送跳过：群 {group_id} 暂无数据")
            return
        image_bytes = await generate_rank_card(rank_data, period, group_id)
        await bot.send_group_msg(
            group_id=int(group_id),
            message=get_broadcast_text(period),
        )
        await bot.send_group_msg(
            group_id=int(group_id),
            message=MessageSegment.image(image_bytes),
        )
    except Exception as e:
        logger.error(f"排行榜定时发送失败，群 {group_id}: {e}")


async def _run_cleanup():
    await asyncio.to_thread(clean_old_data)


def restore_schedule_jobs():
    for group_id, settings in load_schedule_settings().items():
        bot_id = str(settings.get("bot_id", ""))
        for period, field in _SCHEDULE_FIELDS.items():
            value = settings.get(field)
            if value is None:
                continue
            try:
                _add_job(group_id, period, value, bot_id)
            except Exception as e:
                logger.warning(f"恢复排行榜定时任务失败，群 {group_id}: {e}")

    scheduler.add_job(
        _run_cleanup,
        "cron",
        hour=3,
        minute=30,
        id=f"{_JOB_PREFIX}:cleanup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


@get_driver().on_startup
async def _restore_schedule_jobs_on_startup():
    restore_schedule_jobs()
