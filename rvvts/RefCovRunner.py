#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import Runner, RunnerOutcome
from .RISCVOVPSIMRunner import RISCVOVPSIMRunner
from .SpikeRunner import SpikeRunner

import os
import re


class RISCVOVPSIMCoverageRunner(Runner):
    def setup(self, config=None):

        super().setup(config=config)

        # create command
        self.cov_report = "cov_report.log"
        self.covsum_report = "covsum_report.log"
        self.coverextensions = config["RISCVOVPSIMCover_extensions"]
        self.covermetric = config[
            "RISCVOVPSIMCover_metric"
        ]  # basic, extended or mnemonic
        self.coversum_en = config["RISCVOVPSIMCover_sum_enable"]  # True/False
        self.covtype = self.covermetric + "_" + self.coverextensions

        basepara = ["--extensions", self.coverextensions, "--cover", self.covermetric]

        subconfig = config.copy()
        subconfig["dir"] = self.get_dir()

        self.covrunner = RISCVOVPSIMRunner(config=subconfig)
        self.covrunner.set_program(
            basepara
            + [
                "--outputfile",
                "../cov.out",
                "--finishonaddress",
                hex(config["breakpoint"]),
                "--reportfile",
                "../" + self.cov_report,
            ]
        )

        self.coverage = None
        if self.coversum_en:
            self.covsumrunner = RISCVOVPSIMRunner(config=subconfig)
            self.covsumrunner.set_program(
                basepara
                + [
                    "--nosimulation",
                    "--showuncovered",
                    "--inputfiles",
                    "../sum.out,../cov.out",
                    "--outputfile",
                    "../sum.out",
                    "--reportfile",
                    "../" + self.covsum_report,
                ]
            )

    def extract_coverage(self, filename=None):
        with open(filename, "rb") as f:
            try:
                # consider only last 150 bytes
                f.seek(-150, os.SEEK_END)
            except OSError:
                return None

            ret = {}
            while True:
                line = f.readline()
                if not line:
                    break
                line = line.decode()
                tmp = re.split(":", line)
                if len(tmp) != 3:
                    continue
                (name, points, percent) = tmp
                coverage = {}
                coverage["percent"] = float(re.split("%", percent)[0])
                tmp = re.split("/", points)
                coverage["points"] = int(tmp[0])
                coverage["points_max"] = int(tmp[1])

                if "Coverage points hit" in name:
                    coverage["type"] = self.covtype
                    ret["coverage"] = coverage
                elif "Unique instructions" in name:
                    coverage["type"] = "uniq_instr"
                    ret["instr_coverage"] = coverage

            return ret

    def task(self):

        self.covrunner.run(
            parameters=["--program", self.binary], blocking=True, timeout=self.timeout
        )
        res = self.covrunner.get_result()
        if res[0] != RunnerOutcome.COMPLETE:
            return res

        if self.coversum_en:
            # ignore retval (first sum causes ret!=0, but output still ok)
            self.covsumrunner.run(blocking=True, timeout=self.timeout)

        self.coverage = {}
        self.coverage["current"] = self.extract_coverage(
            self.get_dir() + "/" + self.cov_report
        )
        if self.coversum_en:
            self.coverage["sum"] = self.extract_coverage(
                self.get_dir() + "/" + self.covsum_report
            )

        return (res[0], self.coverage)

    def run_handler(self, timeout=1.0, binary=None, **kwargs):
        self.timeout = timeout
        self.binary = binary
        return super().run_handler(**kwargs)


class RefCovRunner(Runner):

    def setup(self, config=None):

        super().setup(config)

        subconfig = config.copy()
        subconfig["dir"] = self.get_dir()

        self.RefCovRunner_ref = SpikeRunner(subconfig)
        if config["RefCovRunner_coverage"]:
            self.RefCovRunner_cov = config["RefCovRunner_coverage"](config=subconfig)
        else:
            self.RefCovRunner_cov = None
        self.binary = ""
        self.timeout = 1.0

    def task(self):
        self.RefCovRunner_ref.run(
            binary=self.binary, blocking=False, timeout=self.timeout
        )
        if self.RefCovRunner_cov:
            self.RefCovRunner_cov.run(
                binary=self.binary, blocking=False, timeout=self.timeout
            )
        self.RefCovRunner_ref.wait()
        if self.RefCovRunner_cov:
            self.RefCovRunner_cov.wait()
        res_ref = self.RefCovRunner_ref.get_result()
        if self.RefCovRunner_cov:
            res_cov = self.RefCovRunner_cov.get_result()
        else:
            res_cov = (RunnerOutcome.COMPLETE, None)

        res_output = {
            "ref:": res_ref[1],
            "cov:": res_cov[1],
        }

        if res_ref[0] != RunnerOutcome.COMPLETE or res_cov[0] != RunnerOutcome.COMPLETE:
            # timeout more important than error
            if (
                res_ref[0] == RunnerOutcome.TIMEOUT
                or res_cov[0] == RunnerOutcome.TIMEOUT
            ):
                return (RunnerOutcome.TIMEOUT, res_output)
            return (RunnerOutcome.ERROR, res_output)
        return (RunnerOutcome.COMPLETE, res_output)

    def run_handler(self, timeout=1.0, binary="", **kwargs):
        self.timeout = timeout
        self.binary = binary
        return super().run_handler(**kwargs)
