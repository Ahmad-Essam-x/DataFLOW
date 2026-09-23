import os
from PIL import Image, ImageDraw

def generate_app_icon(output_dir='assets', static_dir='static'):
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(static_dir, exist_ok=True)
    
    size = 512
    # Transparent canvas
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 1. Rounded container background
    margin = 24
    bg_box = [margin, margin, size - margin, size - margin]
    corner_radius = 100
    
    # Outer glow / shadow
    for offset in range(8, 0, -2):
        draw.rounded_rectangle(
            [margin - offset, margin - offset, size - margin + offset, size - margin + offset],
            radius=corner_radius + offset,
            fill=(2, 132, 199, int(15 * (1 - offset / 10)))
        )
    
    # Main dark slate surface
    draw.rounded_rectangle(bg_box, radius=corner_radius, fill=(15, 23, 42, 255), outline=(2, 132, 199, 255), width=10)
    
    # 2. Draw modern DataFlow pipeline graph: Left node, Center node, Right node
    # Line from Left to Center
    draw.line([(140, 256), (256, 180)], fill=(56, 189, 248, 255), width=14)
    draw.line([(140, 256), (256, 332)], fill=(56, 189, 248, 255), width=14)
    draw.line([(256, 180), (372, 256)], fill=(56, 189, 248, 255), width=14)
    draw.line([(256, 332), (372, 256)], fill=(56, 189, 248, 255), width=14)
    
    # Center pulse bar
    draw.line([(256, 180), (256, 332)], fill=(14, 165, 233, 200), width=8)
    
    # Draw Nodes (Circles)
    # Node 1: Input (Cyan)
    draw.ellipse([100, 216, 180, 296], fill=(14, 165, 233, 255), outline=(224, 242, 254, 255), width=8)
    draw.ellipse([126, 242, 154, 270], fill=(255, 255, 255, 255))
    
    # Node 2: Top Transform (Blue)
    draw.ellipse([216, 140, 296, 220], fill=(2, 132, 199, 255), outline=(186, 230, 253, 255), width=8)
    draw.ellipse([242, 166, 270, 194], fill=(255, 255, 255, 255))
    
    # Node 3: Bottom Transform (Violet/Indigo)
    draw.ellipse([216, 292, 296, 372], fill=(99, 102, 241, 255), outline=(224, 231, 255, 255), width=8)
    draw.ellipse([242, 318, 270, 346], fill=(255, 255, 255, 255))
    
    # Node 4: Output (Green/Emerald)
    draw.ellipse([332, 216, 412, 296], fill=(16, 185, 129, 255), outline=(209, 250, 229, 255), width=8)
    draw.ellipse([358, 242, 386, 270], fill=(255, 255, 255, 255))
    
    # Save PNG (256x256)
    png_256 = img.resize((256, 256), Image.Resampling.LANCZOS)
    png_path = os.path.join(output_dir, 'icon.png')
    png_256.save(png_path, 'PNG')
    
    # Save static favicon
    static_png = os.path.join(static_dir, 'icon.png')
    png_256.save(static_png, 'PNG')
    
    # Save multi-resolution ICO
    ico_path = os.path.join(output_dir, 'icon.ico')
    img.save(ico_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    
    print(f'[OK] Generated {png_path} and {ico_path}')
    return ico_path, png_path

if __name__ == '__main__':
    generate_app_icon()
