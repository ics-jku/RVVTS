#!/usr/bin/env python
# coding: utf-8
#
# (C) 2026 Katharina RUEP <katharina.ruep@jku.at>, Institute for Complex Systems, JKU Linz
# (C) 2026 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .MachineState import MachineState, DumpFile
from .BasicRunner import ProcessTimeoutRunner, RunnerOutcome, RunnerFile

import re
import json
import math


class SailRunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        super().setup(config=config)

        self.config = config
        self.rv_extensions = config["rv_extensions"]
        self.dumpfile = DumpFile(
            filename=self.get_dir() + "/mem." + hex(config["memstart"]) + ".bin",
            config=config,
            addr=config["xmemstart"] + config["xmemlen"] - config["dumpfile_reserve"],
        )
        self.mstate_filename = self.get_dir() + "/mstate.json"

        # create sail.cfg file
        # get default cfg file
        cfg = {}
        cfg_filename = "sail-riscv_a33475aeb8.cfg"
        # TODO: the sail json config has strange style: it contains comments (json5), but also
        # quoted keys (expected by sail-riscv). -> We would need "json5" to read it properly
        # and "json" to write it properly.
        # As current solution we use "json" for read and write and strip the comments manually
        try:
            with open(f"rvvts/{cfg_filename}", "r", encoding="utf-8") as f:
                cfg_template = f.read()
                # Remove // line comments
                cfg_template = re.sub(
                    r"^\s*//.*$", "", cfg_template, flags=re.MULTILINE
                )
                # Remove /* ... */ block comments
                cfg_template = re.sub(r"/\*.*?\*/", "", cfg_template, flags=re.DOTALL)
                cfg = json.loads(cfg_template)
        except FileNotFoundError:
            print(f"Config file '{cfg_filename}' not found in the current directory.")
        except PermissionError:
            print(f"Permission denied when reading '{cfg_filename}'.")
        except OSError as e:
            print(f"Error reading '{cfg_filename}': {e}")
        except json.JSONDecodeError as e:
            print(f"Default config is not valid JSON: {e}")
        # adapt according to settings (e.g. rv_extensions, memory)
        # Base
        cfg["base"]["xlen"] = config["xlen"]
        # Mandatory extensions
        self.set_ext(cfg, "Zifencei", True)
        self.set_ext(cfg, "Zicsr", True)
        # TODO: Develop a cleaner solution. Something like this: iterate over all extension
        # in the config and disable, and then iterate over all extensions in self.rv_extensions
        # to enable extensions in the config
        for ext in ["M", "F", "D", "Zfh"]:
            if ext.casefold() in self.rv_extensions:
                self.set_ext(cfg, ext, True)
            else:
                self.set_ext(cfg, ext, False)
        if "v" in self.rv_extensions:
            cfg["extensions"]["V"]["support_level"] = "Full"
            cfg["extensions"]["V"]["vlen_exp"] = int(math.log(config["vector_vlen"], 2))
            cfg["extensions"]["V"]["elen_exp"] = int(math.log(config["vector_elen"], 2))
        else:
            cfg["extensions"]["V"]["support_level"] = "Disabled"
            cfg["extensions"]["V"]["vlen_exp"] = 3
            cfg["extensions"]["V"]["elen_exp"] = 3
        # Memory
        cfg["memory"]["regions"][0]["base"][
            "value"
        ] = f"0x{config['memstart'] & ((1 << 64) - 1):016x}"
        cfg["memory"]["regions"][0]["size"][
            "value"
        ] = f"0x{config['memlen'] & ((1 << 64) - 1):016x}"  # config["memlen"]
        # write cfg fiel
        cfgstr = json.dumps(cfg)
        self.cmdfile = RunnerFile(dir=self.get_dir(), name=cfg_filename, content=cfgstr)
        # create command
        sail_bin = config["sail_riscv_bin"]
        self.set_program(
            [
                sail_bin,
                "--config",
                str(self.cmdfile.get_name()),
                "--use-abi-names",
                "--breakpoint",
                str(config["breakpoint"]),
                "--memstart",
                str(config["memstart"]),
                "--memlen",
                str(config["memlen"]),
            ]
            # "--inst-limit 100000",
        )

    def task_pre(self):
        self.dumpfile.delete()

    def task_post(self, result):
        outcome, ret = super().task_post(result)

        if outcome != RunnerOutcome.COMPLETE:
            # The sail model may exit with an errorcode on a failed assertation. In this
            # case we get a "Assertation failed" message on stderr.
            # Handling such cases as mstate difference (fail) makes it possible
            # 1. to differenciate failed Assertations from other model execution aborts, and
            # 2. to minimize such cases with CodeErrMinRunner.
            if "Assertion failed" in ret.stderr:
                mstate = MachineState(self.config)
                mstate.state[1]["lastPC"] = -1
                return (RunnerOutcome.COMPLETE, mstate)
            else:
                print(
                    "SailRunner: WARNING: UNKNOWN ABORT! -> CHECK RUNNER IMPLEMENTATION"
                )
                print(ret.stdout)
                print(ret.stderr)
            return (outcome, None)

        try:
            regs, state = self.dumpfile.extract()

        except Exception as e:
            return (RunnerOutcome.ERROR, e)

        mstate = MachineState(self.config, (regs, state))
        mstate.save(self.mstate_filename)
        return (outcome, mstate)

    def run_handler(self, binary="", **kwargs):
        return super().run_handler(parameters=[binary], **kwargs)

    def set_ext(self, cfg, name, supported):
        if name in cfg["extensions"]:
            # Some (e.g., V, Zawrs) have nested objects; only set 'supported' if present
            if (
                isinstance(cfg["extensions"][name], dict)
                and "supported" in cfg["extensions"][name]
            ):
                cfg["extensions"][name]["supported"] = bool(supported)
