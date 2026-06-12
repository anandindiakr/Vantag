import os, re
fixed = 0
for root, dirs, files in os.walk('.'):
    if 'venv' in root or '__pycache__' in root:
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        p = os.path.join(root, f)
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                s = fh.read()
        except Exception:
            continue
        n = re.sub(r'from backend\.', 'from ', s)
        n = re.sub(r'import backend\.', 'import ', n)
        if n != s:
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write(n)
            fixed += 1
            print('fixed', p)
print('total', fixed)
