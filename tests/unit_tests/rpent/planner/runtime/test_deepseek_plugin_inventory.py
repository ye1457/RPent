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

"""Pin the complete native SDK profile inventory without booting a model."""

import json
import os
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest
import yaml

pytest.importorskip("deepseek_harness_runtime")

from deepseek_harness_runtime import resolve_bundled_launch_args


def test_pinned_sdk_profile_plugin_inventory(tmp_path):
    assert version("deepseek-harness-sdk") == "0.2.1rc2"
    assert version("deepseek-harness-runtime-bin") == "0.2.1rc2"
    result = subprocess.run(
        [*resolve_bundled_launch_args(), "--profile", "sdk", "--dump-default-config"],
        env={
            **os.environ,
            "DSH_HOME": str(tmp_path / "home"),
            "DSH_PRIMARY_RUNTIME": "",
            "DSH_TELEMETRY_DISABLED": "1",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    # BaseLoader keeps native !!js conditions as inert strings for review.
    entries = yaml.load(result.stdout, Loader=yaml.BaseLoader)
    actual = [
        {key: row.get(key, "false") for key in ("id", "name", "disabled")}
        for row in entries
    ]
    expected = json.loads(
        (Path(__file__).parent / "fixtures/sdk_plugins.json").read_text()
    )
    assert actual == expected, (
        "Review every SDK profile plugin before updating the runtime pin"
    )
