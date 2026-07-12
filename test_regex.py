import re
with open("assets/map.js", "r") as f: map_js = f.read()
res = re.sub(r'const response = await fetch\("graph\.json"\);.*?data = await response\.json\(\);', 'data = {};', map_js, flags=re.DOTALL)
print("Before len:", len(map_js))
print("After len:", len(res))
if "fetch" in res: print("Fetch still present!")
