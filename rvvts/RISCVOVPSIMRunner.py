#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import ProcessTimeoutRunner


class RISCVOVPSIMRunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        # create command
        rvisacfg = config["rvisacfg"]
        variant = f"RV{rvisacfg.get_xlen()}GC"

        # NOTE: riscvovpsim does not support RV32GCBV -> however, the metric for B is based on a very
        # old standard and therefore worthless anyways -> so ignore B
        # if rvisacfg.is_under_test("b"):
        #    variant = variant + "B"
        if rvisacfg.is_under_test("v"):
            variant = variant + "V"
        self.base_parameters = [config["riscvovpsim_bin"], "--variant", variant]

        super().setup(config=config)

    def set_program(self, program):
        super().set_program(self.base_parameters + program)
