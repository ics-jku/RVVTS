#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#


# TODO: I, V, (F,D) -- add random init of registers


from .ISG_Base import RandRegImmGenerator

# ## RISC-V FLOAT


class RVFRandRegImmGenerator(RandRegImmGenerator):
    def __init__(self):
        pass

    def get_freg(self, zero=True):
        if zero:
            min = 0
        else:
            min = 1
        return "f" + self.get_regnr(min, 31)
