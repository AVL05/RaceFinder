"""Generador de fotos SINTETICAS de carrera con condiciones dificiles y etiquetas conocidas.

Sirve para comparar variantes del algoritmo bajo condiciones controladas (inclinacion, tamano, desenfoque...).
NO sustituye a fotos reales: los resultados sobre este conjunto no se pueden presentar como precision real.
Uso: python tools/synth.py <carpeta_salida> --per-cond 8 --seed 1
"""
import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = ["arialbd.ttf", "impact.ttf", "verdanab.ttf", "tahomabd.ttf", "calibrib.ttf"]
W, H = 3000, 2000
CONDS = ["base", "pequeno", "inclinado", "ocluido", "varios_corredores", "fondo_complejo",
         "cartel_reloj", "poca_luz", "desenfocado", "sin_dorsal"]


def font(rng, size):
    for _ in range(5):
        try:
            return ImageFont.truetype(rng.choice(FONTS), max(6, int(size)))
        except OSError:
            continue
    return ImageFont.load_default()


def bib_image(number, h, rng):
    w = int(h * rng.uniform(1.2, 1.7))
    base = rng.choice([(250, 250, 250), (255, 235, 90), (255, 140, 60), (120, 200, 255), (250, 250, 250)])
    im = Image.new("RGBA", (w, h), base + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w - 1, h - 1), outline=(30, 30, 30, 255), width=max(2, h // 40))
    fs = int(h * 0.62)
    f = font(rng, fs)
    while d.textlength(number, font=f) > w * 0.86 and fs > 8:
        fs -= 4
        f = font(rng, fs)
    d.text((w / 2, h * 0.58), number, font=f, fill=(15, 15, 15, 255), anchor="mm")
    d.text((w / 2, h * 0.12), "CITY RUN 10K", font=font(rng, max(8, h // 9)), fill=(60, 60, 60, 255), anchor="mm")
    for cx, cy in ((0.06, 0.1), (0.94, 0.1), (0.06, 0.9), (0.94, 0.9)):
        r = max(2, h // 40)
        d.ellipse((w * cx - r, h * cy - r, w * cx + r, h * cy + r), fill=(90, 90, 90, 255))
    return im


def warp(im, angle, persp, rng):
    arr = np.array(im)
    h, w = arr.shape[:2]
    pad = int(max(h, w) * 0.5)
    arr = cv2.copyMakeBorder(arr, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    H2, W2 = arr.shape[:2]
    M = cv2.getRotationMatrix2D((W2 / 2, H2 / 2), angle, 1.0)
    arr = cv2.warpAffine(arr, M, (W2, H2), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    if persp:
        j = persp * w
        src = np.float32([[0, 0], [W2, 0], [W2, H2], [0, H2]])
        dst = src + np.float32([[rng.uniform(-j, j), rng.uniform(-j, j)] for _ in range(4)])
        arr = cv2.warpPerspective(arr, cv2.getPerspectiveTransform(src, dst), (W2, H2), borderValue=(0, 0, 0, 0))
    ys, xs = np.where(arr[:, :, 3] > 0)
    return Image.fromarray(arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1])


def background(rng, complex_):
    y = np.linspace(0, 1, H)[:, None, None]
    c1 = np.array([rng.randint(90, 200) for _ in range(3)])
    c2 = np.array([rng.randint(60, 160) for _ in range(3)])
    arr = (c1 * (1 - y) + c2 * y) * np.ones((H, W, 3))
    arr += np.random.default_rng(rng.randint(0, 10**6)).normal(0, 6, (H, W, 3))
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for _ in range(40 if complex_ else 6):
        x, yy = rng.randint(0, W), rng.randint(0, H)
        col = tuple(rng.randint(20, 240) for _ in range(3))
        if rng.random() < 0.5:
            d.rectangle((x, yy, x + rng.randint(40, 400), yy + rng.randint(40, 300)), fill=col)
        else:
            d.ellipse((x, yy, x + rng.randint(40, 300), yy + rng.randint(40, 300)), fill=col)
    if complex_:  # texto de patrocinadores y vallas
        for _ in range(14):
            d.text((rng.randint(0, W - 300), rng.randint(0, H - 100)),
                   rng.choice(["SPORT", "ENERGY", "MEGA", "FINISH", "2025"]),
                   font=font(rng, rng.randint(40, 140)), fill=tuple(rng.randint(0, 255) for _ in range(3)))
    return im


def runner(im, cx, base_y, scale, rng):
    d = ImageDraw.Draw(im)
    shirt = tuple(rng.randint(30, 230) for _ in range(3))
    skin = (rng.randint(150, 230), rng.randint(110, 180), rng.randint(80, 150))
    tw, th = int(260 * scale), int(330 * scale)
    top = base_y - th
    d.ellipse((cx - 60 * scale, top - 150 * scale, cx + 60 * scale, top - 10 * scale), fill=skin)
    d.rounded_rectangle((cx - tw / 2, top, cx + tw / 2, base_y), radius=int(30 * scale), fill=shirt)
    d.rectangle((cx - 90 * scale, base_y, cx + 90 * scale, base_y + 380 * scale), fill=(30, 30, 50))
    return cx, top, tw, th, skin


def render(cond, rng):
    """Devuelve (imagen PIL, dorsales visibles, etiquetas)."""
    bg = background(rng, cond == "fondo_complejo")
    truth, tags = [], []
    no_bib = cond in ("sin_dorsal", "cartel_reloj")
    n_runners = rng.randint(3, 4) if cond == "varios_corredores" else 1
    used = set()
    for k in range(n_runners):
        scale = rng.uniform(0.9, 1.3)
        if cond == "pequeno":
            scale = rng.uniform(0.25, 0.4)
        if cond == "varios_corredores":
            scale = rng.uniform(0.7, 1.0)
        cx = int(W * (k + 0.5) / n_runners) + rng.randint(-60, 60)
        cx, top, tw, th, skin = runner(bg, cx, int(H * rng.uniform(0.62, 0.8)), scale, rng)
        if no_bib:
            continue
        number = str(rng.choice([rng.randint(1, 99), rng.randint(100, 999), rng.randint(1000, 9999)]))
        while number in used:
            number = str(rng.randint(100, 9999))
        used.add(number)
        bib = bib_image(number, max(20, int(th * 0.42)), rng)
        angle = rng.choice([-1, 1]) * rng.uniform(25, 45) if cond == "inclinado" else rng.uniform(-6, 6)
        bib = warp(bib, angle, 0.06 if cond == "inclinado" else 0.015, rng)
        if cond == "ocluido":  # brazo/tira en un borde que no tapa los digitos
            ImageDraw.Draw(bib).rectangle((0, 0, int(bib.width * 0.07), bib.height), fill=skin + (255,))
        bg.paste(bib, (int(cx - bib.width / 2), int(top + th * 0.2)), bib)
        truth.append(number)
    d = ImageDraw.Draw(bg)
    if cond == "cartel_reloj":
        d.rectangle((200, 150, 900, 420), fill=(20, 20, 20))
        d.text((550, 290), "01:42:17", font=font(rng, 130), fill=(255, 40, 40), anchor="mm")
        d.rectangle((2000, 200, 2700, 700), fill=(240, 240, 240))
        d.text((2350, 450), str(rng.randint(1000, 9999)), font=font(rng, 240), fill=(0, 0, 0), anchor="mm")
        d.text((2350, 620), "KM 12", font=font(rng, 80), fill=(200, 0, 0), anchor="mm")
    if cond == "poca_luz":
        arr = (np.array(bg).astype(np.float32) / 255) ** 2.2 * 255 * 0.55
        bg = Image.fromarray(np.clip(arr + np.random.default_rng(1).normal(0, 7, arr.shape), 0, 255).astype(np.uint8))
    if cond == "desenfocado":
        bg = bg.filter(ImageFilter.GaussianBlur(rng.uniform(3, 5)))
    if cond in ("ocluido", "cartel_reloj", "poca_luz", "desenfocado", "pequeno", "inclinado", "varios_corredores", "fondo_complejo"):
        tags.append(cond)
    return bg, truth, tags


def generate(out: Path, per_cond: int, seed: int):
    out.mkdir(parents=True, exist_ok=True)
    labels = {}
    for ci, cond in enumerate(CONDS):
        for i in range(per_cond):
            rng = random.Random(seed * 100000 + ci * 1000 + i)
            im, truth, tags = render(cond, rng)
            name = f"{cond}_{i:02d}.jpg"
            im.save(out / name, quality=92)
            labels[name] = {"bibs": truth, "tags": tags, "cond": cond}
    (out / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
    return labels


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--per-cond", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    print(len(generate(Path(a.out), a.per_cond, a.seed)), "imagenes")
