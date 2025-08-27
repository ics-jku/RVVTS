#!/usr/bin/env python
# coding: utf-8

# (C) 2025 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License

import sys
from rvvts import MachineState

argvalid = False
diff_full = False
mstateA_filename = None
mstateB_filename = None
if len(sys.argv) == 3:
    argvalid = True
    mstateA_filename = sys.argv[1]
    mstateB_filename = sys.argv[2]
elif len(sys.argv) == 4 and sys.argv[1] == "-f":
    argvalid = True
    diff_full = True
    mstateA_filename = sys.argv[2]
    mstateB_filename = sys.argv[3]

if not argvalid:
    print("Diff MachineStates stored in json format")
    print("(C) 2025 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz\n")
    print("Usage: " + sys.argv[0] + "[-f] <MachineState A json file> <MachineState B json file>")
    print("  -f .. show all state elements (difference is marked with 'X')")
    print("")
    sys.exit(1)

mstateA = MachineState.load(mstateA_filename)
mstateB = MachineState.load(mstateB_filename)
diff = mstateA.compare(mstateB, diff_full = diff_full)
print(diff[1])
print("STATES DIFFER: " + str(not diff[0]))
