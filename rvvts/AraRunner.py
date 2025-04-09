#!/usr/bin/env python
# coding: utf-8
#
# (C) 2025 Jonas REICHHARDT <reichhardt.jonas@gmail.com>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .MachineState import MachineState, DumpFile, RVREGS_IDX_DICT
from .BasicRunner import ProcessTimeoutRunner, RunnerOutcome, RunnerFile

import re


class AraRunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        super().setup(config=config)
        self.config = config
        self.rv_extensions = config["rv_extensions"]
        self.xlen = config["xlen"]
        
        self.dumpfile = DumpFile(
            filename=self.get_dir() + "/dump.bin",
            config=config,
            addr=config["xmemstart"] + config["xmemlen"] - config["dumpfile_reserve"],
        )

        self.set_program([config["ara_tb_bin"],"-l"])

    def task_pre(self):
        self.dumpfile.delete()

    def task_post(self, result):
        (outcome, ret) = super().task_post(result)

        if outcome != RunnerOutcome.COMPLETE:
            return (outcome, None)

        try:
            regs = {}
            tmp = ret.stdout
            tmp = tmp.split("\n")
            pc_idx = -1
            for i, s in enumerate(tmp):
                if "pc" in s:
                  pc_idx = i
                if "STALL" in s:
                  return (RunnerOutcome.TIMEOUT,s)
            if pc_idx == -1:
                raise Exception("Could not extract integer registers from testbench output")
            regs["pc"] = int(tmp[pc_idx].split(" ")[1])
                    
            for i in range(0,32,1):
                reg_name = list(RVREGS_IDX_DICT.keys())[list(RVREGS_IDX_DICT.values()).index(i)]
                regs[reg_name] = int(tmp[pc_idx+1+i].split(" ")[1])

            state = self.dumpfile.extract()

        except Exception as e:
            return (RunnerOutcome.ERROR, e)

        return (outcome, MachineState(self.config, (regs, state)))

    def run_handler(self, binary="", **kwargs):
        return super().run_handler(parameters=["ram,"+binary+",elf"], **kwargs)
