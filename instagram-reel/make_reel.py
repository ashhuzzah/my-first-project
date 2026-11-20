#!/usr/bin/env python3
"""Cut four portrait cat clips into a 9:16 Instagram Reel.

Effects: smooth push-in zooms, a punch-in zoom with camera shake, speed ramps
(blurred fast-forward into 60fps slow-mo), zoom-blur/flash and whip
transitions, a warm colour grade with vignette and grain, cinematic bars,
pop-in captions, and whoosh/impact sound effects mixed over the original audio.

Writes two versions: one with captions and a clean one (no text), so you can
add Instagram's own text and trending audio instead if you prefer.

usage:  python3 make_reel.py
env:    CLIP_DIR  folder holding the source .mov files
        WORK_DIR  folder for intermediate files
"""
import math
import os
import subprocess
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "output")
WORK = os.environ.get("WORK_DIR", os.path.join(HERE, "work"))
CLIP_DIR = os.environ.get("CLIP_DIR", ".")
CLIPS = {
    "0911": "381f0552-IMG_0911.mov",
    "0912a": "e9f64c1f-IMG_0912.mov",
    "0912b": "9a2e35e4-IMG_0912.mov",
    "0912c": "f923a7c1-IMG_0912.mov",
}

W, H, FPS = 1080, 1920, 30
SRC_FPS = 60000 / 1001
SR = 48000
CAP_Y = int(H * 0.215)  # caption centre: below the Reels header, above the cat
FONT = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

# Each shot: list of (src_start, src_end, speed) pieces, zoom keyframes
# (time, zoom, centre_x, centre_y) with time in seconds from shot start or
# "p<i>[+/-s]" (start of piece i) / "end"; centre is normalised 0..1.
SHOTS = [
    dict(  # hook: pawing at the glass
        clip="0912a",
        pieces=[(0.0, 1.9, 1.0)],
        keys=[(0, 1.0, 0.32, 0.72), ("end", 1.22, 0.32, 0.72)],
        caption=("him every time it rains", "\U0001F327"),
        cap_at=0.0,
        trans_out="zoom",
    ),
    dict(  # turns round -> punch-in on the side-eye in slow-mo
        clip="0911",
        pieces=[(1.5, 2.75, 1.0), (2.75, 3.65, 0.5)],
        keys=[
            (0, 1.05, 0.50, 0.50),
            ("p1-0.04", 1.12, 0.48, 0.50),
            ("p1", 1.58, 0.45, 0.51),
            ("end", 1.75, 0.45, 0.51),
        ],
        punch="p1",
        caption=("and somehow it's my fault", "\U0001F612"),
        cap_at="p1",
        trans_out="whip",
    ),
    dict(  # fast ramp round behind him -> slow-mo look up at the sky
        clip="0912a",
        pieces=[(3.0, 4.0, 2.5), (4.0, 5.8, 0.55)],
        keys=[(0, 1.28, 0.42, 0.42), ("p1", 1.10, 0.42, 0.40), ("end", 1.40, 0.41, 0.40)],
        caption=("checking if it stopped yet", None),
        cap_at="p1",
        trans_out="zoom",
    ),
    dict(  # dramatic profile, cinematic bars
        clip="0912b",
        pieces=[(3.5, 4.3, 1.0), (4.3, 6.4, 0.7)],
        keys=[(0, 1.05, 0.45, 0.50), ("end", 1.38, 0.40, 0.53)],
        letterbox=True,
        caption=("accepting his fate", None),
        cap_at="p1-0.2",
        trans_out="whip",
    ),
    dict(  # gives up, walks off, gets pets
        clip="0912c",
        pieces=[(3.2, 5.0, 3.0), (5.0, 6.42, 0.55)],
        keys=[(0, 1.22, 0.50, 0.50), ("p1", 1.16, 0.40, 0.50), ("end", 1.0, 0.40, 0.50)],
        caption=("ok fine. pets instead", "\U0001F9E1"),
        cap_at="p1+1.2",
        trans_out=None,
    ),
]


# ---------------------------------------------------------------- timeline
def layout():
    t = 0
    for sh in SHOTS:
        sh["piece_frames"], sh["piece_starts"] = [], []
        n = 0
        for s, e, sp in sh["pieces"]:
            k = round((e - s) / sp * FPS)
            sh["piece_starts"].append(n)
            sh["piece_frames"].append(k)
            n += k
        sh["n"], sh["start"] = n, t
        t += n
    return t


def tframe(sh, spec):
    """Resolve a time spec to a (float) frame index within the shot."""
    if isinstance(spec, (int, float)):
        return spec * FPS
    base, off = spec, 0.0
    for i in range(1, len(spec)):
        if spec[i] in "+-":
            base, off = spec[:i], float(spec[i:])
            break
    b = sh["n"] - 1 if base == "end" else sh["piece_starts"][int(base[1:])]
    return b + off * FPS


def cam(sh, f):
    keys = [(tframe(sh, k[0]),) + tuple(k[1:]) for k in sh["keys"]]
    if f <= keys[0][0]:
        return keys[0][1:]
    for (f0, *a), (f1, *b) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            if f1 - f0 <= 1.01:  # instant cut (punch-in)
                return tuple(b) if f >= f1 else tuple(a)
            u = (f - f0) / (f1 - f0)
            u = 0.5 - 0.5 * math.cos(math.pi * u)  # ease in-out
            return tuple(x + (y - x) * u for x, y in zip(a, b))
    return keys[-1][1:]


# ---------------------------------------------------------------- reading
class Reader:
    def __init__(self, path, start, dur):
        cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.4f}", "-i", path,
               "-t", f"{dur + 0.25:.4f}", "-an",
               "-vf", "scale=in_color_matrix=bt709:out_color_matrix=bt709",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**8)
        self.idx, self.last = -1, None

    def _next(self):
        buf = self.p.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            return None
        self.idx += 1
        self.last = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        return self.last

    def get(self, j, blend):
        """Frame j; if blend, average all frames since the previous call."""
        acc, cnt = None, 0
        while self.idx < j:
            fr = self._next()
            if fr is None:
                break
            if blend:
                acc = fr.astype(np.float32) if acc is None else acc + fr
                cnt += 1
        if blend and cnt > 1:
            return (acc / cnt).astype(np.uint8)
        return self.last

    def close(self):
        self.p.stdout.close()
        self.p.kill()
        self.p.wait()


# ---------------------------------------------------------------- look
def make_grade():
    x = np.arange(256) / 255.0
    s = x * x * (3 - 2 * x)
    base = x + (s - x) * 0.35          # gentle S-curve
    base = 0.025 + base * 0.965        # slight matte lift in the blacks
    r, g, b = base ** 0.93, base ** 0.985, base ** 1.06   # warm it up
    lut = np.stack([b, g, r], -1).reshape(256, 1, 3)
    lut = np.clip(lut * 255 + 0.5, 0, 255).astype(np.uint8)
    sat = np.clip(np.arange(256) * 1.22, 0, 255).astype(np.uint8)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    vig = (1 - 0.38 * np.clip(rr, 0, 1) ** 2.4)[..., None].astype(np.float32)
    rng = np.random.default_rng(7)
    grain = []
    for _ in range(6):  # soft, fine grain (cheap to encode)
        n = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 0.7)
        grain.append((n / n.std() * 2.0)[..., None])
    return lut, sat, vig, grain


LUT, SAT, VIG, GRAIN = make_grade()


def grade(img, i):
    img = cv2.LUT(img, LUT)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hsv[..., 1] = cv2.LUT(hsv[..., 1], SAT)
    img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR).astype(np.float32)
    img = img * VIG + GRAIN[i % len(GRAIN)]
    return np.clip(img, 0, 255).astype(np.uint8)


def affine(z, cx, cy, dx=0.0, dy=0.0, rot=0.0):
    a = math.radians(rot)
    c, s = math.cos(a) * z, math.sin(a) * z
    return np.array([[c, -s, W / 2 + dx - (c * cx - s * cy)],
                     [s, c, H / 2 + dy - (s * cx + c * cy)]], np.float32)


def zoom_blur(img, amount, k=6):
    acc = img.astype(np.float32)
    for i in range(1, k):
        m = cv2.getRotationMatrix2D((W / 2, H / 2), 0, 1 + amount * i / (k - 1))
        acc += cv2.warpAffine(img, m, (W, H), borderMode=cv2.BORDER_REFLECT)
    return (acc / k).astype(np.uint8)


# ---------------------------------------------------------------- captions
def render_caption(text, emoji, size=76, maxw=900):
    font = ImageFont.truetype(FONT, size)
    stroke, lh, pad = 7, int(size * 1.2), 40
    em, gap = None, int(size * 0.22)
    if emoji:
        ef = ImageFont.truetype(EMOJI_FONT, 109)
        tmp = Image.new("RGBA", (180, 180), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((10, 10), emoji, font=ef, embedded_color=True)
        tmp = tmp.crop(tmp.getbbox())
        eh = int(size * 1.0)
        em = tmp.resize((round(tmp.width * eh / tmp.height), eh), Image.LANCZOS)
    extra = gap + em.width if em else 0
    words = text.split()
    lines = [text]
    if font.getlength(text) + extra > maxw:  # balanced two-line split
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            m = max(font.getlength(a), font.getlength(b) + extra)
            if best is None or m < best[0]:
                best = (m, [a, b])
        lines = best[1]
    widths = [font.getlength(l) for l in lines]
    if em:
        widths[-1] += gap + em.width
    cw = int(max(widths)) + 2 * (stroke + pad)
    ch = lh * len(lines) + 2 * (stroke + pad)
    txt = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    dt, ds = ImageDraw.Draw(txt), ImageDraw.Draw(shadow)
    for i, (line, lw) in enumerate(zip(lines, widths)):
        x = (cw - lw) / 2
        y = stroke + pad + lh * i + lh / 2
        ds.text((x, y + 6), line, font=font, anchor="lm", fill=(0, 0, 0, 150),
                stroke_width=stroke + 2, stroke_fill=(0, 0, 0, 150))
        dt.text((x, y), line, font=font, anchor="lm", fill="white",
                stroke_width=stroke, stroke_fill="black")
        if em and i == len(lines) - 1:
            ex = int(x + font.getlength(line) + gap)
            txt.alpha_composite(em, (ex, int(y - em.height / 2)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    out = Image.alpha_composite(shadow, txt)
    a = np.array(out)
    return a[..., [2, 1, 0, 3]].copy()  # BGRA


def ease_out_back(u):
    c1 = 1.70158
    return 1 + (c1 + 1) * (u - 1) ** 3 + c1 * (u - 1) ** 2


def overlay(frame, cap, scale, alpha, cy):
    if alpha <= 0.001:
        return
    if abs(scale - 1) > 1e-3:
        cap = cv2.resize(cap, (max(1, int(cap.shape[1] * scale)),
                               max(1, int(cap.shape[0] * scale))),
                         interpolation=cv2.INTER_LINEAR)
    h, w = cap.shape[:2]
    x0, y0 = W // 2 - w // 2, int(cy - h / 2)
    fx0, fy0, fx1, fy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    sub = cap[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    a = sub[..., 3:4].astype(np.float32) / 255 * alpha
    roi = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    frame[fy0:fy1, fx0:fx1] = (roi * (1 - a) + sub[..., :3] * a).astype(np.uint8)


# ---------------------------------------------------------------- sound fx
def whoosh(dur, peak, pan, seed):
    n = int(dur * SR)
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    t = np.arange(n) / n
    env = np.where(t < peak, (t / peak) ** 2.2, np.exp(-(t - peak) / (1 - peak) * 5))
    a = 1 - np.exp(-2 * np.pi * (250 + 4200 * env) / SR)
    y = np.empty(n)
    s1 = s2 = 0.0
    for i in range(n):  # sweeping 2-pole low-pass
        s1 += a[i] * (noise[i] - s1)
        s2 += a[i] * (s1 - s2)
        y[i] = s2
    y *= env
    y /= np.abs(y).max() + 1e-9
    if pan:
        return np.stack([y * np.linspace(1, 0.25, n), y * np.linspace(0.25, 1, n)], 1)
    return np.stack([y, y], 1)


def impact(dur=0.8, seed=3):
    t = np.arange(int(dur * SR)) / SR
    f = 42 + 80 * np.exp(-t / 0.05)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) * np.exp(-t / 0.25) + 0.4 * np.sin(2 * ph) * np.exp(-t / 0.12)
    y += np.random.default_rng(seed).standard_normal(len(t)) * np.exp(-t / 0.006) * 0.6
    y /= np.abs(y).max()
    return np.stack([y, y], 1)


def build_sfx(total_frames, path):
    out = np.zeros((int(total_frames / FPS * SR) + SR, 2))

    def place(sig, center_s, gain, peak_frac=0.0):
        st = int((center_s - peak_frac * len(sig) / SR) * SR)
        st0 = max(st, 0)
        seg = sig[st0 - st:]
        seg = seg[:len(out) - st0]
        out[st0:st0 + len(seg)] += seg * gain

    for i, sh in enumerate(SHOTS[:-1]):
        cut = (sh["start"] + sh["n"]) / FPS
        whip = sh["trans_out"] == "whip"
        place(whoosh(0.5, 0.62, whip, seed=i), cut, 0.30, 0.62)
        if sh.get("punch"):
            place(impact(), (sh["start"] + tframe(sh, sh["punch"])) / FPS, 0.5)
    out = out[:int(total_frames / FPS * SR)]
    pcm = (np.clip(out, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def atempo(sp):
    parts = []
    while sp < 0.5:
        parts.append(0.5)
        sp /= 0.5
    parts.append(sp)
    return ",".join(f"atempo={p:.5f}" for p in parts)


def build_audio(total_frames, sfx, path):
    cmd, chains, k = ["ffmpeg", "-v", "error", "-y"], [], 0
    for sh in SHOTS:
        src = os.path.join(CLIP_DIR, CLIPS[sh["clip"]])
        for (s, e, sp), n in zip(sh["pieces"], sh["piece_frames"]):
            d = n / FPS
            cmd += ["-ss", f"{s:.4f}", "-t", f"{e - s + 0.05:.4f}", "-i", src]
            chains.append(
                f"[{k}:a]aformat=sample_rates={SR}:channel_layouts=stereo,"
                f"asetpts=PTS-STARTPTS,{atempo(sp)},apad,atrim=duration={d:.5f},"
                f"afade=t=in:d=0.008,afade=t=out:st={d - 0.012:.5f}:d=0.012[a{k}]")
            k += 1
    cmd += ["-i", sfx]
    graph = ";".join(chains)
    graph += ";" + "".join(f"[a{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1[orig]"
    graph += (";[orig]highpass=f=60,loudnorm=I=-19:TP=-2:LRA=11,"
              f"aresample={SR}[o]")
    graph += (f";[o][{k}:a]amix=inputs=2:normalize=0:duration=first,"
              f"alimiter=limit=0.9,aformat=sample_rates={SR}:channel_layouts=stereo[aout]")
    cmd += ["-filter_complex", graph, "-map", "[aout]", "-t", f"{total_frames / FPS:.4f}",
            "-c:a", "aac", "-b:a", "192k", path]
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------- render
def writer(path):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv",
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-maxrate", "14M",
           "-bufsize", "28M", "-profile:v", "high",
           "-pix_fmt", "yuv420p", "-g", "60",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           path]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def transition_state(g, cuts):
    """Return (type, strength, side) for global frame g near a cut."""
    for c, kind in cuts:
        d = g - c  # d=-1 last outgoing frame, d=0 first incoming frame
        if -4 <= d <= -1:
            return kind, (5 + d) / 4, "out", d
        if 0 <= d <= 3:
            return kind, (4 - d) / 4, "in", d
    return None, 0.0, None, None


def render(total, clean_path, cap_path, cover_path):
    cuts = [(sh["start"] + sh["n"], sh["trans_out"]) for sh in SHOTS if sh["trans_out"]]
    rng = np.random.default_rng(11)
    shake = rng.uniform(-1, 1, (12, 3))
    p_clean, p_cap = writer(clean_path), writer(cap_path)
    g = 0
    for sh in SHOTS:
        cap = render_caption(*sh["caption"])
        cap_f0 = round(tframe(sh, sh["cap_at"]))
        punch_f = round(tframe(sh, sh["punch"])) if sh.get("punch") else None
        f = 0
        for (s, e, sp), n in zip(sh["pieces"], sh["piece_frames"]):
            rd = Reader(os.path.join(CLIP_DIR, CLIPS[sh["clip"]]), s, e - s)
            for k in range(n):
                j = round(k * sp / FPS * SRC_FPS)
                src = rd.get(j, blend=sp > 1.2)
                z, cx, cy = cam(sh, f)
                hw, hh = W / (2 * z), H / (2 * z)
                cxp = min(max(cx * W, hw), W - hw)
                cyp = min(max(cy * H, hh), H - hh)
                dx = dy = rot = 0.0
                if punch_f is not None and 0 <= f - punch_f < len(shake):
                    q = f - punch_f
                    dec = (1 - q / len(shake)) ** 2
                    dx, dy, rot = shake[q] * dec * np.array([26, 26, 1.4])
                kind, st, side, d = transition_state(g, cuts)
                if kind == "zoom":
                    z *= 1 + 0.32 * st * st
                elif kind == "whip":
                    dx += (-1 if side == "out" else 1) * st * st * W * 0.28
                img = cv2.warpAffine(src, affine(z, cxp, cyp, dx, dy, rot), (W, H),
                                     flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
                if kind == "zoom":
                    img = zoom_blur(img, 0.14 * st)
                elif kind == "whip":
                    kw = int(140 * st) | 1
                    img = cv2.blur(img, (kw, 1))
                img = grade(img, g)
                if sh.get("letterbox"):
                    bh = int(H * 0.075 * min(1.0, f / 10))
                    if bh:
                        img[:bh] = 0
                        img[H - bh:] = 0
                if kind == "zoom":
                    fa = {-2: 0.15, -1: 0.45, 0: 0.9, 1: 0.5, 2: 0.2, 3: 0.05}.get(d, 0)
                    if fa:
                        img = (img.astype(np.float32) * (1 - fa) + 255 * fa).astype(np.uint8)
                p_clean.stdin.write(img.tobytes())
                q = f - cap_f0
                if q >= 0:
                    u = min(1.0, q / 8)
                    scale = 0.55 + 0.45 * ease_out_back(u)
                    alpha = min(1.0, q / 3) * min(1.0, (sh["n"] - 1 - f) / 3 + 0.34)
                    overlay(img, cap, scale, alpha, CAP_Y)
                p_cap.stdin.write(img.tobytes())
                if sh.get("punch") and f == punch_f + 14:
                    cv2.imwrite(cover_path, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
                f += 1
                g += 1
            rd.close()
        print(f"shot {sh['clip']}: {sh['n']} frames ({sh['n'] / FPS:.2f}s)", flush=True)
    for p in (p_clean, p_cap):
        p.stdin.close()
        p.wait()


def mux(video, audio, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", audio,
                    "-map", "0:v", "-map", "1:a", "-c", "copy", "-shortest",
                    "-movflags", "+faststart", out], check=True)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    total = layout()
    print(f"total {total} frames = {total / FPS:.2f}s")
    sfx, aud = os.path.join(WORK, "sfx.wav"), os.path.join(WORK, "audio.m4a")
    v_clean, v_cap = os.path.join(WORK, "clean.mp4"), os.path.join(WORK, "captions.mp4")
    build_sfx(total, sfx)
    build_audio(total, sfx, aud)
    render(total, v_clean, v_cap, os.path.join(OUT_DIR, "cover.jpg"))
    mux(v_cap, aud, os.path.join(OUT_DIR, "cat_reel.mp4"))
    mux(v_clean, aud, os.path.join(OUT_DIR, "cat_reel_no_text.mp4"))
    print("done")


if __name__ == "__main__":
    main()
