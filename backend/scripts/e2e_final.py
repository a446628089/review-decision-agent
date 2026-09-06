#!/usr/bin/env python3
"""端到端验证入口：复用完整的离线会议验证流程。"""

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("e2e_no_reload.py")), run_name="__main__")
