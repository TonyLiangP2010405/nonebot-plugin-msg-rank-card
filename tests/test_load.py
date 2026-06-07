import nonebot
from nonebot.adapters.onebot.v11 import Adapter


def test_plugin_load():
    nonebot.init()
    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)
    plugin = nonebot.load_plugin("nonebot_plugin_msg_rank_card")
    assert plugin is not None
