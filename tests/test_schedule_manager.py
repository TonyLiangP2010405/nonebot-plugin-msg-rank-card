import asyncio

from nonebot_plugin_apscheduler import scheduler

from nonebot_plugin_msg_rank_card import schedule_manager


def use_temp_schedule_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(schedule_manager, "get_data_dir", lambda: tmp_path)


def test_normalize_clock():
    assert schedule_manager.normalize_clock("8:05") == "08:05"

    try:
        schedule_manager.normalize_clock("25:00")
    except ValueError as error:
        assert "HH:MM" in str(error)
    else:
        raise AssertionError("无效时间应该报错")


def test_schedule_is_persisted_and_job_is_created(monkeypatch, tmp_path):
    use_temp_schedule_dir(monkeypatch, tmp_path)
    group_id = "10001"

    try:
        schedule_manager.configure_group_schedule(group_id, "daily", 6, "999")
        schedule_manager.configure_group_schedule(group_id, "weekly", "20:30", "999")

        settings = schedule_manager.get_group_schedule(group_id)
        assert settings["daily_interval_hours"] == 6
        assert settings["weekly_time"] == "20:30"
        assert settings["bot_id"] == "999"
        assert scheduler.get_job("msg-rank-card:10001:daily") is not None
        assert scheduler.get_job("msg-rank-card:10001:weekly") is not None

        schedule_manager.configure_group_schedule(group_id, "daily", None, "999")
        assert schedule_manager.get_schedule_value(group_id, "daily") is None
        assert scheduler.get_job("msg-rank-card:10001:daily") is None

        scheduler.remove_job("msg-rank-card:10001:weekly")
        schedule_manager.restore_schedule_jobs()
        assert scheduler.get_job("msg-rank-card:10001:weekly") is not None
        assert scheduler.get_job("msg-rank-card:cleanup") is not None
    finally:
        for job_id in (
            f"msg-rank-card:{group_id}:daily",
            f"msg-rank-card:{group_id}:weekly",
            f"msg-rank-card:{group_id}:monthly",
            "msg-rank-card:cleanup",
        ):
            job = scheduler.get_job(job_id)
            if job:
                scheduler.remove_job(job.id)


def test_scheduled_rank_is_sent(monkeypatch):
    sent = []

    class FakeBot:
        async def send_group_msg(self, **kwargs):
            sent.append(kwargs)

    async def fake_generate(rank_data, period):
        assert period == "weekly"
        assert rank_data[0]["user_id"] == "1"
        return b"image"

    monkeypatch.setattr(schedule_manager, "_find_bot", lambda bot_id: FakeBot())
    monkeypatch.setattr(
        schedule_manager,
        "get_rank_for_period",
        lambda group_id, period: [{"user_id": "1"}],
    )
    monkeypatch.setattr(schedule_manager, "generate_rank_card", fake_generate)

    asyncio.run(schedule_manager._run_scheduled_rank("10001", "weekly", "999"))

    assert len(sent) == 2
    assert sent[0] == {"group_id": 10001, "message": "正在放送周报。。。"}
    assert sent[1]["group_id"] == 10001
