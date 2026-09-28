"""Clone PebbleCounts (GPL-3.0) into upstream/, where run.py expects it.

    python scripts/get_upstream.py
"""
# Copyright (C) 2026 Antoine Soloy
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of the PebbleCountsAuto plug-in for PebbleMapper.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with this program. If not, see <https://www.gnu.org/licenses/>.
import subprocess
import sys
from pathlib import Path

dest = Path(__file__).resolve().parents[1] / "upstream"
if (dest / "PebbleCountsAuto.py").exists():
    print(f"have {dest}")
    sys.exit(0)
subprocess.run(["git", "clone", "--depth", "1",
                "https://github.com/UP-RS-ESP/PebbleCounts.git", str(dest)], check=True)
print(f"cloned into {dest}")
