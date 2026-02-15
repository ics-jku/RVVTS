#!/usr/bin/env python
# coding: utf-8
#
# (C) 2025-26 Jonas REICHHARDT <reichhardt.jonas@gmail.com>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .MachineState import MachineState, DumpFile
from .BasicRunner import ProcessTimeoutRunner, RunnerOutcome


class AraRunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        super().setup(config=config)
        self.config = config
        self.rv_extensions = config["rv_extensions"]
        self.xlen = config["xlen"]

        # ARA may hang on test case execution (running clock, but no instructions retired)
        # with this we control, whether we count such cases as TIMEOUT or ERROR (with lastPC = -1)
        # (handling it as error makes it possible to minimize the case with CodeErrMinRunner, but
        # may hide the hang cases)
        self.count_hang_as_error = config.get("AraRunner_count_hang_as_error", False)

        self.dumpfile = DumpFile(
            filename=self.get_dir() + "/dump.bin",
            config=config,
            addr=config["xmemstart"] + config["xmemlen"] - config["dumpfile_reserve"],
        )
        self.mstate_filename = self.get_dir() + "/mstate.json"

        self.set_program([config["ara_tb_bin"], "-l"])

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
                    if self.count_hang_as_error:
                        mstate = MachineState(self.config)
                        mstate.state[1]["lastPC"] = -1
                        return (RunnerOutcome.COMPLETE, mstate)
                    else:
                        return (RunnerOutcome.TIMEOUT, s)
            if pc_idx == -1:
                raise Exception(
                    "Could not extract integer registers from testbench output"
                )
            regs["pc"] = int(tmp[pc_idx].split(" ")[1])

            regs, state = self.dumpfile.extract()

        except Exception as e:
            return (RunnerOutcome.ERROR, e)

        mstate = MachineState(self.config, (regs, state))
        mstate.save(self.mstate_filename)
        return (outcome, mstate)

    def run_handler(self, binary="", **kwargs):
        return super().run_handler(parameters=["ram," + binary + ",elf"], **kwargs)
