from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    output = project / "assets" / "posture_companion.ico"
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 10, 246, 246), radius=62, fill="#5B5FEF")
    draw.ellipse((99, 44, 157, 102), fill="white")
    draw.line((128, 105, 128, 184), fill="white", width=24)
    draw.arc((70, 106, 186, 214), 190, 350, fill="white", width=20)
    image.save(output, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(output)


if __name__ == "__main__":
    main()
