#!/usr/bin/env python
# coding: utf-8
#
# (C) 2026 Anna Reiter <anna.reiter@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .MachineState import MachineState, DumpFile
from .BasicRunner import ProcessTimeoutRunner, RunnerOutcome
import re


class MinresVPRunner(ProcessTimeoutRunner):
    MINRES_VLEN = 128
    MINRES_ELEN = 64
    MINRES_MEM_LEN = 0x300000

    def is_valid_extension_string(self, ext_str):
        res = re.fullmatch("rv(32|64)i?m?f?d?v?(_zicsr)?(_zifencei)?", ext_str)
        if res is not None:
            return True
        return False

    def is_vector_config_valid(self, isa_cfg):
        if int(isa_cfg.get_vlen()) != self.MINRES_VLEN:
            return False

        if int(isa_cfg.get_velen()) != self.MINRES_ELEN:
            return False

        return True

    def build_isa_string(self, isa_cfg):
        isa_str = "rv" + str(isa_cfg.get_xlen())

        # In the Minres VP, there are 4 different isa options:
        # - rv{xlen}gcv_{privilege_level}
        # - rv{xlen}gc_{privilege_level}
        # - rv{xlen}imac_{privilege_level}
        # - rv{xlen}i_{privilege_level}
        # Available options can be queried using --isa=?

        if isa_cfg.is_needed("v"):
            isa_str += "gcv"
        elif isa_cfg.is_needed("f") or isa_cfg.is_needed("d"):
            isa_str += "gc"
        elif isa_cfg.is_needed("m"):
            isa_str += "imac"
        else:
            isa_str += "i"

        isa_str += "_m"
        return isa_str

    def setup(self, config=None):
        isa_cfg = config["rvisacfg"]
        if not self.is_valid_extension_string(isa_cfg.to_isa_str()):
            raise Exception(f"Invalid Extension String {isa_cfg.to_isa_str()}!")

        if not self.is_vector_config_valid(isa_cfg):
            raise Exception(
                "Invalid VLEN or ELEN! Required {} for VLEN and {} for ELEN!".format(
                    self.MINRES_VLEN, self.MINRES_ELEN
                )
            )

        if int(config["memlen"]) != self.MINRES_MEM_LEN:
            raise Exception(
                "Invalid Memory Length! Required length: {}".format(self.MINRES_MEM_LEN)
            )

        super().setup(config=config)
        self.config = config
        self.dumpfile = DumpFile(
            filename=self.get_dir() + "/mem." + hex(config["memstart"]) + ".bin",
            config=config,
            addr=config["xmemstart"] + config["xmemlen"] - config["dumpfile_reserve"],
        )
        self.mstate_filename = self.get_dir() + "/mstate.json"

        # create command
        self.set_program(
            [
                config["minresvp_bin"],
                "--isa=" + self.build_isa_string(isa_cfg),
                "--mem-start-address",  # May not work for arbitrary start addresses
                str(
                    config["memstart"]
                ),  # It is recommended to use 0x80000000 as a starting point
                "--stop-at-pc",
                str(config["breakpoint"]),
                "-f",
            ]
        )

    def run_handler(self, binary="", **kwargs):
        return super().run_handler(parameters=[binary], **kwargs)

    def task_post(self, result):
        outcome, ret = super().task_post(result)

        if outcome != RunnerOutcome.COMPLETE:
            if outcome == RunnerOutcome.TIMEOUT:
                return (RunnerOutcome.TIMEOUT, None)

            if (
                "Simulation aborted with signal SEGV!" in ret.stdout
                or "uncaught exception: Unsupported sew bit value" in ret.stdout
                or "Assertion" in ret.stdout
                or "Assertion" in ret.stderr
            ):
                mstate = MachineState(self.config)
                mstate.state[1]["lastPC"] = -1
                return (RunnerOutcome.COMPLETE, mstate)
            else:
                return (outcome, None)

        try:
            regs, state = self.dumpfile.extract()
            mstate = MachineState(self.config, (regs, state))
            mstate.save(self.mstate_filename)
            return (outcome, mstate)
        except Exception as e:
            return (RunnerOutcome.ERROR, e)
