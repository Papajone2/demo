"""Render real firmware OLED layouts using public sample values, never a vault."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from satooshi.rehearsal import Rehearsal
from satooshi.screen import Screen


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dist/oled-preview.png")
    args = parser.parse_args()
    renderer = Screen()
    samples = [
        ("Welcome", ("SATOOSHI START", [], ""), dict(phase="home")),
        ("Home - no arrows", ("SATOOSHI PRO", ["Unlocked"], ""), dict(phase="home")),
        ("Device pairing", ("Connect wallet?", ["Satooshi web wallet", "Hold right to pair", "Left to decline"], ""), dict(phase="pair")),
    ]
    p = dict(operation="swap", amount="10", symbol="TRX",
             address="T111111111111111111111111111111111", fee="1.2", feeSymbol="TRX",
             network="Tron", receiveAmount="0.00001", receiveSymbol="BTC")
    pages = Rehearsal(p).pages()
    for i, page in enumerate(pages):
        samples.append(("Swap review %d/%d" % (i + 1, len(pages)), (*page, ""),
                        dict(phase="preview_review", step=i, steps=len(pages), simulated=True,
                             review_confirmed=i == len(pages) - 1)))
    samples += [
        ("Holding right - 50%", (*pages[-1], ""), dict(phase="preview_review", step=4, steps=5,
              simulated=True, review_confirmed=True, pressed=(False, True), progress=0.5)),
        ("Approval complete", ("Approval complete", ["No funds moved"], ""), dict(phase="success")),
        ("Computer message", ("From computer", ["Welcome to Satooshi.", "Your device is ready."], ""), dict(phase="message")),
        ("PIN - device only", ("Choose PIN", ["****", "> 5"], ""), dict(phase="pin")),
    ]
    canvas = Image.new("RGB", (1200, 4 * 254), "#111315")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 13)
    for i, (label, screen, options) in enumerate(samples):
        x, y = (i % 3) * 400 + 8, (i // 3) * 254 + 12
        draw.text((x + 6, y), label, fill="#d6d8da", font=font)
        oled = renderer.render(screen, **options).resize((384, 192), Image.Resampling.NEAREST).convert("RGB")
        canvas.paste(oled, (x, y + 26))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(str(out))


if __name__ == "__main__":
    run()
