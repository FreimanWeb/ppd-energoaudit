from __future__ import annotations

import os
import tempfile
from pathlib import Path


_TEST_DB = Path(tempfile.gettempdir()) / "ppd-audit-tests.sqlite"
_TEST_DB.unlink(missing_ok=True)

os.environ.setdefault("PPD_DATABASE_PATH", str(_TEST_DB))
os.environ.setdefault("PPD_SKIP_EXAMPLE_TELEMETRY", "1")
