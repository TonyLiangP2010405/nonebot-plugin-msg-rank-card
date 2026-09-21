import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from nonebot import get_driver
from nonebot.log import logger

from .config import Config

_data_dir: Path = Path("data/msg_rank")
_data_dir_initialized = False
_rank_change_settings_file = "rank-change-notify.json"


def _get_config() -> Config:
    try:
        driver_config = get_driver().config
        if hasattr(driver_config, "model_dump"):
            return Config.model_validate(driver_config.model_dump())
        return Config.parse_obj(driver_config.dict())
    except Exception:
        return Config()


def _get_data_dir() -> Path:
    global _data_dir, _data_dir_initialized
    if not _data_dir_initialized:
        _data_dir = Path(_get_config().msg_rank_data_path)
        _data_dir.mkdir(parents=True, exist_ok=True)
        _data_dir_initialized = True
    return _data_dir


def get_today_str() -> str:
    """获取今天的日期字符串"""
    return datetime.now().strftime("%Y%m%d")


def get_data_dir() -> Path:
    """获取已初始化的数据目录"""
    return _get_data_dir()


def get_group_data_file(group_id: str, day: Optional[date] = None) -> Path:
    """获取群数据文件路径"""
    date_str = day.strftime("%Y%m%d") if day else get_today_str()
    return _get_data_dir() / f"{group_id}_{date_str}.json"


def _load_data_file(file_path: Path) -> dict:
    if file_path.exists():
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"加载群数据失败 {file_path.name}: {e}")
    return {}


def load_group_data(group_id: str) -> dict:
    """加载群数据"""
    return _load_data_file(get_group_data_file(group_id))


def save_group_data(group_id: str, data: dict):
    """保存群数据"""
    file_path = get_group_data_file(group_id)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"保存群数据失败: {e}")


def _update_message_data(data: dict[str, Any], user_id: str, user_name: str, msg_length: int):
    """更新一条成员消息数据"""
    if user_id not in data:
        data[user_id] = {
            "name": user_name,
            "msg_count": 0,
            "time_seconds": 0,
            "last_msg_time": 0,
        }

    data[user_id]["msg_count"] += msg_length

    # 如果两次发言相隔不超过5分钟，将间隔累加为在线时长。
    now = int(time.time())
    last_time = data[user_id].get("last_msg_time", 0)
    if last_time > 0 and now - last_time < 300:
        data[user_id]["time_seconds"] += now - last_time

    data[user_id]["last_msg_time"] = now
    data[user_id]["name"] = user_name


def _build_rank_data(data: dict[str, Any], max_count: int) -> list[dict]:
    """将群消息数据整理为排行榜"""
    rank_list = [
        {
            "user_id": user_id,
            "name": info.get("name", "未知用户"),
            "msg_count": info.get("msg_count", 0),
            "time_seconds": info.get("time_seconds", 0),
        }
        for user_id, info in data.items()
    ]
    rank_list.sort(key=lambda x: x["msg_count"], reverse=True)
    return rank_list[:max_count]


def record_message(group_id: str, user_id: str, user_name: str, msg_length: int = 1):
    """记录一条消息"""
    data = load_group_data(group_id)
    _update_message_data(data, user_id, user_name, msg_length)
    save_group_data(group_id, data)


def record_message_and_check_rank_change(
    group_id: str,
    user_id: str,
    user_name: str,
    msg_length: int = 1,
    max_count: int = 10,
) -> bool:
    """记录消息，并判断排行榜成员顺序是否发生变化。

    第一条消息只初始化榜单，不视为排名变动。
    """
    data = load_group_data(group_id)
    before = [item["user_id"] for item in _build_rank_data(data, max_count)]
    _update_message_data(data, user_id, user_name, msg_length)
    after = [item["user_id"] for item in _build_rank_data(data, max_count)]
    save_group_data(group_id, data)
    return bool(before) and before != after


def get_rank_data(group_id: str, max_count: int = 10) -> list[dict]:
    """获取排行榜数据，按消息数排序"""
    return _build_rank_data(load_group_data(group_id), max_count)


def get_period_rank_data(
    group_id: str,
    period: str,
    max_count: int = 10,
    current_day: Optional[date] = None,
) -> list[dict]:
    """获取今日、本周或本月的汇总排行榜。"""
    today = current_day or datetime.now().date()
    if period == "daily":
        start_day = today
    elif period == "weekly":
        start_day = today - timedelta(days=today.weekday())
    elif period == "monthly":
        start_day = today.replace(day=1)
    else:
        raise ValueError(f"不支持的排行榜周期: {period}")

    aggregated: dict[str, dict[str, Any]] = {}
    day = start_day
    while day <= today:
        daily_data = _load_data_file(get_group_data_file(group_id, day))
        for user_id, info in daily_data.items():
            member = aggregated.setdefault(
                user_id,
                {"name": "未知用户", "msg_count": 0, "time_seconds": 0},
            )
            member["name"] = info.get("name", member["name"])
            member["msg_count"] += info.get("msg_count", 0)
            member["time_seconds"] += info.get("time_seconds", 0)
        day += timedelta(days=1)

    return _build_rank_data(aggregated, max_count)


def _load_rank_change_settings() -> dict[str, bool]:
    settings_path = _get_data_dir() / _rank_change_settings_file
    if not settings_path.exists():
        return {}
    try:
        with open(settings_path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("排名变动提醒配置格式错误")
        return {str(group_id): bool(enabled) for group_id, enabled in data.items()}
    except Exception as e:
        logger.warning(f"加载排名变动提醒配置失败: {e}")
        return {}


def is_rank_change_notify_enabled(group_id: str) -> bool:
    """查询指定群是否已开启排名变动提醒"""
    return _load_rank_change_settings().get(group_id, False)


def set_rank_change_notify(group_id: str, enabled: bool):
    """持久化指定群的排名变动提醒开关"""
    settings = _load_rank_change_settings()
    if enabled:
        settings[group_id] = True
    else:
        settings.pop(group_id, None)

    settings_path = _get_data_dir() / _rank_change_settings_file
    temp_path = settings_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    temp_path.replace(settings_path)


def clean_old_data(days: Optional[int] = None):
    try:
        config = _get_config()
        if not config.msg_rank_auto_clean:
            return
        retention_days = days if days is not None else max(31, config.msg_rank_data_retention_days)
    except Exception:
        retention_days = days if days is not None else 35

    data_dir = _get_data_dir()
    cutoff = datetime.now() - timedelta(days=retention_days)
    cutoff_str = cutoff.strftime("%Y%m%d")

    for file_path in data_dir.glob("*_*.json"):
        try:
            # 文件名格式: {group_id}_{date}.json
            date_str = file_path.stem.split("_")[-1]
            if date_str < cutoff_str:
                file_path.unlink()
                logger.info(f"清理过期数据: {file_path.name}")
        except Exception:
            pass
