"""Compile only the shipped public wordmark into SSD1306 page-order pixels."""
from pathlib import Path
import sys
from PIL import Image


def frame_bytes(source):
    with Image.open(source) as image:
        logo = image.convert("RGBA")
    logo.thumbnail((120, 56), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (128, 64), (0, 0, 0, 255))
    canvas.alpha_composite(logo, ((128 - logo.width) // 2, (64 - logo.height) // 2))
    pixels = canvas.convert("L")
    return bytes(
        sum((pixels.getpixel((x, page * 8 + bit)) >= 128) << bit for bit in range(8))
        for page in range(8) for x in range(128)
    )


def generate(source, destination):
    frame = frame_bytes(source)
    if len(frame) != 1024 or not any(frame) or all(byte == 255 for byte in frame):
        raise ValueError("Expected a visible public 128x64 wordmark.")
    rows = [
        "    " + ", ".join(f"0x{byte:02x}" for byte in frame[i:i + 16]) + ","
        for i in range(0, len(frame), 16)
    ]
    Path(destination).write_text(
        "/* Generated public logo; SSD1306 page order. No wallet data. */\n"
        "static const unsigned char satooshi_logo_frame[1024] __initconst = {\n"
        + "\n".join(rows) + "\n};\n",
        encoding="ascii",
    )


if __name__ == "__main__":
    generate(sys.argv[1], sys.argv[2])
