"""PebbleCountsAuto backend: subprocess entry point (conda env 'pm-pebblecounts').

Reads the PebbleMapper job spec (``--spec <json>``), runs the upstream
``PebbleCountsAuto.py`` (Purinton & Bookhagen, 2019) on each job image and
writes, for each job, an *instance file* next to the CSV the core expects::

    <out_csv>.instances.npz   labels  int32 HxW  (0 = background, k = grain k)
                              scores  float32 N  (1.0: this algorithm has no
                                                  detector confidence)
                              shape   (H, W)

The upstream script is run unmodified, as its own process, in a scratch
folder (it writes its outputs beside the image it is given and asks before
overwriting, so it never sees a folder with previous results). Its
``_PebbleCountsAuto_LABELS.tif`` is the label image read back here.

PebbleCountsAuto is GPL-3.0; it is executed, never imported into
PebbleMapper, and nothing of it is redistributed with the application.

Spec params honoured: ``resolution`` (metres per pixel; the script takes
mm/px), and ``pc`` (a dict passed through as command-line options:
otsu_threshold, cutoff, percent_overlap, misfit_threshold,
min_size_threshold, first_nl_denoise, tophat_th, sobel_th, canny_sig).
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
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM = os.path.join(os.path.dirname(HERE), "upstream")
SCRIPT = os.path.join(UPSTREAM, "PebbleCountsAuto.py")

# The options the upstream argparse understands, with PebbleCounts' own
# defaults; "otsu_threshold" must be given or the script turns interactive.
_OPTIONS = {
    "otsu_threshold": 50, "cutoff": 20, "percent_overlap": 15,
    "misfit_threshold": 30, "min_size_threshold": 10, "first_nl_denoise": 5,
    "tophat_th": 90, "sobel_th": 90, "canny_sig": 2,
}


def log(msg):
    print(f"[pebblecounts] {msg}", flush=True)


def _stage_image(path, work_dir):
    """A copy of the photograph in a scratch folder, as 8-bit BGR-readable
    TIFF/JPEG: the script reads with cv2.imread and writes its outputs
    beside the file it is given."""
    import cv2
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    ext = os.path.splitext(path)[1].lower()
    dst = os.path.join(work_dir, "image.tif")
    if ext in (".tif", ".tiff"):
        shutil.copy2(path, dst)
        return dst
    with Image.open(path) as im:
        arr = np.asarray(im.convert("RGB"))
    cv2.imwrite(dst, arr[:, :, ::-1])
    return dst


def _run_upstream(image_path, resolution_m, opts, work_dir):
    """PebbleCountsAuto.py, unmodified, run in this process; returns its
    per-grain label image.

    Its ``_LABELS.tif`` is a three-band picture of the result, not a label
    image, and its CSV carries no coordinates for a plain photograph — but
    the script does build the kept-grain mask internally as ``label_fixed``.
    ``runpy`` executes the file as ``__main__`` and hands back its globals,
    so that mask is taken as it is, with nothing patched or reimplemented.
    """
    import runpy
    import builtins
    from scipy import ndimage as ndi

    argv = [SCRIPT, "-im", image_path, "-ortho", "n",
            "-input_resolution", f"{resolution_m * 1000.0:.6f}",  # mm/px
            "-subset", "n"]
    for key, default in _OPTIONS.items():
        argv += [f"-{key}", str(opts.get(key, default))]
    log("PebbleCountsAuto.py " + " ".join(argv[1:]))

    old_argv, old_input, old_cwd = sys.argv, builtins.input, os.getcwd()
    # It asks one question the command line cannot set ("create a color
    # mask?"); the answer is no.
    builtins.input = lambda *a, **k: "n"
    sys.argv = argv
    if UPSTREAM not in sys.path:
        sys.path.insert(0, UPSTREAM)      # its own "import PCfunctions"
    os.chdir(work_dir)
    try:
        ns = runpy.run_path(SCRIPT, run_name="__main__")
    except SystemExit as ex:
        raise RuntimeError(f"PebbleCountsAuto stopped early: {ex}")
    finally:
        sys.argv, builtins.input = old_argv, old_input
        os.chdir(old_cwd)

    mask = ns.get("label_fixed")
    if mask is None:
        raise RuntimeError("PebbleCountsAuto finished without a grain mask")
    labels, n = ndi.label(np.asarray(mask).astype(bool))
    return labels.astype(np.int32), int(n)


def main(argv=None):
    ap = argparse.ArgumentParser(description="PebbleCounts backend for PebbleMapper.")
    ap.add_argument("--spec", required=True)
    args = ap.parse_args(argv)
    with open(args.spec, "r", encoding="utf-8") as fh:
        spec = json.load(fh)

    params = spec.get("params", {})
    opts = params.get("pc", {}) or {}
    jobs = spec.get("jobs", [])
    resolution = float(params.get("resolution") or 0.001)
    log(f"PebbleCountsAuto (Purinton & Bookhagen 2019), {len(jobs)} job(s), "
        f"{resolution * 1000:.4f} mm/px")

    for ji, job in enumerate(jobs):
        path = job["path"]
        out_npz = job.get("instances_path") or (job["out_csv"] + ".instances.npz")
        t0 = time.time()
        log(f"job {ji + 1}/{len(jobs)}: {os.path.basename(path)}")
        work_dir = tempfile.mkdtemp(prefix="pm_pc_")
        try:
            staged = _stage_image(path, work_dir)
            labels, n = _run_upstream(staged, resolution, opts, work_dir)
            h, w = labels.shape
            scores = np.ones(n, dtype=np.float32)
            os.makedirs(os.path.dirname(out_npz) or ".", exist_ok=True)
            np.savez_compressed(out_npz, labels=labels, scores=scores,
                                shape=np.array([h, w], dtype=np.int64))
            log(f"  {n} grains -> {os.path.basename(out_npz)} "
                f"({time.time() - t0:.1f}s)")
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
