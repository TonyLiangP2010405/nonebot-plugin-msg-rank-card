import asyncio

from nonebot import on_command, on_message
from nonebot.adapters import Bot, Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .card_generator import MemberInfo, RankCardGenerator, download_avatar
from .config import Config
from .data_source import (
    clean_old_data,
    get_rank_data,
    is_rank_change_notify_enabled,
    record_message,
    record_message_and_check_rank_change,
    set_rank_change_notify,
)

__plugin_meta__ = PluginMetadata(
    name="每日水群排行榜",
    description="记录群聊消息，生成精美的每日水群排行榜图片",
    usage=(
        "发送 /水群榜 或 /msgrank 查看今日排行榜；"
        "Superuser 可使用 /排名变动提醒 开启|关闭|状态"
    ),
    type="application",
    homepage="https://github.com/TonyLiangP2010405/nonebot-plugin-msg-rank-card",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

# 消息监听：记录群聊消息
msg_handler = on_message(priority=99, block=False)

# 排行榜命令
rank_cmd = on_command("水群榜", aliases={"msgrank", "msg_rank", "今日水群榜"}, priority=10, block=True)

# 清理命令
clean_cmd = on_command("清理水群数据", aliases={"clean_msgrank"}, priority=10, block=True)

# 排名变动提醒开关（仅 Superuser 可用）
rank_change_cmd = on_command(
    "排名变动提醒",
    aliases={"水群榜变动提醒", "rank_change_notify"},
    permission=SUPERUSER,
    priority=10,
    block=True,
)


def _get_max_count(bot: Bot) -> int:
    try:
        driver_config = bot.config
        if hasattr(driver_config, "model_dump"):
            config = Config.model_validate(driver_config.model_dump())
        else:
            config = Config.parse_obj(driver_config.dict())
        return max(1, min(config.msg_rank_max_count, 10))
    except Exception:
        return 10


async def _generate_rank_card(rank_data: list[dict]) -> bytes:
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
    return await asyncio.to_thread(generator.generate_card_bytes, members)


@msg_handler.handle()
async def handle_message(bot: Bot, event: GroupMessageEvent):
    group_id = str(event.group_id)
    user_id = str(event.user_id)
    user_name = event.sender.nickname or "未知用户"

    max_count = _get_max_count(bot)
    notify_enabled = is_rank_change_notify_enabled(group_id)

    try:
        if notify_enabled:
            rank_changed = record_message_and_check_rank_change(
                group_id,
                user_id,
                user_name,
                msg_length=1,
                max_count=max_count,
            )
        else:
            record_message(group_id, user_id, user_name, msg_length=1)
            rank_changed = False
    except Exception as e:
        logger.warning(f"记录消息失败: {e}")
        return

    if not rank_changed:
        return

    try:
        rank_data = get_rank_data(group_id, max_count=max_count)
        image_bytes = await _generate_rank_card(rank_data)
        await bot.send(event, "当前检测到排名变化，重新发送最新榜单：")
        await bot.send(event, MessageSegment.image(image_bytes))
    except Exception as e:
        logger.error(f"发送排名变动提醒失败: {e}")


@rank_cmd.handle()
async def handle_rank(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = str(event.group_id)
    max_count = _get_max_count(bot)
    rank_data = get_rank_data(group_id, max_count=max_count)

    if not rank_data:
        await rank_cmd.finish("今天还没有人水群呢~")
        return

    try:
        image_bytes = await _generate_rank_card(rank_data)
    except Exception as e:
        logger.error(f"生成排行榜图片失败: {e}")
        await rank_cmd.finish("生成排行榜图片失败了，请稍后再试~")
        return

    await rank_cmd.finish(MessageSegment.image(image_bytes))


@clean_cmd.handle()
async def handle_clean(bot: Bot, event: GroupMessageEvent):
    clean_old_data()
    await clean_cmd.finish("已清理过期数据~")


@rank_change_cmd.handle()
async def handle_rank_change(event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = str(event.group_id)
    action = args.extract_plain_text().strip().lower()

    if action in {"", "状态", "status"}:
        status = "已开启" if is_rank_change_notify_enabled(group_id) else "已关闭"
        await rank_change_cmd.finish(f"本群排名变动提醒{status}。")

    if action in {"开启", "打开", "on", "enable"}:
        enabled = True
    elif action in {"关闭", "关掉", "off", "disable"}:
        enabled = False
    else:
        await rank_change_cmd.finish("用法：/排名变动提醒 开启|关闭|状态")
        return

    try:
        set_rank_change_notify(group_id, enabled)
    except Exception as e:
        logger.error(f"保存排名变动提醒开关失败: {e}")
        await rank_change_cmd.finish("保存开关状态失败，请检查数据目录权限。")
        return

    status = "开启" if enabled else "关闭"
    await rank_change_cmd.finish(f"已{status}本群排名变动提醒。")
