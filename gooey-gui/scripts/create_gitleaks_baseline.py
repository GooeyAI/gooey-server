#!/usr/bin/env python3

import subprocess
import json

# create a baseline file
subprocess.run(
    ["gitleaks", "detect", "--report-path", "gitleaks-baseline.json"],
)

# parse the baseline file
with open("gitleaks-baseline.json") as f:
    baseline = json.load(f)

# output list of "Fingerprint"s to .gitleaksignore
with open(".gitleaksignore", "w") as f:
    for leak in baseline:
        f.write(leak["Fingerprint"] + "\n")
