import re
with open('core/visualizer.py', 'r') as f:
    c = f.read()

if "plt.style.use" not in c:
    c = c.replace(
        "import matplotlib.pyplot as plt",
        "import matplotlib.pyplot as plt\nimport os\n\n_style_path = os.path.join(os.path.dirname(__file__), 'viz', 'blicsa.mplstyle')\nif os.path.exists(_style_path): plt.style.use(_style_path)"
    )

with open('core/visualizer.py', 'w') as f:
    f.write(c)

