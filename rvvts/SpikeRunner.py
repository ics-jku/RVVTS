#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .MachineState import MachineState, DumpFile
from .BasicRunner import ProcessTimeoutRunner, RunnerOutcome, RunnerFile

import re


class SpikeRunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        super().setup(config=config)

        self.config = config
        self.rv_extensions = config["rv_extensions"]
        self.dumpfile = DumpFile(
            filename=self.get_dir() + "/mem." + hex(config["memstart"]) + ".bin",
            config=config,
            addr=config["xmemstart"] + config["xmemlen"] - config["dumpfile_reserve"],
        )

        # create command file
        cmdstr = ""
        cmdstr += "until pc 0 " + hex(config["breakpoint"]) + "\n"
        cmdstr += "pc 0\n"
        cmdstr += "reg 0\n"
        # ensure dump is complete
        cmdstr += "rs 1\n"
        cmdstr += "until pc 0 " + hex(config["breakpoint"]) + "\n"
        cmdstr += "dump\n"
        cmdstr += "quit\n"
        self.cmdfile = RunnerFile(
            dir=self.get_dir(), name="cmdin.spike", content=cmdstr
        )

        # create command
        # TODO: when switching to new spike version
        # --varch does no longer exist in new spike versions (use zvl/zve instead)
        # e.g. ".._zvl512b" (see V spec)
        # 1. If --varch is used, this triggers a framework bug (reference of None type) -> fix before fixing varch
        # 2. Fix parameters below
        self.set_program(
            [
                config["spike_bin"],
                "--isa",
                "RV" + str(config["xlen"]) + "I" + config["rv_extensions"],
                "--varch="
                + "vlen:"
                + str(config["vector_vlen"])
                + ",elen:"
                + str(config["vector_elen"]),
                "-d",
                "-m" + hex(config["memstart"]) + ":" + hex(config["memlen"]),
                "--pc=" + hex(config["xmemstart"]),
                "--debug-cmd=" + str(self.cmdfile.get_name()),
            ]
        )

    def task_pre(self):
        self.dumpfile.delete()

    def task_post(self, result):
        (outcome, ret) = super().task_post(result)

        if outcome != RunnerOutcome.COMPLETE:
            return (outcome, None)

        try:
            regs = {}
            tmp = ret.stderr
            tmp = re.sub("\n", " ", tmp)
            tmp = re.split(r"(zero:.*)", tmp)
            tmp0 = tmp[0]
            tmp0 = re.split(r"\s+", tmp0)
            tmp0 = tmp0[-2]
            tmp1 = tmp[1]
            tmp1 = re.sub(":", "", tmp1)
            tmp1 = re.sub("s0", "fp", tmp1)  # quirk to match gdb
            tmp1 = re.split(r"\s+", tmp1)
            regs = {tmp1[i]: int(tmp1[i + 1], 16) for i in range(0, 2 * 32, 2)}
            # vregs = {}
            # if 'v' in self.rv_extensions:
            #    s = 2*32 + 4
            #    e = s + 5 * 32
            #    vregs = {tmp1[i]: [tmp1[i + 2], tmp1[i + 2 + 2]] for i in range(s, e, 5)}
            #    #print(vregs)
            regs["pc"] = int(tmp0, 16)

            state = self.dumpfile.extract()

        except Exception as e:
            return (RunnerOutcome.ERROR, e)

        return (outcome, MachineState(self.config, (regs, state)))

    def run_handler(self, binary="", **kwargs):
        return super().run_handler(parameters=[binary], **kwargs)
