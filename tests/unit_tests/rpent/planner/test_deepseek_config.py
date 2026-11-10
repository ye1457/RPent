# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Configuration preflight neither starts sessions nor exposes secret metadata."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from rpent.planner import deepseek_config


@pytest.fixture
def runtime(monkeypatch):
    state = SimpleNamespace(
        clients=[],
        result={"status": "ready", "provider": "openai-codex", "model": "test-model"},
    )

    class Client:
        def __init__(self, config):
            self.config = config
            self.closed = False
            state.clients.append(self)

        def start(self):
            patch = json.loads(Path(self.config.patches[0]).read_text())
            config = patch[-1]["insert"][0]["config"]
            if state.result is not None:
                Path(config["resultPath"]).write_text(json.dumps(state.result))

        def close(self):
            self.closed = True

    monkeypatch.setitem(
        sys.modules,
        "deepseek_harness",
        SimpleNamespace(HarnessClient=Client, HarnessConfig=SimpleNamespace),
    )
    monkeypatch.setattr(deepseek_config, "version", lambda name: "0.2.1rc2")
    return state


def check(home, **kwargs):
    return deepseek_config.preflight_configuration(
        dsh_home=home, model="test-model", reasoning_effort="xhigh", **kwargs
    )


def test_metadata_preflight_closes_without_initializing_session(runtime, tmp_path):
    # The fake client deliberately has no initialize/prompt/request method.
    runtime.result["debug"] = "SYNTHETIC_PRIVATE_CREDENTIAL"
    result = check(tmp_path / "home")
    assert result["provider"] == "openai-codex"
    assert result["dsh_home"] == str(tmp_path / "home")
    assert runtime.clients[0].closed
    assert not Path(runtime.clients[0].config.cwd).exists()
    assert "SYNTHETIC_PRIVATE_CREDENTIAL" not in json.dumps(result)


@pytest.mark.parametrize(
    "status,error,match",
    [
        ("missing_credential", RuntimeError, "rpent-dsh-login"),
        ("unsupported_capability", ValueError, "reasoning or image"),
        ("inspection_failed", RuntimeError, "could not inspect"),
    ],
)
def test_preflight_failures_are_stable_and_do_not_echo_raw_diagnostics(
    runtime, tmp_path, status, error, match, capsys
):
    runtime.result = {"status": status, "detail": "SYNTHETIC_PRIVATE_CREDENTIAL"}
    with pytest.raises(error, match=match) as caught:
        check(tmp_path / "home")
    assert "SYNTHETIC_PRIVATE_CREDENTIAL" not in str(caught.value)
    assert capsys.readouterr().out == ""
    assert runtime.clients[0].closed


def test_preflight_timeout_closes_runtime(runtime, tmp_path):
    runtime.result = None
    with pytest.raises(TimeoutError, match="timed out"):
        check(tmp_path / "home", timeout_s=0.01)
    assert runtime.clients[0].closed


def test_preflight_reports_early_exit_before_sleep_and_preserves_safe_diagnostics(
    runtime, tmp_path, monkeypatch
):
    runtime.result = None
    client_type = sys.modules["deepseek_harness"].HarnessClient
    start = client_type.start

    def start_exited(client):
        start(client)
        client._proc = SimpleNamespace(poll=lambda: 23)

    def diagnostics(client):
        assert not client.closed
        return "bootstrap failed; Authorization: Bearer SYNTHETIC_GRANT access_token=SYNTHETIC_ACCESS"

    def no_wait(_):
        pytest.fail("An exited runtime must not consume the preflight deadline")

    monkeypatch.setattr(client_type, "start", start_exited)
    monkeypatch.setattr(client_type, "_runtime_diagnostics", diagnostics, raising=False)
    monkeypatch.setattr(deepseek_config.time, "sleep", no_wait)
    with pytest.raises(RuntimeError, match="exited before.*23") as caught:
        check(tmp_path / "home")
    message = str(caught.value)
    assert "bootstrap failed" in message
    assert "SYNTHETIC_GRANT" not in message
    assert "SYNTHETIC_ACCESS" not in message
    assert runtime.clients[0].closed


def test_preflight_timeout_captures_bounded_redacted_diagnostics_before_close(
    runtime, tmp_path, monkeypatch
):
    runtime.result = None
    client_type = sys.modules["deepseek_harness"].HarnessClient
    start = client_type.start

    def start_running(client):
        start(client)
        client._proc = SimpleNamespace(poll=lambda: None)

    def diagnostics(client):
        assert not client.closed
        return (
            "x" * 20000 + '\nrefresh_token="SYNTHETIC_REFRESH"\nmetadata plugin pending'
        )

    monkeypatch.setattr(client_type, "start", start_running)
    monkeypatch.setattr(client_type, "_runtime_diagnostics", diagnostics, raising=False)
    with pytest.raises(TimeoutError, match="timed out.*running") as caught:
        check(tmp_path / "home", timeout_s=0.001)
    message = str(caught.value)
    assert "metadata plugin pending" in message
    assert "SYNTHETIC_REFRESH" not in message
    assert "<redacted>" in message
    assert len(message) < 8500
    assert runtime.clients[0].closed


def test_preflight_reports_missing_private_diagnostics_without_fabricating_exit(
    runtime, tmp_path
):
    runtime.result = None
    with pytest.raises(TimeoutError) as caught:
        check(tmp_path / "home", timeout_s=0.001)
    message = str(caught.value)
    assert "process state unavailable" in message
    assert "stderr diagnostics unavailable" in message
    assert "exit code: 0" not in message
    assert runtime.clients[0].closed


def test_preflight_rejects_changed_model_identity(runtime, tmp_path):
    runtime.result["model"] = "different-model"
    with pytest.raises(RuntimeError, match="different model"):
        check(tmp_path / "home")


def test_preflight_missing_home_and_wrong_version_fail_before_runtime(
    runtime, monkeypatch
):
    monkeypatch.delenv("DSH_HOME", raising=False)
    with pytest.raises(ValueError, match="dsh-home"):
        check(None)
    monkeypatch.setattr(deepseek_config, "version", lambda name: "0.2.0")
    with pytest.raises(RuntimeError, match="0.2.1rc2"):
        check("unused-home")
    assert runtime.clients == []


def test_unsupported_provider_is_rejected_before_runtime(runtime, tmp_path):
    with pytest.raises(ValueError, match="requires openai-codex"):
        check(tmp_path / "home", provider="other-provider")
    assert runtime.clients == []


@pytest.mark.parametrize("extra", [[], ["--tui"], ["--dashboard"], ["--explore"]])
def test_runtime_foundation_is_not_registered_as_a_task_planner(extra, capsys):
    from rpent.cli.main import _build_argparser

    with pytest.raises(SystemExit) as caught:
        _build_argparser().parse_args(["--planner", "deepseek_harness", *extra])
    assert caught.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
