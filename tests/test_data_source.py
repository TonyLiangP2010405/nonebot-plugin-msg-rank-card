import json
from datetime import date

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


def write_daily_data(tmp_path, group_id, day, data):
    path = tmp_path / f"{group_id}_{day.strftime('%Y%m%d')}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_weekly_and_monthly_rank_aggregation(monkeypatch, tmp_path):
    use_temp_data_dir(monkeypatch, tmp_path)
    group_id = "10001"
    current_day = date(2026, 9, 23)  # 周三

    write_daily_data(tmp_path, group_id, date(2026, 9, 1), {"1": {"name": "用户一", "msg_count": 50}})
    write_daily_data(tmp_path, group_id, date(2026, 9, 20), {"2": {"name": "用户二", "msg_count": 30}})
    write_daily_data(
        tmp_path,
        group_id,
        date(2026, 9, 21),
        {
            "1": {"name": "用户一", "msg_count": 5, "time_seconds": 20},
            "2": {"name": "用户二", "msg_count": 8, "time_seconds": 30},
        },
    )
    write_daily_data(
        tmp_path,
        group_id,
        current_day,
        {
            "1": {"name": "用户一新昵称", "msg_count": 10, "time_seconds": 40},
            "3": {"name": "用户三", "msg_count": 2, "time_seconds": 10},
        },
    )

    daily = data_source.get_period_rank_data(group_id, "daily", current_day=current_day)
    weekly = data_source.get_period_rank_data(group_id, "weekly", current_day=current_day)
    monthly = data_source.get_period_rank_data(group_id, "monthly", current_day=current_day)

    assert [(item["user_id"], item["msg_count"]) for item in daily] == [("1", 10), ("3", 2)]
    assert [(item["user_id"], item["msg_count"]) for item in weekly] == [
        ("1", 15),
        ("2", 8),
        ("3", 2),
    ]
    assert weekly[0]["name"] == "用户一新昵称"
    assert weekly[0]["time_seconds"] == 60
    assert [(item["user_id"], item["msg_count"]) for item in monthly] == [
        ("1", 65),
        ("2", 38),
        ("3", 2),
    ]


def test_unknown_rank_period_is_rejected(monkeypatch, tmp_path):
    use_temp_data_dir(monkeypatch, tmp_path)

    try:
        data_source.get_period_rank_data("10001", "yearly")
    except ValueError as error:
        assert "yearly" in str(error)
    else:
        raise AssertionError("未知排行榜周期应该报错")
