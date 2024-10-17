#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import ProcessTimeoutRunner


class QEMURunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        super().setup(config=config)

        # create command
        xlen = config["xlen"]
        qemu_bin = "qemu-system-riscv" + str(xlen)
        cpustr = "rv" + str(xlen)
        if "v" in config["rv_extensions"]:
            cpustr = (
                cpustr
                + ",v=true,vlen="
                + str(config["vector_vlen"])
                + ",elen="
                + str(config["vector_elen"])
            )

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
