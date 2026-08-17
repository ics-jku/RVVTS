#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import ProcessTimeoutRunner


class QEMURunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        super().setup(config=config)

        # create command
        rvisacfg = config["rvisacfg"]
        xlen = rvisacfg.get_xlen()
        qemu_bin = "qemu-system-riscv" + str(xlen)
        cpustr = "rv" + str(xlen)
        if rvisacfg.is_needed("f"):
            cpustr = f"{cpustr},f=true"
        if rvisacfg.is_needed("d"):
            cpustr = f"{cpustr},d=true"
        if rvisacfg.is_needed("q"):
            cpustr = f"{cpustr},q=true"
        if rvisacfg.is_needed("zfh"):
            cpustr = f"{cpustr},zfh=true"
        if rvisacfg.is_needed("v"):
            cpustr = f"{cpustr},v=true,vlen={rvisacfg.get_vlen()},elen={rvisacfg.get_velen()}"

        self.set_program(
            [
                config["qemu_path"] + "/" + qemu_bin,
                "-M",
                "spike",
                "-cpu",
                cpustr,
                "-display",
                "none",
                "-serial",
                "mon:stdio",
                "-gdb",
                "tcp::" + str(config["debug_port"]),
                "-S",
            ]
        )

    def run_handler(self, binary="", **kwargs):
        return super().run_handler(parameters=["-bios", binary], **kwargs)
