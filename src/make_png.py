import os
import sys

from PIL import Image, ImageDraw, ImageFont

from logger import get_app_logger


script_logger = get_app_logger('make_png', 'make_png.log')

# Set the font size
FONT_SIZE = 32


def get_font_path():
    """Returns the correct Arial font path based on the operating system."""
    if os.name == 'nt':  # Windows
        # Pillow automatically checks C:\Windows\Fonts for this
        return "arial.ttf"
    elif sys.platform == 'darwin':  # macOS
        return "/Library/Fonts/Arial.ttf"
    else:  # Linux (Fallback)
        return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def create_label(text):
    script_logger.info(f"Generating label PNG for: '{text}'")
    
    try:
        # Create a new image with white background
        img = Image.new('RGB', (306, 34), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Load a font dynamically based on the OS
        font_path = get_font_path()
        try:
            font = ImageFont.truetype(font_path, FONT_SIZE)
        except IOError:
            script_logger.warning(
                f"Could not load font {font_path}. Using safe default fallback."
            )
            font = ImageFont.load_default()

        # Calculate text position
        text_x = 5  # Adjust as needed
        text_y = 5  # Adjust as needed

        # Draw text on image
        draw.text((text_x, text_y), text, fill=(0, 0, 0), font=font)

        # Save the image
        img.save("label.png")
        script_logger.info(f"Successfully generated label.png for text: '{text}'")
        
    except Exception as e:
        script_logger.critical(f"CRITICAL ERROR generating PNG label: {e}")
        sys.exit(1)  # Tell the parent process that this script failed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        script_logger.error("make_png.py was called without text arguments.")
        sys.exit(1)

    label_text = sys.argv[1]
    create_label(label_text)