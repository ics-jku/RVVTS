#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .MachineState import MachineState, DumpFile
from .BasicRunner import Runner, ProcessTimeoutRunner, RunnerOutcome, RunnerFile

import re


# TODO: TRY STDIN
class GDBRunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        super().setup(config=config)

        self.config = config
        self.xlen = config["xlen"]

        self.dumpfile = DumpFile(
            config=config,
            filename=self.get_dir() + "/mem." + hex(config["memstart"]) + ".bin",
            addr=config["xmemstart"] + config["xmemlen"] - config["dumpfile_reserve"],
        )

        # create command file
        memend = config["memstart"] + config["memlen"]
        cmdstr = ""
        cmdstr += "set architecture riscv:rv" + str(config["xlen"]) + "\n"
        cmdstr += "target remote localhost:" + str(config["debug_port"]) + "\n"
        cmdstr += "set $pc = " + hex(config["xmemstart"]) + "\n"  # force entry point
        cmdstr += "break *" + hex(config["breakpoint"]) + "\n"
        cmdstr += "cont\n"
        cmdstr += "info registers general\n"
        # ensure dump is complete
        cmdstr += "cont\n"
        cmdstr += (
            "dump binary memory "
            + self.dumpfile.get_filename()
            + " "
            + hex(config["memstart"])
            + " "
            + hex(memend)
            + "\n"
        )
        cmdstr += "quit\n"
        self.cmdfile = RunnerFile(dir=self.get_dir(), name="cmdin.gdb", content=cmdstr)

        # create command
        self.set_program(
            [config["gdb_bin"], "--command=" + str(self.cmdfile.get_name())]
        )
        self.bitmask = (1 << config["xlen"]) - 1

    def task_pre(self):
        self.dumpfile.delete()

    def task_post(self, result):
        (outcome, ret) = super().task_post(result)

        if outcome != RunnerOutcome.COMPLETE:
            return (outcome, None)

        try:
            regs = ret.stdout
            regs = re.sub("\n", " ", regs)
            regs = re.split(r"(zero.*)", regs)[1]
            regs = re.split(r"\s+", regs)
            regs = {
                regs[i]: int(regs[i + 1], 16) & self.bitmask
                for i in range(0, 33 * 3, 3)
            }

            state = self.dumpfile.extract()

            return (outcome, MachineState(self.config, (regs, state)))
        except Exception as e:
            return (RunnerOutcome.ERROR, e)


class DuTGDBRunner(Runner):
    def setup(self, config=None):

        super().setup(config=config)

        subconfig = config.copy()
        subconfig["dir"] = self.get_dir()
        self.DuTGDBRunner_dut = config["DuTGDBRunner_dut"](config=subconfig)
        self.DuTGDBRunner_gdb = GDBRunner(config=subconfig)
        self.binary = ""
        self.timeout = 1.0

    def task(self):
        self.DuTGDBRunner_dut.run(
            binary=self.binary, blocking=False, timeout=self.timeout
        )
        self.DuTGDBRunner_gdb.run(
            binary=self.binary, blocking=False, timeout=self.timeout
        )
        self.DuTGDBRunner_gdb.wait()
        # gdb is complete -> stop dut
        if self.DuTGDBRunner_dut.is_busy():
            self.DuTGDBRunner_dut.stop()
            self.DuTGDBRunner_dut.wait()

        gdbres = self.DuTGDBRunner_gdb.get_result()
        dutres = self.DuTGDBRunner_dut.get_result()
        if gdbres[0] == RunnerOutcome.COMPLETE:
            return gdbres

        # deliver all output on error
        return (
            gdbres[0],
            {"DuTGDBRunner_dut": dutres[1], "DuTGDBRunner_gdb": gdbres[1]},
        )

    def run_handler(self, timeout=1.0, binary="", **kwargs):

        # parameter parsing
        self.binary = binary
        self.timeout = timeout

        return super().run_handler(**kwargs)
