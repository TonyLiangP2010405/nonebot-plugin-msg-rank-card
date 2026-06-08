import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from nonebot import get_driver
from nonebot.log import logger

from .config import Config

_data_dir: Path = Path("data/msg_rank")
_data_dir_initialized = False


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


def get_group_data_file(group_id: str) -> Path:
    """获取群数据文件路径"""
    return _get_data_dir() / f"{group_id}_{get_today_str()}.json"


def load_group_data(group_id: str) -> dict:
    """加载群数据"""
    file_path = get_group_data_file(group_id)
    if file_path.exists():
        try:
            with open(file_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"加载群数据失败: {e}")
    return {}


def save_group_data(group_id: str, data: dict):
    """保存群数据"""
    file_path = get_group_data_file(group_id)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"保存群数据失败: {e}")


def record_message(group_id: str, user_id: str, user_name: str, msg_length: int = 1):
    """记录一条消息"""
    data = load_group_data(group_id)

    if user_id not in data:
        data[user_id] = {
            "name": user_name,
            "msg_count": 0,
            "time_seconds": 0,
            "last_msg_time": 0,
        }

    # 更新消息数
    data[user_id]["msg_count"] += msg_length

    # 计算在线时长（简单估算：如果距离上次消息在5分钟内，累加时间差）
    now = int(time.time())
    last_time = data[user_id].get("last_msg_time", 0)
    if last_time > 0 and now - last_time < 300:  # 5分钟内
        data[user_id]["time_seconds"] += now - last_time

    data[user_id]["last_msg_time"] = now
    data[user_id]["name"] = user_name  # 更新昵称

    save_group_data(group_id, data)


def get_rank_data(group_id: str, max_count: int = 10) -> list[dict]:
    """获取排行榜数据，按消息数排序"""
    data = load_group_data(group_id)

    rank_list = []
    for user_id, info in data.items():
        rank_list.append({
            "user_id": user_id,
            "name": info.get("name", "未知用户"),
            "msg_count": info.get("msg_count", 0),
            "time_seconds": info.get("time_seconds", 0),
        })

    # 按消息数降序排序
    rank_list.sort(key=lambda x: x["msg_count"], reverse=True)

    return rank_list[:max_count]


def clean_old_data(days: int = 7):
    try:
        if not _get_config().msg_rank_auto_clean:
            return
    except Exception:
        pass

    data_dir = _get_data_dir()
    cutoff = datetime.now() - timedelta(days=days)
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
