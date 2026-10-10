import asyncio
import sys
import time
from datetime import date
from types import ModuleType, SimpleNamespace

import pytest
from PIL import Image

from nonebot_plugin_msg_rank_card import rank_service
from nonebot_plugin_msg_rank_card.config import Config

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


async def fake_avatar(user_id):
    return Image.new("RGBA", (100, 100), (200, 60, 60, 255))


def sample_rank_data():
    return [
        {"user_id": "1", "name": "浅夏柚子", "msg_count": 128, "time_seconds": 3661},
        {"user_id": "2", "name": "阿岚", "msg_count": 96, "time_seconds": 1800},
    ]


def install_affection_stub(
    monkeypatch,
    *,
    affection=42,
    title="春心萌动",
    text="今天也很想见你呀",
    fail_response=False,
):
    """注入假的馒头好感度插件模块，并让软依赖检查通过"""
    module = ModuleType("nonebot_plugin_mantou_affection")
    scenes = []

    async def get_affection_snapshot(group_id, user_id):
        return SimpleNamespace(affection=affection, level=3, title=title, band="warm")

    async def get_affection_response(scene, group_id, user_id, *, seed=""):
        scenes.append(scene)
        if fail_response:
            raise RuntimeError("文案库不可用")
        return SimpleNamespace(affection=affection, level=3, title=title, band="warm", text=text)

    module.get_affection_snapshot = get_affection_snapshot
    module.get_affection_response = get_affection_response
    monkeypatch.setitem(sys.modules, "nonebot_plugin_mantou_affection", module)
    monkeypatch.setattr(rank_service, "get_plugin_by_module_name", lambda name: module)
    return scenes


def test_affection_display_is_skipped_without_plugin(monkeypatch):
    monkeypatch.setattr(rank_service, "get_plugin_by_module_name", lambda name: None)

    assert asyncio.run(rank_service._get_affection_display("10001", "1")) is None
    assert asyncio.run(rank_service._get_affection_display(None, "1")) is None


def test_affection_display_contains_rank_note(monkeypatch):
    scenes = install_affection_stub(monkeypatch)

    display = asyncio.run(rank_service._get_affection_display("10001", "1"))

    assert display.affection == 42
    assert display.title == "春心萌动"
    assert display.note == "今天也很想见你呀"
    assert scenes == ["msg_rank_card.rank"]


def test_missing_note_keeps_affection_display(monkeypatch):
    install_affection_stub(monkeypatch, text=None)

    display = asyncio.run(rank_service._get_affection_display("10001", "1"))

    assert (display.affection, display.title, display.note) == (42, "春心萌动", "")


def test_note_error_keeps_affection_display(monkeypatch):
    install_affection_stub(monkeypatch, fail_response=True)

    display = asyncio.run(rank_service._get_affection_display("10001", "1"))

    assert (display.affection, display.title, display.note) == (42, "春心萌动", "")


def test_old_affection_plugin_without_note_api(monkeypatch):
    module = ModuleType("nonebot_plugin_mantou_affection")

    async def get_affection_snapshot(group_id, user_id):
        return SimpleNamespace(affection=42, level=3, title="春心萌动", band="warm")

    module.get_affection_snapshot = get_affection_snapshot
    monkeypatch.setitem(sys.modules, "nonebot_plugin_mantou_affection", module)
    monkeypatch.setattr(rank_service, "get_plugin_by_module_name", lambda name: module)

    display = asyncio.run(rank_service._get_affection_display("10001", "1"))

    assert (display.affection, display.title, display.note) == (42, "春心萌动", "")


async def fake_send(message, **kwargs):
    return None


def install_bet_stub(monkeypatch, *, result=True, error=None, with_api=True):
    """注入假的馒头博弈接口，并让软依赖检查通过，返回调用记录"""
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
            if error is not None:
                raise error
            return result

        module.maybe_start_bet = maybe_start_bet

    monkeypatch.setitem(sys.modules, "nonebot_plugin_mantou_affection", module)
    monkeypatch.setattr(rank_service, "get_plugin_by_module_name", lambda name: module)
    return calls


def test_try_start_bet_passes_rank_candidates(monkeypatch):
    calls = install_bet_stub(monkeypatch)

    started = asyncio.run(
        rank_service.try_start_bet(
            "10001", "9", nickname="浅夏柚子", rank_data=sample_rank_data(), send=fake_send
        )
    )

    assert started is True
    assert calls == [
        {
            "group_id": "10001",
            "user_id": "9",
            "nickname": "浅夏柚子",
            "candidates": [("1", "浅夏柚子"), ("2", "阿岚")],
            "send": fake_send,
        }
    ]


def test_try_start_bet_returns_false_when_bet_is_declined(monkeypatch):
    calls = install_bet_stub(monkeypatch, result=False)

    started = asyncio.run(
        rank_service.try_start_bet("10001", "9", rank_data=sample_rank_data(), send=fake_send)
    )

    assert started is False
    assert len(calls) == 1


def test_try_start_bet_is_skipped_without_plugin(monkeypatch):
    calls = install_bet_stub(monkeypatch)
    monkeypatch.setattr(rank_service, "get_plugin_by_module_name", lambda name: None)

    started = asyncio.run(
        rank_service.try_start_bet("10001", "9", rank_data=sample_rank_data(), send=fake_send)
    )

    assert started is False
    assert calls == []


def test_try_start_bet_is_skipped_without_group_or_send(monkeypatch):
    calls = install_bet_stub(monkeypatch)

    assert (
        asyncio.run(rank_service.try_start_bet(None, "9", rank_data=sample_rank_data(), send=fake_send))
        is False
    )
    assert asyncio.run(rank_service.try_start_bet("10001", "9", rank_data=sample_rank_data())) is False
    assert calls == []


def test_try_start_bet_swallows_plugin_errors(monkeypatch):
    install_bet_stub(monkeypatch, error=RuntimeError("博弈服务不可用"))

    started = asyncio.run(
        rank_service.try_start_bet("10001", "9", rank_data=sample_rank_data(), send=fake_send)
    )

    assert started is False


def test_try_start_bet_is_skipped_when_plugin_has_no_bet_api(monkeypatch):
    calls = install_bet_stub(monkeypatch, with_api=False)

    started = asyncio.run(
        rank_service.try_start_bet("10001", "9", rank_data=sample_rank_data(), send=fake_send)
    )

    assert started is False
    assert calls == []


def test_member_daily_rank_returns_rank_data_on_rank(monkeypatch):
    monkeypatch.setattr(rank_service, "_daily_rank_cache", {})
    monkeypatch.setattr(rank_service, "get_rank_for_period", lambda group_id, period: sample_rank_data())

    rank_data = rank_service.get_member_daily_rank("10001", "2")

    assert [info["user_id"] for info in rank_data] == ["1", "2"]


def test_member_daily_rank_returns_none_off_rank(monkeypatch):
    monkeypatch.setattr(rank_service, "_daily_rank_cache", {})
    monkeypatch.setattr(rank_service, "get_rank_for_period", lambda group_id, period: sample_rank_data())

    assert rank_service.get_member_daily_rank("10001", "9") is None


def test_daily_rank_lookup_is_cached_per_group(monkeypatch):
    monkeypatch.setattr(rank_service, "_daily_rank_cache", {})
    queries = []

    def counting_query(group_id, period):
        queries.append((group_id, period))
        return sample_rank_data()

    monkeypatch.setattr(rank_service, "get_rank_for_period", counting_query)

    rank_service.get_cached_daily_rank("10001")
    rank_service.get_cached_daily_rank("10001")
    rank_service.get_cached_daily_rank("20002")

    assert queries == [("10001", "daily"), ("20002", "daily")]

    timestamp, cached = rank_service._daily_rank_cache["10001"]
    rank_service._daily_rank_cache["10001"] = (
        timestamp - rank_service.DAILY_RANK_CACHE_SECONDS - 1,
        cached,
    )
    rank_service.get_cached_daily_rank("10001")

    assert queries == [("10001", "daily"), ("20002", "daily"), ("10001", "daily")]


class FakeClock:
    """把 rank_service 的单调时钟固定下来，便于测试时间窗口边界"""

    def __init__(self, now):
        self.now = now

    def monotonic(self):
        return self.now


def test_bet_recent_minutes_defaults_to_five(monkeypatch):
    monkeypatch.setattr(rank_service, "get_plugin_config", lambda: Config())

    assert rank_service.get_bet_recent_minutes() == 5


@pytest.mark.parametrize(("configured", "expected"), [(0, 1), (1, 1), (60, 60), (240, 120)])
def test_bet_recent_minutes_is_clamped(monkeypatch, configured, expected):
    monkeypatch.setattr(
        rank_service, "get_plugin_config", lambda: Config(msg_rank_bet_recent_minutes=configured)
    )

    assert rank_service.get_bet_recent_minutes() == expected


def test_record_recent_speaker_marks_member_recent(monkeypatch):
    monkeypatch.setattr(rank_service, "_recent_speakers", {})

    rank_service.record_recent_speaker("10001", "1")

    assert [
        info["user_id"] for info in rank_service.filter_recent_members(sample_rank_data(), "10001", 5)
    ] == ["1"]
    assert rank_service.filter_recent_members(sample_rank_data(), "20002", 5) == []


def test_filter_recent_members_drops_stale_speakers(monkeypatch):
    monkeypatch.setattr(rank_service, "_recent_speakers", {})
    rank_service.record_recent_speaker("10001", "1")
    rank_service._recent_speakers[("10001", "2")] = time.monotonic() - 5 * 60 - 1

    assert [
        info["user_id"] for info in rank_service.filter_recent_members(sample_rank_data(), "10001", 5)
    ] == ["1"]


def test_filter_recent_members_window_boundary(monkeypatch):
    monkeypatch.setattr(rank_service, "time", FakeClock(1000.0))
    monkeypatch.setattr(
        rank_service,
        "_recent_speakers",
        {("10001", "1"): 1000.0 - 5 * 60, ("10001", "2"): 1000.0 - 5 * 60 - 1},
    )

    assert [
        info["user_id"] for info in rank_service.filter_recent_members(sample_rank_data(), "10001", 5)
    ] == ["1"]


def test_recent_speaker_table_is_pruned(monkeypatch):
    monkeypatch.setattr(rank_service, "RECENT_SPEAKER_PRUNE_THRESHOLD", 2)
    stale = time.monotonic() - rank_service.MAX_BET_RECENT_MINUTES * 60 - 1
    monkeypatch.setattr(
        rank_service,
        "_recent_speakers",
        {("10001", "1"): stale, ("10001", "2"): stale},
    )

    rank_service.record_recent_speaker("10001", "3")

    assert list(rank_service._recent_speakers) == [("10001", "3")]


def test_get_period_date_range():
    day = date(2026, 9, 30)  # 周三

    assert rank_service.get_period_date_range("daily", day) is None
    assert rank_service.get_period_date_range("weekly", day) == "统计 09-28 ~ 09-30"
    assert rank_service.get_period_date_range("monthly", day) == "统计 09-01 ~ 09-30"


def test_build_report_message_mentions_ranked_members_for_weekly():
    message = rank_service.build_report_message("weekly", [{"user_id": "1"}, {"user_id": "2"}])

    assert message[0].data["text"] == "正在放送周报。。。"
    assert [seg.data["qq"] for seg in message if seg.type == "at"] == ["1", "2"]


def test_build_report_message_returns_plain_text_for_daily():
    assert rank_service.build_report_message("daily", [{"user_id": "1"}]) == "正在放送日报。。。"


def test_weekly_card_receives_date_range(monkeypatch):
    monkeypatch.setattr(rank_service, "get_plugin_by_module_name", lambda name: None)
    monkeypatch.setattr(rank_service, "download_avatar", fake_avatar)
    captured = {}

    class RecordingGenerator:
        def generate_card_bytes(self, members, title, date_range=None):
            captured["date_range"] = date_range
            return b"image-bytes"

    monkeypatch.setattr(rank_service, "RankCardGenerator", RecordingGenerator)

    asyncio.run(rank_service.generate_rank_card(sample_rank_data(), "weekly", "10001"))
    assert captured["date_range"] == rank_service.get_period_date_range("weekly")

    asyncio.run(rank_service.generate_rank_card(sample_rank_data(), "daily", "10001"))
    assert captured["date_range"] is None


def test_members_carry_affection_note(monkeypatch):
    install_affection_stub(monkeypatch)
    monkeypatch.setattr(rank_service, "download_avatar", fake_avatar)
    captured = {}

    class RecordingGenerator:
        def generate_card_bytes(self, members, title, date_range=None):
            captured["members"] = members
            return b"image-bytes"

    monkeypatch.setattr(rank_service, "RankCardGenerator", RecordingGenerator)

    image_bytes = asyncio.run(rank_service.generate_rank_card(sample_rank_data(), "daily", "10001"))

    assert image_bytes == b"image-bytes"
    member = captured["members"][0]
    assert member.affection == 42
    assert member.affection_title == "春心萌动"
    assert member.affection_note == "今天也很想见你呀"


def test_card_bytes_are_generated_without_affection_plugin(monkeypatch):
    monkeypatch.setattr(rank_service, "get_plugin_by_module_name", lambda name: None)
    monkeypatch.setattr(rank_service, "download_avatar", fake_avatar)

    image_bytes = asyncio.run(rank_service.generate_rank_card(sample_rank_data(), "daily", "10001"))

    assert image_bytes.startswith(PNG_SIGNATURE)
    assert len(image_bytes) > 1000
