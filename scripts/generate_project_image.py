#!/usr/bin/env python3
"""Generate docs/images/project.png for the sidetrack README hero."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "docs" / "images" / "project.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    width, height = 1280, 720
    img = Image.new("RGB", (width, height), "#0b1220")
    draw = ImageDraw.Draw(img)

    for y in range(height):
        t = y / height
        r = int(11 + t * 18)
        g = int(18 + t * 28)
        b = int(32 + t * 40)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    draw.rectangle([0, 0, 14, height], fill="#22d3ee")
    draw.rounded_rectangle(
        (48, 70, width - 48, height - 70),
        radius=28,
        fill="#111827",
        outline="#1f2937",
        width=2,
    )

    f_title = load_font(64, bold=True)
    f_sub = load_font(30)
    f_mono = load_font(24)
    f_small = load_font(20)
    f_badge = load_font(18, bold=True)

    draw.rounded_rectangle([88, 110, 250, 148], radius=12, fill="#164e63")
    draw.text((108, 118), "OPEN SOURCE", fill="#67e8f9", font=f_badge)
    draw.text((88, 170), "sidetrack", fill="#f8fafc", font=f_title)
    draw.text(
        (88, 250),
        "Sensible git worktree manager for multi-branch work",
        fill="#94a3b8",
        font=f_sub,
    )

    term = (88, 320, width - 88, height - 120)
    draw.rounded_rectangle(term, radius=18, fill="#020617", outline="#334155", width=2)
    for i, color in enumerate(["#ef4444", "#f59e0b", "#22c55e"]):
        x = 120 + i * 28
        draw.ellipse([x, 340, x + 14, 354], fill=color)

    lines = [
        ("$ ", "#64748b", "sidetrack add fix/login", "#e2e8f0"),
        ("", "", "  created worktree ../repo-worktrees/fix-login", "#67e8f9"),
        ("$ ", "#64748b", "sidetrack list", "#e2e8f0"),
        ("", "", "  main          .                 clean", "#a7f3d0"),
        ("", "", "  fix/login     ../.../fix-login  dirty", "#fde68a"),
        ("$ ", "#64748b", "sidetrack go fix/login", "#e2e8f0"),
    ]

    y = 380
    for prefix, prefix_color, text, text_color in lines:
        if prefix:
            draw.text((120, y), prefix, fill=prefix_color, font=f_mono)
            tw = draw.textlength(prefix, font=f_mono)
            draw.text((120 + tw, y), text, fill=text_color, font=f_mono)
        else:
            draw.text((120, y), text, fill=text_color, font=f_mono)
        y += 36

    draw.text(
        (88, height - 100),
        "Use cases: PR review mid-feature · hotfix without stash · parallel agent checkouts",
        fill="#64748b",
        font=f_small,
    )

    img.save(out, "PNG", optimize=True)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
