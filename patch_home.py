import re

with open('main.py', 'r') as f:
    content = f.read()

# Add "home": self._build_tab_home() to _tabs
if '"home"' not in content:
    content = content.replace(
        '"import":  self._build_tab_import(),',
        '"home":    self._build_tab_home(),\n            "import":  self._build_tab_import(),'
    )
    # Also change self._switch_tab("import") to self._switch_tab("home")
    content = content.replace('self._switch_tab("import")', 'self._switch_tab("home")')

    # Add navigation button for home
    content = content.replace(
        '("import",  "📂", "tab_import"),',
        '("home",    "🏠", "menu_home"),\n            ("import",  "📂", "tab_import"),'
    )

with open('main.py', 'w') as f:
    f.write(content)
