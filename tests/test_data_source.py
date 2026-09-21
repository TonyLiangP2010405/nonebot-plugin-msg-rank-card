from nonebot_plugin_msg_rank_card import data_source


def use_temp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(data_source, "_data_dir", tmp_path)
    monkeypatch.setattr(data_source, "_data_dir_initialized", True)


def test_rank_change_notify_setting_is_persisted(monkeypatch, tmp_path):
    use_temp_data_dir(monkeypatch, tmp_path)

    assert not data_source.is_rank_change_notify_enabled("10001")

    data_source.set_rank_change_notify("10001", True)
    assert data_source.is_rank_change_notify_enabled("10001")

    data_source.set_rank_change_notify("10001", False)
    assert not data_source.is_rank_change_notify_enabled("10001")


def test_rank_change_only_when_member_order_changes(monkeypatch, tmp_path):
    use_temp_data_dir(monkeypatch, tmp_path)

    assert not data_source.record_message_and_check_rank_change("10001", "1", "用户一")
    assert data_source.record_message_and_check_rank_change("10001", "2", "用户二")
    assert not data_source.record_message_and_check_rank_change("10001", "1", "用户一")
    assert not data_source.record_message_and_check_rank_change("10001", "2", "用户二")
    assert data_source.record_message_and_check_rank_change("10001", "2", "用户二")

    rank_data = data_source.get_rank_data("10001")
    assert [item["user_id"] for item in rank_data] == ["2", "1"]


def test_change_outside_visible_rank_does_not_notify(monkeypatch, tmp_path):
    use_temp_data_dir(monkeypatch, tmp_path)

    assert not data_source.record_message_and_check_rank_change("10001", "1", "用户一", max_count=1)
    assert not data_source.record_message_and_check_rank_change("10001", "2", "用户二", max_count=1)
