import nonebot


def test_plugin_load():
    plugin = nonebot.get_plugin("nonebot_plugin_msg_rank_card")
    assert plugin is not None
