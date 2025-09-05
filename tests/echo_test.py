# expects artifacts/out.txt to contain the word "SUCCESS"
import sys, pathlib
p = pathlib.Path("artifacts/out.txt")
sys.exit(0 if p.exists() and "SUCCESS" in p.read_text() else 1)