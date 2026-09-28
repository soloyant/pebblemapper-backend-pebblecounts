"""PebbleCountsAuto (Purinton & Bookhagen, 2019) as a PebbleMapper backend.

Declared through ``user_detectors.json`` (``{"module":
"pm_pebblecounts_backend.backend", "factory": "make_backend", "path": "<this
repository>"}``); no PebbleMapper source is touched. The driver is
PebbleMapper's own :class:`detectors.instance_backend.InstanceSubprocessBackend`.

This one is not a neural network at all: k-means colour masking, edge
detection and ellipse filtering in OpenCV and scikit-image, on the CPU, with
no weights to load. It is here to test the claim that PebbleMapper takes *any*
grain detector, not merely another CNN.

The upstream script is GPL-3.0-or-later and so is this adapter (see LICENSE):
``run.py`` executes ``PebbleCountsAuto.py`` unmodified inside its own process
and takes the grain mask the script builds. PebbleMapper itself (MIT) only
launches that process and reads back a label image; nothing of PebbleCounts is
included in this repository or redistributed with the application.
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
from __future__ import annotations

import json
import os
from pathlib import Path

from detectors.base import BackendInfo
from detectors.instance_backend import InstanceSubprocessBackend

PKG_DIR = Path(__file__).resolve().parent
REPO_DIR = PKG_DIR.parent
UPSTREAM = REPO_DIR / "upstream"
# PebbleCountsAuto needs numpy, opencv, scikit-image, scipy, shapely,
# matplotlib and GDAL. environment.yml builds 'pm-pebblecounts'; the set is
# also a subset of PebbleMapper's own environment, so PM_PC_ENV=maskrcnn works
# where building GDAL with conda is not an option.
ENV_NAME = os.environ.get("PM_PC_ENV", "pm-pebblecounts")
_SCRIPT = PKG_DIR / "run.py"

CITATION = ("Purinton, B., & Bookhagen, B. (2019). Introducing PebbleCounts: "
            "a grain-sizing tool for photo surveys of dynamic gravel-bed "
            "rivers. Earth Surface Dynamics, 7, 859-877. "
            "https://doi.org/10.5194/esurf-7-859-2019")

INFO = BackendInfo(
    name="pebblecounts",
    display_name="PebbleCountsAuto (Purinton & Bookhagen)",
    framework="classical (opencv + scikit-image)",
    license=("GPL-3.0-or-later (PebbleCounts, Copyright Benjamin Purinton; "
             "this adapter is GPL-3.0-or-later too, Copyright 2026 Antoine "
             "Soloy). The upstream script is executed as a separate process "
             "and is not redistributed with this adapter or with PebbleMapper."),
    output_type="instance",
    env=ENV_NAME,
    in_process=False,
    weights="none (no trained model)",
    install_hint=("Run scripts/get_upstream.py (clones UP-RS-ESP/PebbleCounts "
                  "into upstream/), create the conda env (environment.yml) and "
                  "declare the backend in user_detectors.json. If the env "
                  "exists but lacks GDAL, add it in place: conda install -n "
                  "pm-pebblecounts -c conda-forge gdal"),
    description=("Edge detection and ellipse filtering, no neural network and "
                 "no weights; CPU only. Its grains are measured by "
                 "PebbleMapper's shared measurement step, and it reports no "
                 "per-instance confidence, so every clast is scored 1.0. "
                 "Cite: " + CITATION),
)


def make_backend():
    """Zero-argument factory named in user_detectors.json."""
    return PebbleCountsBackend()


class PebbleCountsBackend(InstanceSubprocessBackend):
    info = INFO
    env_name = ENV_NAME
    required_modules = ("osgeo", "cv2", "skimage", "sklearn", "shapely")
    script = _SCRIPT
    model_version = "PebbleCountsAuto (2019)"
    log_prefix = "pebblecounts"

    def is_available(self) -> bool:
        return (super().is_available()
                and (UPSTREAM / "PebbleCountsAuto.py").is_file())

    def spec_params(self, mode, kwargs, resolution):
        log_fn = kwargs.get("log_fn") or (lambda s: None)
        from functions import modes
        if modes.normalise_mode(mode) == modes.ORTHO:
            log_fn("[pebblecounts] note: this backend runs the photograph "
                   "path of PebbleCountsAuto; an ortho is processed whole, "
                   "with no tiling and no resume.")
        if kwargs.get("min_confidence") is not None:
            log_fn("[pebblecounts] note: min_confidence is a Mask R-CNN "
                   "threshold; this algorithm has no detector confidence, so "
                   "it is recorded in the manifest but not applied.")
        opts = dict(kwargs.get("pebblecounts_options")
                    or json.loads(os.environ.get("PM_PC_OPTIONS", "{}") or "{}"))
        return {"pc": opts}
