import asyncio
import sys
from types import ModuleType, SimpleNamespace

from PIL import Image

from nonebot_plugin_msg_rank_card import rank_service

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


def test_members_carry_affection_note(monkeypatch):
    install_affection_stub(monkeypatch)
    monkeypatch.setattr(rank_service, "download_avatar", fake_avatar)
    captured = {}

    class RecordingGenerator:
        def generate_card_bytes(self, members, title):
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
