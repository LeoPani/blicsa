import re

with open("main.py", "r") as f:
    content = f.read()

# For _rank_tree insertions
content = re.sub(
    r'(self._rank_tree\.insert\("", "end", values=\(.*?\))(?!, tags=)', 
    r'\1, tags=("striped",) if i % 2 == 0 else ()', 
    content
)

# For _data_tree insertions (in _refresh_data_view)
content = re.sub(
    r'(self._data_tree\.insert\("", "end", values=\(.*?\))(?!, tags=)', 
    r'\1, tags=("striped",) if i % 2 == 0 else ()', 
    content
)

with open("main.py", "w") as f:
    f.write(content)
