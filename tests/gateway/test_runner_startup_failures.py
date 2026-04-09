from types import SimpleNamespace

import pytest

import gateway.run as gateway_run
from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter
from gateway.run import GatewayRunner
from gateway.status import read_runtime_status


class _RetryableFailureAdapter(BasePlatformAdapter):
    def __init__(self):
        super().__init__(PlatformConfig(enabled=True, token="***"), Platform.TELEGRAM)

    async def connect(self) -> bool:
        self._set_fatal_error(
            "telegram_connect_error",
            "Telegram startup failed: temporary DNS resolution failure.",
            retryable=True,
        )
        return False

    async def disconnect(self) -> None:
        self._mark_disconnected()

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        raise NotImplementedError

    async def get_chat_info(self, chat_id):
        return {"id": chat_id}


class _DisabledAdapter(BasePlatformAdapter):
    def __init__(self):
        super().__init__(PlatformConfig(enabled=False, token="***"), Platform.TELEGRAM)

    async def connect(self) -> bool:
        raise AssertionError("connect should not be called for disabled platforms")

    async def disconnect(self) -> None:
        self._mark_disconnected()

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        raise NotImplementedError

    async def get_chat_info(self, chat_id):
        return {"id": chat_id}


@pytest.mark.asyncio
async def test_runner_returns_failure_for_retryable_startup_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    config = GatewayConfig(
        platforms={
            Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")
        },
        sessions_dir=tmp_path / "sessions",
    )
    runner = GatewayRunner(config)

    monkeypatch.setattr(runner, "_create_adapter", lambda platform, platform_config: _RetryableFailureAdapter())

    ok = await runner.start()

    assert ok is False
    assert runner.should_exit_cleanly is False
    state = read_runtime_status()
    assert state["gateway_state"] == "startup_failed"
    assert "temporary DNS resolution failure" in state["exit_reason"]
    assert state["platforms"]["telegram"]["state"] == "fatal"
    assert state["platforms"]["telegram"]["error_code"] == "telegram_connect_error"


@pytest.mark.asyncio
async def test_runner_allows_cron_only_mode_when_no_platforms_are_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    config = GatewayConfig(
        platforms={
            Platform.TELEGRAM: PlatformConfig(enabled=False, token="***")
        },
        sessions_dir=tmp_path / "sessions",
    )
    runner = GatewayRunner(config)

    ok = await runner.start()

    assert ok is True
    assert runner.should_exit_cleanly is False
    assert runner.adapters == {}
    state = read_runtime_status()
    assert state["gateway_state"] == "running"


def test_replace_existing_gateway_uses_sigterm_on_windows(monkeypatch):
    calls = []
    removed = []
    fake_sigterm = SimpleNamespace(name="SIGTERM")

    monkeypatch.setattr(gateway_run, "_IS_WINDOWS", True)
    monkeypatch.setattr(gateway_run, "signal", SimpleNamespace(SIGTERM=fake_sigterm))
    monkeypatch.setattr(gateway_run.time, "sleep", lambda _: None)
    monkeypatch.setattr(gateway_run.os, "kill", lambda pid, sig: calls.append((pid, sig)))
    monkeypatch.setattr("gateway.status.remove_pid_file", lambda: removed.append(True))
    monkeypatch.setattr("gateway.status.release_all_scoped_locks", lambda: 0)

    assert gateway_run._replace_existing_gateway(42) is True
    assert calls[0] == (42, fake_sigterm)
    assert calls[-1] == (42, fake_sigterm)
    assert removed == [True]


def test_replace_existing_gateway_uses_sigkill_off_windows(monkeypatch):
    calls = []
    removed = []
    fake_sigterm = SimpleNamespace(name="SIGTERM")
    fake_sigkill = SimpleNamespace(name="SIGKILL")

    monkeypatch.setattr(gateway_run, "_IS_WINDOWS", False)
    monkeypatch.setattr(
        gateway_run,
        "signal",
        SimpleNamespace(SIGTERM=fake_sigterm, SIGKILL=fake_sigkill),
    )
    monkeypatch.setattr(gateway_run.time, "sleep", lambda _: None)
    monkeypatch.setattr(gateway_run.os, "kill", lambda pid, sig: calls.append((pid, sig)))
    monkeypatch.setattr("gateway.status.remove_pid_file", lambda: removed.append(True))
    monkeypatch.setattr("gateway.status.release_all_scoped_locks", lambda: 0)

    assert gateway_run._replace_existing_gateway(99) is True
    assert calls[0] == (99, fake_sigterm)
    assert calls[-1] == (99, fake_sigkill)
    assert removed == [True]
