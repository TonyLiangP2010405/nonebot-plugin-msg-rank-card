from nonebot_plugin_msg_rank_card.card_generator import RankCardGenerator


def test_bundled_card_resources_are_found():
    RankCardGenerator._instance = None
    generator = RankCardGenerator()

    assert len(generator.bg_files) == 3
    assert [path.name for path in generator.frame_files] == [f"{index}.png" for index in range(1, 11)]
    assert generator.font_file is not None
