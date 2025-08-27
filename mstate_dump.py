#!/usr/bin/env python
# coding: utf-8

# (C) 2025 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License

import sys
from rvvts import MachineState

if len(sys.argv) != 2:
    print("Dump MachineState stored in json format")
    print("(C) 2025 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz\n")
    print("Usage: " + sys.argv[0] + " <MachineState json file>\n")
    sys.exit(1)

mstate = MachineState.load(sys.argv[1])
print(mstate)
