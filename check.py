from pathlib import Path

files = [
    'prompts/analyse_bug.txt',
    'prompts/analyse_feature.txt',
    'prompts/review_diff.txt',
    'prompts/generate_pr.txt',
    'pipeline/analyser.py',
    'pipeline/understander.py',
]

for f in files:
    p = Path(f)
    if p.exists():
        size = p.stat().st_size
        status = "EMPTY" if size == 0 else f"{size} bytes"
    else:
        status = "MISSING"
    print(f"{status:>12}  {f}")