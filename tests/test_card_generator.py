from datetime import datetime, timezone

from PIL import Image

from nonebot_plugin_msg_rank_card.card_generator import (
    MemberInfo,
    RankCardGenerator,
    get_beijing_time_text,
)


def test_bundled_card_resources_are_found():
    RankCardGenerator._instance = None
    generator = RankCardGenerator()

    assert len(generator.bg_files) == 3
    assert [path.name for path in generator.frame_files] == [f"{index}.png" for index in range(1, 11)]
    assert generator.font_file is not None


def test_first_place_avatar_is_used_as_background():
    RankCardGenerator._instance = None
    generator = RankCardGenerator()
    avatar = Image.new("RGBA", (100, 100), (220, 10, 10, 255))

    card = generator.generate_card([MemberInfo("第一名", 100, 60, avatar)])
    background_pixel = card.getpixel((0, 500))

    assert background_pixel[0] > background_pixel[1]
    assert background_pixel[1] == background_pixel[2]


def test_beijing_time_text_uses_utc_plus_eight():
    utc_time = datetime(2026, 9, 21, 1, 5, tzinfo=timezone.utc)

    assert get_beijing_time_text(utc_time) == "北京时间 09:05"
