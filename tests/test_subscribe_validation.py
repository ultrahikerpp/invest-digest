"""Regression test: subscribing to only the weekly digest (no channels checked)
must pass validation in the docs/index.html subscribe modal."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX_HTML = Path(__file__).parent.parent / "docs" / "index.html"


def _extract_sub_can_submit() -> str:
    html = INDEX_HTML.read_text(encoding="utf-8")
    match = re.search(r"function _subCanSubmit\([^)]*\)\s*{[^}]*}", html)
    assert match, "_subCanSubmit function not found in docs/index.html"
    return match.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize(
    "channels,weekly_checked,expected",
    [
        ([], True, True),          # weekly-only subscription: the reported bug
        ([], False, False),        # nothing selected: still rejected
        (["UC1"], False, True),    # channel-only subscription: unaffected
    ],
)
def test_sub_can_submit(channels, weekly_checked, expected):
    fn_src = _extract_sub_can_submit()
    script = f"{fn_src}\nconsole.log(JSON.stringify(_subCanSubmit({json.dumps(channels)}, {json.dumps(weekly_checked)})));"
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout.strip()) == expected
