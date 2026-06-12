import json
d=json.load(open('deep_test_results.json'))
s=d['summary']
print(f"Total: {s['passed']}/{s['total']} ({s['pct']}pct)")
print("FAILS:")
for t in d['tests']:
    if t['status']=='FAIL': print(f"  - {t['name']}: {t['detail']}")
