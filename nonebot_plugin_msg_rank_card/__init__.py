from nonebot import on_command, on_message, require
from nonebot.adapters import Bot, Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .config import Config
from .data_source import (
    clean_old_data,
    is_rank_change_notify_enabled,
    record_message,
    record_message_and_check_rank_change,
    set_rank_change_notify,
)
from .rank_service import generate_rank_card, get_max_count, get_rank_for_period

require("nonebot_plugin_apscheduler")

from .schedule_manager import (  # noqa: E402
    configure_group_schedule,
    get_schedule_value,
    normalize_clock,
)

__plugin_meta__ = PluginMetadata(
    name="每日水群排行榜",
    description="记录群聊消息，生成精美的每日水群排行榜图片",
    usage=(
        "发送 /水群榜、/周水群榜或 /月水群榜查看排行榜；"
        "Superuser 可配置排名变动提醒与定时发送"
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
weekly_rank_cmd = on_command("周水群榜", aliases={"周榜", "weekrank"}, priority=10, block=True)
monthly_rank_cmd = on_command("月水群榜", aliases={"月榜", "monthrank"}, priority=10, block=True)

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

# 定时发送开关（仅 Superuser 可用）
daily_schedule_cmd = on_command("日榜定时", permission=SUPERUSER, priority=10, block=True)
weekly_schedule_cmd = on_command("周榜定时", permission=SUPERUSER, priority=10, block=True)
monthly_schedule_cmd = on_command("月榜定时", permission=SUPERUSER, priority=10, block=True)


@msg_handler.handle()
async def handle_message(bot: Bot, event: GroupMessageEvent):
    group_id = str(event.group_id)
    user_id = str(event.user_id)
    user_name = event.sender.nickname or "未知用户"

    max_count = get_max_count()
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
        rank_data = get_rank_for_period(group_id, "daily")
        image_bytes = await generate_rank_card(rank_data, "daily")
        await bot.send(event, "当前检测到排名变化，重新发送最新榜单：")
        await bot.send(event, MessageSegment.image(image_bytes))
    except Exception as e:
        logger.error(f"发送排名变动提醒失败: {e}")


@rank_cmd.handle()
async def handle_rank(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = str(event.group_id)
    rank_data = get_rank_for_period(group_id, "daily")

    if not rank_data:
        await rank_cmd.finish("今天还没有人水群呢~")
        return

    try:
        image_bytes = await generate_rank_card(rank_data, "daily")
    except Exception as e:
        logger.error(f"生成排行榜图片失败: {e}")
        await rank_cmd.finish("生成排行榜图片失败了，请稍后再试~")
        return

    await rank_cmd.finish(MessageSegment.image(image_bytes))


@weekly_rank_cmd.handle()
async def handle_weekly_rank(event: GroupMessageEvent):
    group_id = str(event.group_id)
    rank_data = get_rank_for_period(group_id, "weekly")
    if not rank_data:
        await weekly_rank_cmd.finish("本周还没有人水群呢~")
        return
    try:
        image_bytes = await generate_rank_card(rank_data, "weekly")
    except Exception as e:
        logger.error(f"生成周排行榜图片失败: {e}")
        await weekly_rank_cmd.finish("生成周排行榜图片失败了，请稍后再试~")
        return
    await weekly_rank_cmd.finish(MessageSegment.image(image_bytes))


@monthly_rank_cmd.handle()
async def handle_monthly_rank(event: GroupMessageEvent):
    group_id = str(event.group_id)
    rank_data = get_rank_for_period(group_id, "monthly")
    if not rank_data:
        await monthly_rank_cmd.finish("本月还没有人水群呢~")
        return
    try:
        image_bytes = await generate_rank_card(rank_data, "monthly")
    except Exception as e:
        logger.error(f"生成月排行榜图片失败: {e}")
        await monthly_rank_cmd.finish("生成月排行榜图片失败了，请稍后再试~")
        return
    await monthly_rank_cmd.finish(MessageSegment.image(image_bytes))


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


@daily_schedule_cmd.handle()
async def handle_daily_schedule(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    group_id = str(event.group_id)
    action = args.extract_plain_text().strip().lower()
    current = get_schedule_value(group_id, "daily")

    if action in {"", "状态", "status"}:
        status = f"每隔 {current} 小时发送" if current else "已关闭"
        await daily_schedule_cmd.finish(f"本群日榜定时{status}。")

    if action in {"关闭", "关掉", "off", "disable"}:
        try:
            configure_group_schedule(group_id, "daily", None, bot.self_id)
        except Exception as e:
            logger.error(f"关闭日榜定时任务失败: {e}")
            await daily_schedule_cmd.finish("保存定时任务失败，请检查数据目录权限。")
            return
        await daily_schedule_cmd.finish("已关闭本群日榜定时发送。")

    try:
        hours = int(action.removesuffix("小时"))
        if not 1 <= hours <= 168:
            raise ValueError
    except ValueError:
        await daily_schedule_cmd.finish("用法：/日榜定时 1-168|关闭|状态")
        return

    try:
        configure_group_schedule(group_id, "daily", hours, bot.self_id)
    except Exception as e:
        logger.error(f"设置日榜定时任务失败: {e}")
        await daily_schedule_cmd.finish("保存定时任务失败，请检查数据目录权限。")
        return
    await daily_schedule_cmd.finish(f"已设置本群每隔 {hours} 小时发送今日排行榜。")


async def _handle_clock_schedule(matcher, bot: Bot, event: GroupMessageEvent, args: Message, period: str):
    group_id = str(event.group_id)
    action = args.extract_plain_text().strip().lower()
    current = get_schedule_value(group_id, period)
    period_name = "周榜" if period == "weekly" else "月榜"

    if action in {"", "状态", "status"}:
        status = f"每天 {current} 发送" if current else "已关闭"
        await matcher.finish(f"本群{period_name}定时{status}。")

    if action in {"关闭", "关掉", "off", "disable"}:
        try:
            configure_group_schedule(group_id, period, None, bot.self_id)
        except Exception as e:
            logger.error(f"关闭{period_name}定时任务失败: {e}")
            await matcher.finish("保存定时任务失败，请检查数据目录权限。")
            return
        await matcher.finish(f"已关闭本群{period_name}定时发送。")

    try:
        clock = normalize_clock(action)
    except ValueError:
        await matcher.finish(f"用法：/{period_name}定时 HH:MM|关闭|状态")
        return

    try:
        configure_group_schedule(group_id, period, clock, bot.self_id)
    except Exception as e:
        logger.error(f"设置{period_name}定时任务失败: {e}")
        await matcher.finish("保存定时任务失败，请检查数据目录权限。")
        return
    await matcher.finish(f"已设置本群每天 {clock} 发送{period_name}。")


@weekly_schedule_cmd.handle()
async def handle_weekly_schedule(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    await _handle_clock_schedule(weekly_schedule_cmd, bot, event, args, "weekly")


@monthly_schedule_cmd.handle()
async def handle_monthly_schedule(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    await _handle_clock_schedule(monthly_schedule_cmd, bot, event, args, "monthly")
