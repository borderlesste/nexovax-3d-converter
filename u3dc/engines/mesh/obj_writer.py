"""Escritor Wavefront OBJ + MTL (+ texturas)."""
from __future__ import annotations

import os
import re

import numpy as np

from ... import APP_NAME, __version__
from ...models.scene import SceneModel


def _clean(name: str) -> str:
    name = re.sub(r"[\r\n\t]+", " ", str(name)).strip()
    return re.sub(r"\s+", "_", name) or "objeto"


def write_obj(scene: SceneModel, path: str, report, keep_materials: bool = True) -> list[str]:
    parts = scene.scaled_copy_flat()
    if not parts:
        raise ValueError("No hay geometría para exportar a OBJ.")
    out_dir = os.path.dirname(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    written = [path]
    mtl_name = stem + ".mtl"
    mat_names: dict[int, str] = {}
    if keep_materials and scene.materials:
        used_names = set()
        for i, m in enumerate(scene.materials):
            n = _clean(m.name)
            base, k = n, 1
            while n in used_names:
                n = f"{base}_{k}"
                k += 1
            used_names.add(n)
            mat_names[i] = n
        tex_files: dict[int, str] = {}
        with open(os.path.join(out_dir, mtl_name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"# {APP_NAME} {__version__}\n")
            for i, m in enumerate(scene.materials):
                r, g, b, a = m.base_color
                fh.write(f"\nnewmtl {mat_names[i]}\nKa 0 0 0\nKd {r:.6f} {g:.6f} {b:.6f}\n"
                         f"Ks 0.2 0.2 0.2\nNs {max(1.0, (1 - m.roughness) * 1000):.1f}\nd {a:.6f}\n"
                         f"illum 2\nPr {m.roughness:.4f}\nPm {m.metallic:.4f}\n")
                if m.base_color_texture is not None:
                    ti = m.base_color_texture
                    if ti not in tex_files:
                        tex = scene.textures[ti]
                        fname = f"{stem}_tex{ti}{tex.extension}"
                        with open(os.path.join(out_dir, fname), "wb") as th:
                            th.write(tex.data)
                        written.append(os.path.join(out_dir, fname))
                        tex_files[ti] = fname
                    fh.write(f"map_Kd {tex_files[ti]}\n")
        written.insert(1, os.path.join(out_dir, mtl_name))

    has_uv_any = keep_materials and any(p[5] is not None for p in parts)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# {APP_NAME} {__version__}\n")
        if mat_names:
            fh.write(f"mtllib {mtl_name}\n")
        voff = 1
        vtoff = 1
        vnoff = 1
        for name, v, f, mat, n, uv in parts:
            fh.write(f"o {_clean(name)}\n")
            np.savetxt(fh, v, fmt="v %.9g %.9g %.9g")
            use_uv = has_uv_any and uv is not None
            if use_uv:
                np.savetxt(fh, uv, fmt="vt %.7g %.7g")
            if n is not None:
                np.savetxt(fh, n, fmt="vn %.6g %.6g %.6g")
            if mat is not None and mat in mat_names:
                fh.write(f"usemtl {mat_names[mat]}\n")
            fv = f + voff
            if use_uv and n is not None:
                ft, fn = f + vtoff, f + vnoff
                arr = np.stack([fv[:, 0], ft[:, 0], fn[:, 0], fv[:, 1], ft[:, 1], fn[:, 1],
                                fv[:, 2], ft[:, 2], fn[:, 2]], axis=1)
                np.savetxt(fh, arr, fmt="f %d/%d/%d %d/%d/%d %d/%d/%d")
            elif use_uv:
                ft = f + vtoff
                arr = np.stack([fv[:, 0], ft[:, 0], fv[:, 1], ft[:, 1], fv[:, 2], ft[:, 2]], axis=1)
                np.savetxt(fh, arr, fmt="f %d/%d %d/%d %d/%d")
            elif n is not None:
                fn = f + vnoff
                arr = np.stack([fv[:, 0], fn[:, 0], fv[:, 1], fn[:, 1], fv[:, 2], fn[:, 2]], axis=1)
                np.savetxt(fh, arr, fmt="f %d//%d %d//%d %d//%d")
            else:
                np.savetxt(fh, fv, fmt="f %d %d %d")
            voff += len(v)
            if use_uv:
                vtoff += len(uv)
            if n is not None:
                vnoff += len(n)
    return written
