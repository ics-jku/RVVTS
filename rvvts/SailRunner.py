#!/usr/bin/env python
# coding: utf-8
#
# (C) 2026 Katharina RUEP <katharina.ruep@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .MachineState import MachineState, DumpFile
from .BasicRunner import ProcessTimeoutRunner, RunnerOutcome, RunnerFile

import re
import json

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
        cfg_filename = "sail.cfg"
        try:
            with open(f"rvvts/{cfg_filename}", "r", encoding="utf-8") as f:
                cfg_template = f.read()
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
        # Extensions
        if "v" in self.rv_extensions:
            cfg["extensions"]["vlen_exp"] = config["vector_vlen"]
            cfg["extensions"]["elen_exp"] = config["vector_elen"]
        else:
            cfg["extensions"]["support_level"] = "Disabled"
            cfg["extensions"]["vlen_exp"] = 3
            cfg["extensions"]["elen_exp"] = 3
        for float_ext in ["F", "D", "Zfh"]:
            if float_ext.casefold() in self.rv_extensions:
                self.set_ext(cfg, float_ext, True)
            else:
                self.set_ext(cfg, float_ext, False)
        self.set_ext(cfg, "Zifencei", True)
        # Memory
        cfg["memory"]["regions"][0]["base"]["value"] = f"0x{config['memstart'] & ((1 << 64) - 1):016x}"
        cfg["memory"]["regions"][0]["size"]["value"] = f"0x{config['memlen'] & ((1 << 64) - 1):016x}" #config["memlen"]
        # write cfg fiel
        cfgstr = json.dumps(cfg)
        self.cmdfile = RunnerFile(
            dir=self.get_dir(), name=cfg_filename, content=cfgstr
        )
        # create command
        sail_bin = config["sail_riscv_bin"]
        self.set_program(
            [
                sail_bin,
                "--config", str(self.cmdfile.get_name()),
                "--use-abi-names",  
                "--breakpoint", str(config["breakpoint"]),
                "--memstart", str(config["memstart"]),
                "--memlen", str(config["memlen"])
            ]
            #"--inst-limit 100000",
        )

    def task_pre(self):
        self.dumpfile.delete()

    def task_post(self, result):
        (outcome, ret) = super().task_post(result)

        if outcome != RunnerOutcome.COMPLETE:
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
            if isinstance(cfg["extensions"][name], dict) and "supported" in cfg["extensions"][name]:
                cfg["extensions"][name]["supported"] = bool(supported)
        
