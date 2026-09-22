from datetime import datetime, timezone

from PIL import Image

from nonebot_plugin_msg_rank_card.card_generator import (
    BG_WIDTH,
    CARD_HEIGHT,
    CARD_WIDTH,
    RANK_BADGE_WIDTH,
    MemberInfo,
    RankCardGenerator,
    get_beijing_time_text,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CARD_X = (BG_WIDTH - CARD_WIDTH) // 2
CARD_Y = 125


def render_member_card(generator, note):
    avatar = Image.new("RGBA", (100, 100), (220, 10, 10, 255))
    member = MemberInfo(
        "浅夏柚子",
        128,
        3661,
        avatar,
        affection=42,
        affection_title="春心萌动",
        affection_note=note,
    )
    return generator.generate_card([member], "今日水群排行榜", "北京时间 09:05")


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


def test_affection_note_is_drawn_in_the_affection_row():
    RankCardGenerator._instance = None
    generator = RankCardGenerator()

    with_note = render_member_card(generator, "今天也很想见你呀")
    without_note = render_member_card(generator, None)

    affection_row = (CARD_X + 250, CARD_Y + 48, CARD_X + CARD_WIDTH, CARD_Y + 72)
    name_row = (CARD_X, CARD_Y, CARD_X + CARD_WIDTH, CARD_Y + 46)

    assert with_note.crop(affection_row).tobytes() != without_note.crop(affection_row).tobytes()
    assert with_note.crop(name_row).tobytes() == without_note.crop(name_row).tobytes()


def test_long_affection_note_stays_before_the_rank_badge():
    RankCardGenerator._instance = None
    generator = RankCardGenerator()

    with_note = render_member_card(generator, "这是一句特别长的馒头短评超过十六个字")
    without_note = render_member_card(generator, None)

    badge_area = (
        CARD_X + CARD_WIDTH - RANK_BADGE_WIDTH + 5,
        CARD_Y,
        CARD_X + CARD_WIDTH,
        CARD_Y + CARD_HEIGHT,
    )

    assert with_note.crop(badge_area).tobytes() == without_note.crop(badge_area).tobytes()


def test_card_bytes_are_generated_with_affection_notes():
    RankCardGenerator._instance = None
    generator = RankCardGenerator()
    members = [
        MemberInfo("浅夏柚子", 128, 3661, None, affection=42, affection_title="春心萌动", affection_note="今天也很想见你呀"),
        MemberInfo("阿岚", 96, 1800, None, affection=7, affection_title="略有好感", affection_note="来水群啦"),
        MemberInfo("路人", 8, 30, None, affection=3, affection_title="初见"),
    ]

    image_bytes = generator.generate_card_bytes(members, "今日水群排行榜", "北京时间 09:05")

    assert image_bytes.startswith(PNG_SIGNATURE)
    assert len(image_bytes) > 1000
