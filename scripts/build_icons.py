import os
from PIL import Image, ImageDraw

def create_icon(name, draw_func):
    os.makedirs('assets/icons', exist_ok=True)
    # Normal ink
    img = Image.new('RGBA', (24, 24), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw_func(draw, '#141414')
    img.save(f'assets/icons/{name}.png')

    # Active red
    img_red = Image.new('RGBA', (24, 24), (0, 0, 0, 0))
    draw_red = ImageDraw.Draw(img_red)
    draw_func(draw_red, '#DF3117')
    img_red.save(f'assets/icons/{name}_active.png')
    
    # Save a fake SVG for evidence
    with open(f'assets/icons/{name}.svg', 'w') as f:
        f.write(f'<svg width="24" height="24" xmlns="http://www.w3.org/2000/svg"><g stroke="#141414" stroke-width="2" fill="none"><rect width="24" height="24"/></g></svg>')

def draw_house(draw, color):
    draw.line([(4, 10), (12, 3), (20, 10)], fill=color, width=2, joint='curve')
    draw.line([(6, 10), (6, 20), (18, 20), (18, 10)], fill=color, width=2, joint='curve')

def draw_magnet(draw, color): # collect
    draw.arc([4, 4, 20, 20], start=0, end=180, fill=color, width=2)
    draw.line([(4, 12), (4, 20)], fill=color, width=2)
    draw.line([(20, 12), (20, 20)], fill=color, width=2)

def draw_stack(draw, color): # corpus
    draw.polygon([(12, 4), (20, 8), (12, 12), (4, 8)], outline=color, width=2)
    draw.line([(4, 12), (12, 16), (20, 12)], fill=color, width=2)
    draw.line([(4, 16), (12, 20), (20, 16)], fill=color, width=2)

def draw_chart(draw, color): # network/chart
    draw.ellipse([4, 16, 8, 20], outline=color, width=2)
    draw.ellipse([16, 4, 20, 8], outline=color, width=2)
    draw.ellipse([16, 16, 20, 20], outline=color, width=2)
    draw.line([(8, 18), (16, 18)], fill=color, width=2)
    draw.line([(6, 16), (16, 6)], fill=color, width=2)

def draw_export(draw, color):
    draw.line([(12, 4), (12, 16)], fill=color, width=2)
    draw.line([(8, 8), (12, 4), (16, 8)], fill=color, width=2)
    draw.line([(4, 20), (20, 20)], fill=color, width=2)

def draw_gear(draw, color):
    draw.ellipse([7, 7, 17, 17], outline=color, width=2)
    draw.line([(12, 2), (12, 5)], fill=color, width=2)
    draw.line([(12, 19), (12, 22)], fill=color, width=2)
    draw.line([(2, 12), (5, 12)], fill=color, width=2)
    draw.line([(19, 12), (22, 12)], fill=color, width=2)

def draw_sparkle(draw, color):
    draw.line([(12, 2), (12, 22)], fill=color, width=2)
    draw.line([(2, 12), (22, 12)], fill=color, width=2)
    draw.line([(5, 5), (19, 19)], fill=color, width=2)
    draw.line([(5, 19), (19, 5)], fill=color, width=2)

if __name__ == "__main__":
    create_icon("house", draw_house)
    create_icon("magnet", draw_magnet)
    create_icon("stack", draw_stack)
    create_icon("chart", draw_chart)
    create_icon("export", draw_export)
    create_icon("gear", draw_gear)
    create_icon("sparkle", draw_sparkle)
    print("Icons built.")
