import re

with open('main.py', 'r') as f:
    c = f.read()

# Update sidebar buttons
c = re.sub(
    r'btn = ctk\.CTkButton\(\s*sb, text=f"\{icon\}  \{label\}", anchor="w",\s*font=ctk\.CTkFont\(size=13\),\s*fg_color="transparent", hover_color=\("\#d0d0ea", "\#1a1a35"\),\s*text_color=\("gray10", "white"\), corner_radius=0, height=44,',
    'btn = ctk.CTkButton(sb, text=f"{icon}  {label}", anchor="w", font=ctk.CTkFont(size=13, weight="bold"), fg_color="transparent", hover_color="#e0e0e0", text_color=INK, corner_radius=0, height=44, border_width=0, border_color=RED,',
    c
)

c = re.sub(
    r'btn\.configure\(fg_color=ACCENT if active else "transparent",\s*text_color="\#000" if active else \("gray10", "white"\)\)',
    'btn.configure(border_width=6 if active else 0, font=ctk.CTkFont(size=13, weight="bold" if active else "normal"))',
    c
)

# Update progress bar
c = re.sub(
    r'self\._progress_bar = ctk\.CTkProgressBar\(sb, mode="indeterminate", height=5,\s*progress_color=ACCENT, fg_color=CARD2_BG\)',
    'self._progress_bar = ctk.CTkProgressBar(sb, mode="indeterminate", height=5, progress_color=YELLOW, fg_color=PAPER, border_width=1, border_color=INK, corner_radius=0)',
    c
)

with open('main.py', 'w') as f:
    f.write(c)

# Fix components dialog borders
with open('ui/components.py', 'r') as f:
    cc = f.read()
cc = re.sub(r'fg_color=CONTENT_BG\)', 'fg_color=CONTENT_BG, border_width=3, border_color=INK)', cc)
with open('ui/components.py', 'w') as f:
    f.write(cc)
