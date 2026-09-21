
from pydantic import BaseModel


class Config(BaseModel):
    """插件配置"""

    # 数据存储路径
    msg_rank_data_path: str = "data/msg_rank"
    # 资源文件路径
    msg_rank_resource_path: str = ""
    # 每日排行榜最大显示人数
    msg_rank_max_count: int = 10
    # 是否自动清理过期数据
    msg_rank_auto_clean: bool = True
    # 数据保留天数，需要覆盖完整月榜
    msg_rank_data_retention_days: int = 35
    # 排行榜标题
    msg_rank_title: str = "今日水群排行榜"
