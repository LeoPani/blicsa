import os
from PIL import Image

def generate_icons():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    
    input_image_path = os.path.join(project_root, 'assets', 'branding', 'blicsa-icon-256.png')
    output_dir = os.path.join(base_dir, 'icons')
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    if not os.path.exists(input_image_path):
        print(f"Error: Input image not found at {input_image_path}")
        return
        
    try:
        with Image.open(input_image_path) as img:
            sizes = [16, 32, 48, 128]
            for size in sizes:
                resized_img = img.resize((size, size), Image.Resampling.LANCZOS)
                output_path = os.path.join(output_dir, f'icon-{size}.png')
                resized_img.save(output_path, format='PNG')
                print(f"Generated {output_path}")
    except Exception as e:
        print(f"Failed to generate icons: {e}")

if __name__ == "__main__":
    generate_icons()
