"""Deal Darwin creative loop: overlay brand elements on Firefly concepts,
score each with Drex Max (R1-R5 noul questions, image attached), pick the
winner, then validate the checker on the labeled dev split.

Run: python3 -m app.creative_loop
Drex image format (docs/drex/guides/drex-max): top-level JSON field
"images": ["data:image/jpeg;base64,..."] (inline data URL, <=8 images,
4 MiB body limit). Questions reference the image as "Image 1".
"""
import base64
import csv
import io
import json
import os
import time
import urllib.error
import urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app import drex_client  # noqa: F401  (importing it loads NACE_API_KEY from .env)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://console.nace.ai/v1/systemone"
MODEL = "drex-max-v1.1"
FIRE = os.path.join(ROOT, "creative", "firefly")
ADS = os.path.join(ROOT, "creative", "images")
LABELS = os.path.join(ROOT, "creative", "creative_labels.csv")
TEMPLATES = os.path.join(ROOT, "scripts", "drex_question_templates.json")
CACHE = os.path.join(ROOT, "app", "cache", "creative_scores.json")
FONT_BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

NAVY, ORANGE, OFFWHITE, SLATE = (11, 37, 69), (255, 107, 26), (246, 243, 238), (92, 107, 122)
RULE_IDS = ["R1", "R2", "R3", "R4", "R5"]
RULE_COLS = {"R1": "R1_logo_ok", "R2": "R2_palette_ok", "R3": "R3_disclosure_ok",
             "R4": "R4_competitor_ok", "R5": "R5_safe_zone_ok"}


def rules():
    tpl = json.load(open(TEMPLATES))["creative_rule"]
    return {rid: tpl["question"].format(rule_text=txt) for rid, txt in tpl["rules"].items()}


# ---------- Drex calls with image ----------

def ask_image(image_path, questions, state="Image 1 is an ad concept."):
    """Drex Max with the image attached (inline JPEG data URL). Returns the raw answers dict."""
    key = os.environ.get("NACE_API_KEY")
    if not key:
        raise RuntimeError("NACE_API_KEY not set")
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        im.thumbnail((1024, 1440))  # keep body under the 4 MiB inline limit
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
    data = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    body = json.dumps({"model": MODEL, "state": state, "images": [data], "questions": questions}).encode()
    req = urllib.request.Request(
        URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        return drex_client.send(req, timeout=90)["answers"]  # shared backoff + 4-call cap
    except drex_client.NaceError as e:
        raise RuntimeError(f"Drex {e}")


def ask_rules(image_path):
    """Ask all five rule questions about one image; returns {rid: p_yes}."""
    questions = {rid: {"type": "noul", "instructions": "Inspect Image 1. " + txt} for rid, txt in rules().items()}
    answers = ask_image(image_path, questions, "Image 1 is a Northwind ad concept.")
    return {rid: answers[rid]["noul"] for rid in RULE_IDS}


def iter_scores(paths):
    """Yield {"name", "prob", "p_pass_product", "p_pass_min"} per image, scored live by Drex Max."""
    for name, path in paths:
        probs = ask_rules(path)
        prod = 1.0
        for r in RULE_IDS:
            prod *= probs[r]
        yield {"name": name, "prob": probs, "p_pass_product": prod, "p_pass_min": min(probs.values())}


# ---------- Overlay step ----------

def _bright(img, box):
    """Mean luminance of a region (fraction coords), 0..1."""
    w, h = img.size
    crop = img.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    px = list(crop.convert("L").getdata())
    return (sum((v / 255) ** 2.2 for v in px) / len(px)) if px else 0.5


def overlay(src, dst):
    # Center-crop to 4:5 and resize to 720x900 so every concept gets the same overlay scale.
    img = ImageOps.fit(Image.open(src).convert("RGB"), (720, 900), Image.LANCZOS, centering=(0.5, 0.5))
    d = ImageDraw.Draw(img)
    w, h = img.size
    pad = int(0.035 * min(w, h))

    # Headline "RUN THE BLOCK" in the top third
    top_bg = _bright(img, (0, 0, 1, 0.4))
    color = NAVY if top_bg > 0.45 else OFFWHITE
    size = int(0.052 * h)
    font = ImageFont.truetype(FONT_BLACK, size)
    text = "RUN THE BLOCK"
    tw = d.textlength(text, font=font)
    d.text(((w - tw) / 2, 0.13 * h), text, font=font, fill=color)

    # Logo top right: triangle + NORTHWIND, width >= 22% of image width
    logo_bg = _bright(img, (0.55, 0, 1, 0.25))
    lcolor = NAVY if logo_bg > 0.45 else OFFWHITE
    fs = int(0.045 * h)
    while fs < int(0.10 * h):
        f = ImageFont.truetype(FONT_BLACK, fs)
        b = f.getbbox("NORTHWIND")
        tri_h, gap = int(1.2 * (b[3] - b[1])), int(0.008 * w)
        lw = tri_h + gap + (b[2] - b[0])
        if lw >= 0.23 * w:
            break
        fs += max(1, int(0.004 * h))
    f = ImageFont.truetype(FONT_BLACK, fs)
    b = f.getbbox("NORTHWIND")
    tri_h, gap = int(1.2 * (b[3] - b[1])), int(0.008 * w)
    lw = tri_h + gap + (b[2] - b[0])
    lx, ly = w - pad - lw, pad
    d.polygon([(lx + tri_h, ly), (lx, ly + tri_h), (lx + tri_h * 0.5, ly + tri_h)], fill=ORANGE)
    d.text((lx + tri_h + gap, ly - b[1]), "NORTHWIND", font=f, fill=lcolor)

    # "#ad" top left, at least 2.5% of image height tall
    ad_bg = _bright(img, (0, 0, 0.35, 0.15))
    acolor = NAVY if ad_bg > 0.45 else OFFWHITE
    afs = int(0.035 * h)
    af = ImageFont.truetype(FONT_BOLD, afs)
    d.text((pad, pad), "#ad", font=af, fill=acolor)

    img.save(dst)
    return dst


# ---------- Run ----------

def fmt_row(name, probs):
    cells = " ".join(f"{probs[r]:5.2f}" for r in RULE_IDS)
    prod = 1.0
    for r in RULE_IDS:
        prod *= probs[r]
    return f"{name:10s} {cells}  {prod:6.3f}  {min(probs[r] for r in RULE_IDS):5.2f}"


def main():
    # 1. Overlay
    finals = []
    for i in sorted(int(f.split("_")[1].split(".")[0])
                    for f in os.listdir(FIRE) if f.startswith("concept_")):
        src = os.path.join(FIRE, f"concept_{i}.png")
        dst = os.path.join(FIRE, f"final_{i}.png")
        overlay(src, dst)
        finals.append((f"final_{i}", dst))
        print(f"overlay: {src} -> {dst}")

    # 2. Check with Drex Max
    scores = {"model": MODEL, "concepts": {}}
    for name, path in finals:
        probs = ask_rules(path)
        prod = 1.0
        for r in RULE_IDS:
            prod *= probs[r]
        scores["concepts"][name] = {
            "image": os.path.relpath(path, ROOT),
            "prob": {r: probs[r] for r in RULE_IDS},
            "p_pass_product": prod,
            "p_pass_min": min(probs[r] for r in RULE_IDS),
            "pass": all(probs[r] >= 0.5 for r in RULE_IDS),
        }
        print(f"scored {name}: {fmt_row(name, probs)}")
    winner = max(scores["concepts"], key=lambda k: scores["concepts"][k]["p_pass_product"])
    scores["winner"] = winner
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(scores, open(CACHE, "w"), indent=2)

    # 3. Table + winner
    print("\nconcept " + " ".join(RULE_IDS) + "   p_prod  p_min")
    for name in scores["concepts"]:
        print(fmt_row(name, scores["concepts"][name]["prob"]))
    print(f"\nWINNER: {winner} "
          f"(p_prod={scores['concepts'][winner]['p_pass_product']:.3f}, "
          f"all_rules_pass={scores['concepts'][winner]['pass']})")

    # 4. Validate checker on dev split
    rows = [r for r in csv.DictReader(open(LABELS)) if r["split"] == "dev"]
    correct = {r: 0 for r in RULE_IDS}
    for row in rows:
        probs = ask_rules(os.path.join(ADS, os.path.basename(row["filename"])))
        for rid in RULE_IDS:
            correct[rid] += int(probs[rid] >= 0.5) == int(row[RULE_COLS[rid]])
        print(f"dev {row['filename']}: " + " ".join(f"{probs[r]:.2f}" for r in RULE_IDS)
              + "  labels: " + "".join(row[RULE_COLS[r]] for r in RULE_IDS))
    n = len(rows)
    json.dump({"split": "dev", "n": n, "threshold": 0.5, "model": MODEL, "correct": correct},
              open(os.path.join(os.path.dirname(CACHE), "creative_validation.json"), "w"), indent=2)
    print(f"\nPer-rule accuracy on dev split (n={n}, threshold p>=0.5):")
    for rid in RULE_IDS:
        print(f"  {rid}: {correct[rid]}/{n} = {correct[rid]/n:.3f}")


if __name__ == "__main__":
    main()
