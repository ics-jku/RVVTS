#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import ProcessTimeoutRunner


class VPRunner(ProcessTimeoutRunner):
    def setup(self, config=None):

        super().setup(config=config)

        # create command
        vp_bin = "tiny" + str(config["xlen"]) + "-vp"
        self.set_program(
            [
                config["vp_path"] + "/" + vp_bin,
                "--memory-start=" + str(config["memstart"]),
                "--memory-size=" + str(config["memlen"]),
                "--use-dmi",
                "--tlm-global-quantum=1000000",
                "--error-on-zero-traphandler=true",
                "--intercept-syscalls",
                "--debug-mode",
                "--debug-port",
                str(config["debug_port"]),
            ]
        )

    def run_handler(self, binary="", **kwargs):
        return super().run_handler(parameters=[binary], **kwargs)
