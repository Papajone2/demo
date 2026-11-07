"""Render real firmware OLED layouts using public sample values, never a vault."""
import argparse
import math
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
        ("Instant splash - logo only", ("SATOOSHI LOGO", [], ""), dict(phase="home")),
        ("Ready to connect", ("SATOOSHI START", [], ""), dict(phase="home")),
        ("Connected home", ("SATOOSHI LOGO", [], ""), dict(phase="home")),
        ("Open device wallet", ("Open wallet?", ["Confirm on device"], ""), dict(phase="wallet_open")),
        ("Create / Recover", ("Set up Satooshi", ["Choose your wallet"], ""), dict(phase="setup_confirm")),
        ("Recovery word", ("Word 1 of 24", ["abandon"], "Next word"), dict(phase="backup")),
        ("Review all 24 words", ("Check word 1/24", ["abandon"], "Next word"),
         dict(phase="quiz", progress=.55, pressed=(False, True))),
        ("Restore on device", ("Restore word 1/24", ["abandon"], "Hold right 1s"), dict(phase="recover")),
        ("Optional PIN", ("Set a PIN?", ["Protect this device"], ""), dict(phase="pin_choice")),
        ("PIN: tap to move", ("Choose PIN", ["**", "5"], "Hold right 1s"),
         dict(phase="pin", progress=.65, pressed=(False, True))),
    ]
    p = dict(operation="send", amount="10", symbol="TRX",
             address="T111111111111111111111111111111111", fee="1.2", feeSymbol="TRX",
             network="tron-mainnet")
    pages = Rehearsal(p).pages()
    for i, page in enumerate(pages):
        samples.append(("Real browser payment %d/%d" % (i + 1, len(pages)), (*page, ""),
                        dict(phase="browser_review_release", step=i, steps=len(pages),
                             review_confirmed=i == len(pages) - 1)))
    samples += [
        ("Receive: review every page", ("Verify address", ["Solana", "111111111111111111", "111111111111111111"], "Next"),
         dict(phase="receive_address")),
        ("Approval acknowledged", ("Payment approved", ["Return to wallet"], ""), dict(phase="success")),
    ]
    canvas = Image.new("RGB", (1200, math.ceil(len(samples) / 3) * 254), "#111315")
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
