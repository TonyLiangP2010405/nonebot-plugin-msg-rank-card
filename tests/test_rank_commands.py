import asyncio
import sys
from contextlib import suppress
from types import ModuleType, SimpleNamespace

import pytest
from nonebot.adapters.onebot.v11 import Message
from nonebot.exception import FinishedException

import nonebot_plugin_msg_rank_card as plugin
from nonebot_plugin_msg_rank_card import rank_service, schedule_manager


class FakeMatcher:
    """记录发送顺序的假 matcher，finish 抛出与 NoneBot 一致的结束异常"""

    def __init__(self, timeline):
        self.sent = []
        self.finished = False
        self._timeline = timeline

    async def send(self, message, **kwargs):
        self.sent.append(message)
        self._timeline.append(("send", message))

    async def finish(self, message=None, **kwargs):
        if message is not None:
            await self.send(message, **kwargs)
        self.finished = True
        raise FinishedException


def sample_rank_data():
    return [
        {"user_id": "1", "name": "浅夏柚子", "msg_count": 128, "time_seconds": 3661},
        {"user_id": "2", "name": "阿岚", "msg_count": 96, "time_seconds": 1800},
    ]


def make_event(*, user_id=9, group_id=10001, card="", nickname="阿岚"):
    return SimpleNamespace(
        user_id=user_id,
        group_id=group_id,
        sender=SimpleNamespace(card=card, nickname=nickname),
    )


async def fake_generate_card(rank_data, period, group_id):
    return b"image-bytes"


def run_handler(coro):
    with suppress(FinishedException):
        asyncio.run(coro)


def install_bet_stub(monkeypatch, timeline, *, result=True, error=None, with_api=True):
    """注入假的馒头博弈接口，返回调用记录"""
    module = ModuleType("nonebot_plugin_mantou_affection")
    calls = []

    if with_api:

        async def maybe_start_bet(group_id, user_id, *, nickname="", candidates=None, send=None):
            calls.append(
                {
                    "group_id": group_id,
                    "user_id": user_id,
                    "nickname": nickname,
                    "candidates": candidates,
                    "send": send,
                }
            )
            timeline.append("bet")
            if error is not None:
                raise error
            return result

        module.maybe_start_bet = maybe_start_bet

    monkeypatch.setitem(sys.modules, "nonebot_plugin_mantou_affection", module)
    monkeypatch.setattr(rank_service, "get_plugin_by_module_name", lambda name: module)
    return calls


def prepare_rank_command(monkeypatch, timeline, matcher_name, *, rank_data=None):
    entries = sample_rank_data() if rank_data is None else rank_data
    matcher = FakeMatcher(timeline)
    monkeypatch.setattr(plugin, matcher_name, matcher)
    monkeypatch.setattr(plugin, "get_rank_for_period", lambda group_id, period: entries)
    monkeypatch.setattr(plugin, "generate_rank_card", fake_generate_card)
    return matcher


@pytest.mark.parametrize(
    ("matcher_name", "broadcast", "trigger"),
    [
        pytest.param(
            "rank_cmd",
            "正在放送日报。。。",
            lambda event: plugin.handle_rank(None, event, Message()),
            id="daily",
        ),
        pytest.param(
            "weekly_rank_cmd",
            "正在放送周报。。。",
            lambda event: plugin.handle_weekly_rank(event),
            id="weekly",
        ),
        pytest.param(
            "monthly_rank_cmd",
            "正在放送月报。。。",
            lambda event: plugin.handle_monthly_rank(event),
            id="monthly",
        ),
    ],
)
def test_rank_command_starts_bet_after_card(monkeypatch, matcher_name, broadcast, trigger):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    matcher = prepare_rank_command(monkeypatch, timeline, matcher_name)

    run_handler(trigger(make_event(card="浅夏柚子", nickname="阿岚")))

    broadcast_message = matcher.sent[0]
    text = broadcast_message if isinstance(broadcast_message, str) else broadcast_message[0].data["text"]
    assert text == broadcast
    assert matcher.sent[1].type == "image"
    assert matcher.finished is True
    assert timeline == [("send", matcher.sent[0]), ("send", matcher.sent[1]), "bet"]

    assert calls == [
        {
            "group_id": "10001",
            "user_id": "9",
            "nickname": "浅夏柚子",
            "candidates": [("1", "浅夏柚子"), ("2", "阿岚")],
            "send": matcher.send,
        }
    ]


@pytest.mark.parametrize(
    ("card", "nickname", "expected"),
    [("浅夏柚子", "阿岚", "浅夏柚子"), ("", "阿岚", "阿岚"), ("", "", "9")],
)
def test_bet_nickname_falls_back_to_sender_fields(monkeypatch, card, nickname, expected):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    prepare_rank_command(monkeypatch, timeline, "rank_cmd")

    run_handler(plugin.handle_rank(None, make_event(card=card, nickname=nickname), Message()))

    assert [call["nickname"] for call in calls] == [expected]


def test_rank_command_survives_missing_mantou_plugin(monkeypatch):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    monkeypatch.setattr(rank_service, "get_plugin_by_module_name", lambda name: None)
    matcher = prepare_rank_command(monkeypatch, timeline, "rank_cmd")

    run_handler(plugin.handle_rank(None, make_event(), Message()))

    assert calls == []
    assert matcher.finished is True
    assert len(matcher.sent) == 2


def test_rank_command_survives_plugin_without_bet_api(monkeypatch):
    timeline = []
    install_bet_stub(monkeypatch, timeline, with_api=False)
    matcher = prepare_rank_command(monkeypatch, timeline, "rank_cmd")

    run_handler(plugin.handle_rank(None, make_event(), Message()))

    assert timeline == [("send", matcher.sent[0]), ("send", matcher.sent[1])]
    assert matcher.finished is True


def test_rank_command_survives_bet_errors(monkeypatch):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline, error=RuntimeError("博弈服务不可用"))
    matcher = prepare_rank_command(monkeypatch, timeline, "rank_cmd")

    run_handler(plugin.handle_rank(None, make_event(), Message()))

    assert len(calls) == 1
    assert matcher.finished is True
    assert len(matcher.sent) == 2


def test_no_bet_when_rank_is_empty(monkeypatch):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    matcher = prepare_rank_command(monkeypatch, timeline, "rank_cmd", rank_data=[])

    run_handler(plugin.handle_rank(None, make_event(), Message()))

    assert calls == []
    assert matcher.sent == ["今天还没有人水群呢~"]


def test_scheduled_broadcast_does_not_start_bet(monkeypatch):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)

    class FakeBot:
        async def send_group_msg(self, **kwargs):
            pass

    monkeypatch.setattr(schedule_manager, "_find_bot", lambda bot_id: FakeBot())
    monkeypatch.setattr(schedule_manager, "get_rank_for_period", lambda group_id, period: sample_rank_data())
    monkeypatch.setattr(schedule_manager, "generate_rank_card", fake_generate_card)

    asyncio.run(schedule_manager._run_scheduled_rank("10001", "daily", "999"))

    assert calls == []
    assert timeline == []
