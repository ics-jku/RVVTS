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
import subprocess


class SailRunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        super().setup(config=config)

        sail_riscv_bin = config["sail_riscv_bin"]

        self.config = config
        self.rv_extensions = config["rv_extensions"]
        self.dumpfile = DumpFile(
            filename=self.get_dir() + "/mem." + hex(config["memstart"]) + ".bin",
            config=config,
            addr=config["xmemstart"] + config["xmemlen"] - config["dumpfile_reserve"],
        )
        self.mstate_filename = self.get_dir() + "/mstate.json"

        #
        # Create sail_riscv.cfg file
        #

        cfg = {}

        # Get original default cfg from sail-riscv run
        result = subprocess.run(
            [sail_riscv_bin, "--print-default-config"],
            capture_output=True,  # captures stdout and stderr
            text=True,  # returns strings instead of bytes
        )
        cfg_template = result.stdout

        # TODO: the sail_riscv json config has strange style: it contains comments (json5), but also
        # quoted keys (expected by sail-riscv). -> We would need "json5" to read it properly
        # and "json" to write it properly.
        # As current solution we use "json" for read and write and strip the comments manually

        # Remove // line comments
        cfg_template = re.sub(r"^\s*//.*$", "", cfg_template, flags=re.MULTILINE)
        # Remove /* ... */ block comments
        cfg_template = re.sub(r"/\*.*?\*/", "", cfg_template, flags=re.DOTALL)

        # read with "json"
        try:
            cfg = json.loads(cfg_template)
        except json.JSONDecodeError as e:
            print(f"Default config is not valid JSON: {e}")

        # Adapt the sail-riscv cfg according to rvvts configs (e.g. rv_extensions, memory)
        # Adjust base
        cfg["base"]["xlen"] = config["xlen"]

        # Disable all extensions
        self.cfg_set_ext_all(cfg, False)

        # Enable mandatory extensions
        self.cfg_set_ext(cfg, "Zifencei", True)
        self.cfg_set_ext(cfg, "Zicsr", True)

        # Enable configured extensions
        for ext in ["M", "F", "D", "Zfh", "V"]:
            if ext.casefold() in self.rv_extensions:
                self.cfg_set_ext(cfg, ext, True)
            else:
                self.cfg_set_ext(cfg, ext, False)

        # Apply "V" configuration
        if "v" in self.rv_extensions:
            cfg["extensions"]["V"]["vlen_exp"] = int(math.log(config["vector_vlen"], 2))
            cfg["extensions"]["V"]["elen_exp"] = int(math.log(config["vector_elen"], 2))
        else:
            cfg["extensions"]["V"]["vlen_exp"] = 3
            cfg["extensions"]["V"]["elen_exp"] = 3

        # Apply memory configuration
        self.cfg_set_mem(cfg, config["memstart"], config["memlen"])

        # Create the adjusted sail-riscv cfg file
        cfgstr = json.dumps(cfg)
        self.cfgfile = RunnerFile(
            dir=self.get_dir(), name="sail-riscv.cfg", content=cfgstr
        )

        # Create command
        self.set_program(
            [
                sail_riscv_bin,
                "--config",
                str(self.cfgfile.get_name()),
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
            # The sail_riscv model may exit with an errorcode on a failed assertation. In this
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

    def cfg_set_ext_all(self, cfg, supported):
        for name in cfg["extensions"]:
            self.cfg_set_ext(cfg, name, bool(supported))

    def cfg_set_ext(self, cfg, name, supported):

        def update_existing(d: dict, key, value):
            if key not in d:
                raise KeyError(f"Key does not exist: {key!r}")
            d[key] = value

        if name not in cfg["extensions"]:
            print(
                f'SailRunner: WARNING: Extension "{name}" not in sail-riscv config! -> CHECK RUNNER IMPLEMENTATION'
            )
            return False

        ext = cfg["extensions"][name]

        if not isinstance(ext, dict):
            print(
                f'SailRunner: WARNING: Node for extension "{name}" not a dictionary! -> CHECK RUNNER IMPLEMENTATION'
            )
            return False

        # if extension has 'supported' attribute -> set
        if "supported" in ext:
            ext["supported"] = bool(supported)
            # ok
            return True
        else:
            # Some (e.g., V, Stateen) have special structure -> try
            try:
                if name == "Stateen":
                    update_existing(ext["Smstateen"], "supported", bool(supported))
                    update_existing(ext["Ssstateen"], "supported", bool(supported))
                    return True
                if name == "V":
                    if supported:
                        update_existing(ext, "support_level", "Full")
                    else:
                        update_existing(ext, "support_level", "Disabled")
                    return True
            except Exception:
                print(
                    f'SailRunner: WARNING: Broken special handling for extension "{name}"! -> CHECK RUNNER IMPLEMENTATION'
                )
                return False

            print(
                f'SailRunner: WARNING: Missing special handling for extension "{name}"! -> CHECK RUNNER IMPLEMENTATION'
            )
            return False

    def cfg_set_mem(self, cfg, memstart, memlen):

        regions = cfg["memory"]["regions"]

        # find main memory region
        memregion = None
        for region in regions:

            if "attributes" not in region:
                continue

            # newer sail-riscv versions have set the attribute 'mem_type' to 'MainMemory'
            if (
                "mem_type" in region["attributes"]
                and region["attributes"]["mem_type"] == "MainMemory"
            ):
                # main memory region found
                memregion = region
                break

            # on older sail-riscv version we rely on 'include_in_device_tree' which is only set to true for main memory
            if region["include_in_device_tree"] is True:
                # main memory region found
                memregion = region
                break

        if memregion is None:
            raise Exception(
                "SailRunner: ERROR: Unable to set memory region! -> CHECK RUNNER IMPLEMENTATION"
            )

        # Apply memory configuration
        memregion["base"]["value"] = f"0x{memstart & ((1 << 64) - 1):016x}"
        memregion["size"]["value"] = f"0x{memlen & ((1 << 64) - 1):016x}"
