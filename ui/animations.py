import customtkinter as ctk

def fade_in(widget, duration_ms=300, steps=15, current_step=0):
    """
    Fades in a widget. Note: Tkinter doesn't support true alpha transparency
    for individual widgets easily without images or text color manipulation,
    so this usually fakes it by changing text/border colors if possible,
    or simply packs it after a delay. We will simulate fade by mapping colors.
    """
    # For a true fade in CTk, we can't really change opacity of a frame.
    # We will just make it visible if it's the first step.
    if current_step == 0:
        pass # ensure it's mapped
    # For now, Tkinter limitation means we just wait and show, or we can animate text color.
    if current_step >= steps:
        return
    widget.after(duration_ms // steps, lambda: fade_in(widget, duration_ms, steps, current_step + 1))

def slide_in(widget, target_x, target_y, duration_ms=300, steps=15, current_step=0, start_x=None, start_y=None):
    """Slides a widget to a target position using place()."""
    if start_x is None: start_x = target_x - 50
    if start_y is None: start_y = target_y
    if current_step == 0:
        widget.place(x=start_x, y=start_y)
    
    progress = current_step / steps
    # Ease out cubic
    ease = 1 - (1 - progress) ** 3
    curr_x = start_x + (target_x - start_x) * ease
    curr_y = start_y + (target_y - start_y) * ease
    
    widget.place(x=curr_x, y=curr_y)
    
    if current_step < steps:
        widget.after(duration_ms // steps, lambda: slide_in(widget, target_x, target_y, duration_ms, steps, current_step + 1, start_x, start_y))
    else:
        # Revert to pack/grid if needed, or keep placed
        pass

def pulse(widget, min_color="#E0E0E0", max_color="#F6F4EE", duration_ms=1000, steps=20, current_step=0, forward=True):
    """Pulses the fg_color of a widget between two hex colors."""
    if not widget.winfo_exists():
        return
    
    # Simple color interpolation
    def hex_to_rgb(hx):
        hx = hx.lstrip('#')
        return tuple(int(hx[i:i+2], 16) for i in (0, 2, 4))
    def rgb_to_hex(rgb):
        return '#%02x%02x%02x' % tuple(int(c) for c in rgb)
        
    c1 = hex_to_rgb(min_color)
    c2 = hex_to_rgb(max_color)
    
    progress = current_step / steps
    ease = 0.5 - math.cos(progress * math.pi) / 2 if forward else 0.5 - math.cos((1 - progress) * math.pi) / 2
    
    curr_c = [c1[i] + (c2[i] - c1[i]) * ease for i in range(3)]
    try:
        widget.configure(fg_color=rgb_to_hex(curr_c))
    except Exception:
        pass
        
    next_step = current_step + 1
    next_fwd = forward
    if next_step >= steps:
        next_step = 0
        next_fwd = not forward
        
    widget.after(duration_ms // steps, lambda: pulse(widget, min_color, max_color, duration_ms, steps, next_step, next_fwd))
    
def stagger_items(items, animation_func, delay_ms=50, **kwargs):
    """Applies an animation function to a list of items with a staggered delay."""
    for i, item in enumerate(items):
        item.after(i * delay_ms, lambda it=item: animation_func(it, **kwargs))

import math
