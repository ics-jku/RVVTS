#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import ProcessTimeoutRunner


class RISCVOVPSIMRunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        # create command
        variant = "RV" + str(config["xlen"]) + "GC"
        if "v" in config["rv_extensions"]:
            variant = variant + "V"
        self.base_parameters = [config["riscvovpsim_bin"], "--variant", variant]

        super().setup(config=config)

    def set_program(self, program):
        super().set_program(self.base_parameters + program)
