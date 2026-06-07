from nonebot import on_command, on_message
from nonebot.adapters import Bot, Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from .card_generator import MemberInfo, RankCardGenerator, download_avatar
from .config import Config
from .data_source import clean_old_data, get_rank_data, record_message

__plugin_meta__ = PluginMetadata(
    name="每日水群排行榜",
    description="记录群聊消息，生成精美的每日水群排行榜图片",
    usage="发送 /水群榜 或 /msgrank 查看今日排行榜",
    type="application",
    homepage="https://github.com/TonyLiangP2010405/nonebot-plugin-msg-rank-card",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

# 消息监听：记录群聊消息
msg_handler = on_message(priority=99, block=False)

# 排行榜命令
rank_cmd = on_command("水群榜", aliases={"msgrank", "msg_rank", "今日水群榜"}, priority=10, block=True)

# 清理命令（仅管理员可用）
clean_cmd = on_command("清理水群数据", aliases={"clean_msgrank"}, priority=10, block=True)


@msg_handler.handle()
async def handle_message(bot: Bot, event: GroupMessageEvent):
    """记录群聊消息"""
    group_id = str(event.group_id)
    user_id = str(event.user_id)
    user_name = event.sender.nickname or "未知用户"

    # 记录消息
    record_message(group_id, user_id, user_name, msg_length=1)


@rank_cmd.handle()
async def handle_rank(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    """处理排行榜命令"""
    group_id = str(event.group_id)

    # 获取排行榜数据
    rank_data = get_rank_data(group_id)

    if not rank_data:
        await rank_cmd.finish("今天还没有人水群呢~")
        return

    # 构建成员信息列表
    members = []
    for info in rank_data:
        # 下载头像
        avatar = await download_avatar(info["user_id"])
        member = MemberInfo(
            name=info["name"],
            msg_count=info["msg_count"],
            time_seconds=info["time_seconds"],
            head_pic=avatar,
        )
        members.append(member)

    # 生成图片
    generator = RankCardGenerator()
    image_bytes = generator.generate_card_bytes(members)

    # 发送图片
    await rank_cmd.finish(MessageSegment.image(image_bytes))


@clean_cmd.handle()
async def handle_clean(bot: Bot, event: GroupMessageEvent):
    """清理过期数据"""
    # 简单权限检查：只有群主和管理员可以清理
    sender_role = event.sender.role if hasattr(event.sender, "role") else "member"
    if sender_role not in ["owner", "admin"]:
        await clean_cmd.finish("只有群主或管理员才能清理数据哦~")
        return

    clean_old_data()
    await clean_cmd.finish("已清理过期数据~")
