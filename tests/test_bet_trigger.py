import asyncio
import sys
import time
from contextlib import suppress
from types import ModuleType, SimpleNamespace

import pytest
from nonebot.adapters.onebot.v11 import Message
from nonebot.exception import FinishedException

import nonebot_plugin_msg_rank_card as plugin
from nonebot_plugin_msg_rank_card import data_source, rank_service, schedule_manager


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


class DummyBot:
    async def send(self, *args, **kwargs):
        raise AssertionError("普通群消息不应触发排名变动提醒发送")


def sample_rank_data():
    return [
        {"user_id": "1", "name": "浅夏柚子", "msg_count": 128, "time_seconds": 3661},
        {"user_id": "2", "name": "阿岚", "msg_count": 96, "time_seconds": 1800},
    ]


def make_event(*, user_id=1, group_id=10001, card="", nickname="阿岚"):
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


def prepare_message_path(monkeypatch, tmp_path, timeline, *, rank_data=None):
    """让群消息链路使用临时数据目录，并由假 matcher 接管 msg_handler"""
    monkeypatch.setattr(data_source, "_data_dir", tmp_path)
    monkeypatch.setattr(data_source, "_data_dir_initialized", True)
    monkeypatch.setattr(rank_service, "_daily_rank_cache", {})
    monkeypatch.setattr(rank_service, "_recent_speakers", {})
    monkeypatch.setattr(plugin, "is_rank_change_notify_enabled", lambda group_id: False)
    entries = sample_rank_data() if rank_data is None else rank_data
    monkeypatch.setattr(rank_service, "get_rank_for_period", lambda group_id, period: entries)
    matcher = FakeMatcher(timeline)
    monkeypatch.setattr(plugin, "msg_handler", matcher)
    return matcher


def make_stale_speaker(user_id, *, group_id="10001"):
    """把成员的最近发言时间改到窗口之外"""
    window = rank_service.get_bet_recent_minutes()
    rank_service._recent_speakers[(group_id, user_id)] = time.monotonic() - window * 60 - 1


def prepare_rank_command(monkeypatch, timeline, matcher_name):
    matcher = FakeMatcher(timeline)
    monkeypatch.setattr(plugin, matcher_name, matcher)
    monkeypatch.setattr(plugin, "get_rank_for_period", lambda group_id, period: sample_rank_data())
    monkeypatch.setattr(plugin, "generate_rank_card", fake_generate_card)
    return matcher


def test_ranked_member_message_starts_bet(monkeypatch, tmp_path):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    matcher = prepare_message_path(monkeypatch, tmp_path, timeline)

    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1, card="浅夏柚子")))

    assert calls == [
        {
            "group_id": "10001",
            "user_id": "1",
            "nickname": "浅夏柚子",
            "candidates": [("1", "浅夏柚子")],
            "send": matcher.send,
        }
    ]
    assert timeline == ["bet"]
    assert [(item["user_id"], item["msg_count"]) for item in data_source.get_rank_data("10001")] == [("1", 1)]


def test_recent_speakers_are_passed_as_candidates(monkeypatch, tmp_path):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    prepare_message_path(monkeypatch, tmp_path, timeline)

    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=2)))
    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1)))

    assert [call["candidates"] for call in calls] == [
        [("2", "阿岚")],
        [("1", "浅夏柚子"), ("2", "阿岚")],
    ]


def test_stale_speaker_is_filtered_from_candidates(monkeypatch, tmp_path):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    prepare_message_path(monkeypatch, tmp_path, timeline)

    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=2)))
    make_stale_speaker("2")
    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1)))

    assert [call["candidates"] for call in calls] == [
        [("2", "阿岚")],
        [("1", "浅夏柚子")],
    ]


def test_unranked_member_message_does_not_start_bet(monkeypatch, tmp_path):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    prepare_message_path(monkeypatch, tmp_path, timeline)

    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=9)))

    assert calls == []
    assert timeline == []
    assert [(item["user_id"], item["msg_count"]) for item in data_source.get_rank_data("10001")] == [("9", 1)]


@pytest.mark.parametrize(
    ("card", "nickname", "expected"),
    [("浅夏柚子", "阿岚", "浅夏柚子"), ("", "阿岚", "阿岚"), ("", "", "1")],
)
def test_bet_nickname_falls_back_to_sender_fields(monkeypatch, tmp_path, card, nickname, expected):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    prepare_message_path(monkeypatch, tmp_path, timeline)

    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1, card=card, nickname=nickname)))

    assert [call["nickname"] for call in calls] == [expected]


def test_message_survives_missing_mantou_plugin(monkeypatch, tmp_path):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    monkeypatch.setattr(rank_service, "get_plugin_by_module_name", lambda name: None)
    prepare_message_path(monkeypatch, tmp_path, timeline)

    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1)))

    assert calls == []
    assert timeline == []
    assert [(item["user_id"], item["msg_count"]) for item in data_source.get_rank_data("10001")] == [("1", 1)]


def test_message_survives_plugin_without_bet_api(monkeypatch, tmp_path):
    timeline = []
    install_bet_stub(monkeypatch, timeline, with_api=False)
    prepare_message_path(monkeypatch, tmp_path, timeline)

    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1)))

    assert timeline == []
    assert [(item["user_id"], item["msg_count"]) for item in data_source.get_rank_data("10001")] == [("1", 1)]


def test_message_survives_bet_errors(monkeypatch, tmp_path):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline, error=RuntimeError("博弈服务不可用"))
    prepare_message_path(monkeypatch, tmp_path, timeline)

    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1)))

    assert len(calls) == 1
    assert [(item["user_id"], item["msg_count"]) for item in data_source.get_rank_data("10001")] == [("1", 1)]


def test_daily_rank_lookup_is_cached_per_group(monkeypatch, tmp_path):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    prepare_message_path(monkeypatch, tmp_path, timeline)
    queries = []

    def counting_query(group_id, period):
        queries.append((group_id, period))
        return sample_rank_data()

    monkeypatch.setattr(rank_service, "get_rank_for_period", counting_query)

    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1)))
    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1)))
    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1, group_id=20002)))

    assert queries == [("10001", "daily"), ("20002", "daily")]
    assert len(calls) == 3

    timestamp, cached = rank_service._daily_rank_cache["10001"]
    rank_service._daily_rank_cache["10001"] = (
        timestamp - rank_service.DAILY_RANK_CACHE_SECONDS - 1,
        cached,
    )
    run_handler(plugin.handle_message(DummyBot(), make_event(user_id=1)))

    assert queries == [("10001", "daily"), ("20002", "daily"), ("10001", "daily")]


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
def test_rank_command_does_not_start_bet(monkeypatch, matcher_name, broadcast, trigger):
    timeline = []
    calls = install_bet_stub(monkeypatch, timeline)
    matcher = prepare_rank_command(monkeypatch, timeline, matcher_name)

    run_handler(trigger(make_event(card="浅夏柚子")))

    broadcast_message = matcher.sent[0]
    text = broadcast_message if isinstance(broadcast_message, str) else broadcast_message[0].data["text"]
    assert text == broadcast
    assert matcher.sent[1].type == "image"
    assert matcher.finished is True
    assert calls == []
    assert timeline == [("send", matcher.sent[0]), ("send", matcher.sent[1])]


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
