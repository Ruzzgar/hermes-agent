import subprocess
from textwrap import dedent

from hermes_cli import memory_setup


def _write_memory_plugin(tmp_path, provider_name: str, plugin_yaml: str):
    fake_module = tmp_path / "repo" / "hermes_cli" / "memory_setup.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.write_text("# test stub\n")

    plugin_dir = fake_module.parent.parent / "plugins" / "memory" / provider_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(dedent(plugin_yaml))
    return fake_module


def test_install_dependencies_warns_for_external_only_dependency(monkeypatch, tmp_path, capsys):
    fake_module = _write_memory_plugin(
        tmp_path,
        "demo",
        """
        name: demo
        version: 1.0.0
        external_dependencies:
          - name: democtl
            check: "democtl --version"
            install: "brew install democtl"
        """,
    )
    monkeypatch.setattr(memory_setup, "__file__", str(fake_module))

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(memory_setup.subprocess, "run", fake_run)

    memory_setup._install_dependencies("demo")

    output = capsys.readouterr().out
    assert "democtl" in output
    assert "brew install democtl" in output
    assert calls == [
        (
            ["democtl", "--version"],
            {"capture_output": True, "timeout": 5, "check": True},
        )
    ]


def test_external_dependency_check_runs_without_shell(monkeypatch):
    recorded = {}

    def fake_run(cmd, **kwargs):
        recorded["cmd"] = cmd
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(memory_setup.subprocess, "run", fake_run)

    assert memory_setup._external_dependency_is_available(
        'democtl --probe "value with spaces" && whoami'
    )
    assert recorded["cmd"] == ["democtl", "--probe", "value with spaces", "&&", "whoami"]
    assert "shell" not in recorded["kwargs"]
    assert recorded["kwargs"] == {
        "capture_output": True,
        "timeout": 5,
        "check": True,
    }
