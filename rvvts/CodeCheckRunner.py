#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import Runner, RunnerOutcome, RunnerFile
from .BuildRunner import BuildRunner
from .RefCovRunner import RefCovRunner


class CodeCheckRunner(Runner):
    def setup(self, config=None):

        super().setup(config)

        self.timeout = 1.0
        self.binary_file = RunnerFile(dir=self.get_dir(), name="out.bin")

        subconfig = config.copy()
        subconfig["dir"] = self.get_dir()

        subconfig["binary"] = self.binary_file.get_name()
        self.build_runner = BuildRunner(config=subconfig)

        subconfig["breakpoint"] = self.build_runner.get_breakpoint()
        self.refcov_runner = RefCovRunner(config=subconfig)

    def task(self):

        self.build_runner.run(code=self.code, blocking=True, timeout=self.timeout)
        res = self.build_runner.get_result()
        if res[0] != RunnerOutcome.COMPLETE:
            return res

        self.refcov_runner.run(
            binary=self.binary_file.get_name(), blocking=True, timeout=self.timeout
        )
        return self.refcov_runner.get_result()

    def run_handler(self, timeout=1.0, code="", **kwargs):
        self.timeout = timeout
        self.code = code
        return super().run_handler(**kwargs)
