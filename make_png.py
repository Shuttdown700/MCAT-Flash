import sys
from PIL import Image, ImageFont, ImageDraw

# Set the font size
FONT_SIZE = 32

def create_label(text):
    # Create a new image with white background
    img = Image.new('RGB', (306, 34), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Load a font with the specified size
    font = ImageFont.truetype("/Library/Fonts/Arial.ttf", FONT_SIZE)

    # Calculate text position
    text_x = 5  # Adjust as needed
    text_y = 5  # Adjust as needed

    # Draw text on image
    draw.text((text_x, text_y), text, fill=(0, 0, 0), font=font)

    # Save the image
    img.save("label.png")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py 'Your text here'")
        sys.exit(1)

    text = sys.argv[1]
    create_label(text)
