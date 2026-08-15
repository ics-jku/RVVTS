#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .MachineState import MachineState, DumpFile
from .BasicRunner import ProcessTimeoutRunner, RunnerOutcome, RunnerFile


class SpikeRunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        super().setup(config=config)

        self.config = config
        self.dumpfile = DumpFile(
            filename=self.get_dir() + "/mem." + hex(config["memstart"]) + ".bin",
            config=config,
            addr=config["xmemstart"] + config["xmemlen"] - config["dumpfile_reserve"],
        )
        self.mstate_filename = self.get_dir() + "/mstate.json"

        # create command file
        cmdstr = ""
        cmdstr += "until pc 0 " + hex(config["breakpoint"]) + "\n"
        cmdstr += "dump\n"
        cmdstr += "quit\n"
        self.cmdfile = RunnerFile(
            dir=self.get_dir(), name="cmdin.spike", content=cmdstr
        )

        # create command
        self.set_program(
            [
                config["spike_bin"],
                "--isa",
                config["rvisacfg"].to_isa_str_alt(),
                "-d",
                "-m" + hex(config["memstart"]) + ":" + hex(config["memlen"]),
                "--pc=" + hex(config["xmemstart"]),
                "--debug-cmd=" + str(self.cmdfile.get_name()),
            ]
        )

    def task_pre(self):
        self.dumpfile.delete()

    def task_post(self, result):
        outcome, ret = super().task_post(result)

        if outcome != RunnerOutcome.COMPLETE:
            return (outcome, None)

        try:
            regs, state = self.dumpfile.extract()
            mstate = MachineState(self.config, (regs, state))
            mstate.save(self.mstate_filename)
            return (outcome, mstate)
        except Exception as e:
            return (RunnerOutcome.ERROR, e)

    def run_handler(self, binary="", **kwargs):
        return super().run_handler(parameters=[binary], **kwargs)
