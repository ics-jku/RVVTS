#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import Runner, RunnerOutcome
from .RefCovRunner import RefCovRunner


class CompareRunner(Runner):

    def setup(self, config=None):

        super().setup(config)

        subconfig = config.copy()
        subconfig["dir"] = self.get_dir()

        self.CompareRunner_refcov = RefCovRunner(subconfig)
        self.CompareRunner_dut = config["CompareRunner_dut"](config=subconfig)
        self.binary = ""
        self.timeout = 1.0

    def task(self):
        self.CompareRunner_refcov.run(
            binary=self.binary, blocking=False, timeout=self.timeout
        )
        self.CompareRunner_dut.run(
            binary=self.binary, blocking=False, timeout=self.timeout
        )
        self.CompareRunner_refcov.wait()
        self.CompareRunner_dut.wait()
        res_refcov = self.CompareRunner_refcov.get_result()
        res_ref = (res_refcov[0], res_refcov[1]["ref:"])
        res_cov = (res_refcov[0], res_refcov[1]["cov:"])
        res_dut = self.CompareRunner_dut.get_result()

        if (
            res_refcov[0] != RunnerOutcome.COMPLETE
            or res_dut[0] != RunnerOutcome.COMPLETE
        ):
            res_output = {
                "ref:": res_ref[1],
                "dut:": res_dut[1],
                "cov:": res_cov[1],
            }
            # timeout more important than error
            if (
                res_refcov[0] == RunnerOutcome.TIMEOUT
                or res_dut[0] == RunnerOutcome.TIMEOUT
            ):
                return (RunnerOutcome.TIMEOUT, res_output)
            return (RunnerOutcome.ERROR, res_output)

        try:
            (is_equal, output) = res_ref[1].compare(res_dut[1])
            if is_equal:
                outcome = RunnerOutcome.COMPLETE
            else:
                outcome = RunnerOutcome.ERROR

            if res_cov[1]:
                output += "\nCOVERAGE\n"
                for k0, v0 in res_cov[1].items():
                    output += " * " + k0 + "\n"
                    for k1, v1 in v0.items():
                        output += (
                            "   * "
                            + k1.ljust(16)
                            + (" (" + str(v1["type"]) + ")").ljust(20)
                            + ": "
                            + (str(v1["points"]) + "/" + str(v1["points_max"])).ljust(
                                16
                            )
                            + " ("
                            + str(v1["percent"])
                            + "%)\n"
                        )

            return (outcome, output)

        except Exception as e:
            return (RunnerOutcome.ERROR, e)

    def run_handler(self, timeout=1.0, binary="", **kwargs):
        self.timeout = timeout
        self.binary = binary
        return super().run_handler(**kwargs)
