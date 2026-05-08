import os
import sys

from PIL import Image, ImageDraw, ImageFont

from logger import get_app_logger

script_logger = get_app_logger('make_png', 'make_png.log')

def get_font_path():
    """Returns a valid font path, checking common Linux directories."""
    if os.name == 'nt':  # Windows
        return "arial.ttf"
    elif sys.platform == 'darwin':  # macOS
        return "/Library/Fonts/Arial.ttf"
    else:  # Linux / Raspberry Pi
        # Try multiple common Pi fonts to ensure we get one that scales
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return "arial.ttf"  # Absolute fallback

def get_text_size(text_string, font):
    """Safely calculates text dimensions regardless of the Pillow version."""
    if hasattr(font, 'getbbox'):
        # Modern Pillow (v10+)
        bbox = font.getbbox(text_string)
        horizontal = bbox[2] - bbox[0]
        vertical = bbox[3] - bbox[1]
        # is right, is left | is bottom, is top
        return horizontal, vertical
        
    elif hasattr(font, 'getsize'):
        # Legacy Pillow (v9 and older)
        return font.getsize(text_string)
    else:
        # Nuclear fallback for bitmap fonts
        return font.getmask(text_string).size

def create_label(text):
    script_logger.info(f"Generating dynamic label PNG for: '{text}'")
    try:
        TARGET_WIDTH = 306
        MIN_HEIGHT = 100  # 0.5 inches: Published Hardware minimum to prevent red light errors
        
        font_path = get_font_path()
        font_size = 10
        # 1. Load the TrueType font safely
        font_loaded = False
        try:
            font = ImageFont.truetype(font_path, font_size)
            font_loaded = True
        except Exception as e:
            script_logger.warning(f"Could not load TrueType font from {font_path}: {e}")
            font = ImageFont.load_default()

        # 2. Dynamically scale the font size (only if we have a scalable TrueType font)
        if font_loaded:
            while True:
                text_width, text_height = get_text_size(text, font)
                # Stop growing when the text is 20 pixels away from the edges
                if text_width >= (TARGET_WIDTH - 20):
                    break
                
                font_size += 1
                font = ImageFont.truetype(font_path, font_size)
        else:
            # Default bitmap fonts cannot be scaled, just measure it once
            text_width, text_height = get_text_size(text, font)
        # 2. Shrink the canvas height to wrap the text tightly, honoring MIN_HEIGHT
        canvas_height = max(MIN_HEIGHT, text_height + 20)
        
        # 3. Generate the actual printable canvas
        img = Image.new('RGB', (TARGET_WIDTH, canvas_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # 4. Center the text perfectly
        x = (TARGET_WIDTH - text_width) // 2
        y = (canvas_height - text_height) // 2

        draw.text((x, y), text, fill=(0, 0, 0), font=font)
        
        img.save("label.png")
        script_logger.info(
            f"Dynamic label generated -> Width: {TARGET_WIDTH}px, Height: {canvas_height}px"
        )
        
    except Exception as e:
        script_logger.critical(f"CRITICAL ERROR generating PNG label: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        script_logger.error("make_png.py was called without text arguments.")
        sys.exit(1)

    # Join all arguments to handle room names with spaces
    label_text = sys.argv[1]
    create_label(label_text)