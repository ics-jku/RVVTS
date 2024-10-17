#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import Runner
from .ISG import ProgramMultiGenerator, RVProgramGenerator, RVVProgramGenerator
from .CodeErrMinRunner import CodeErrMinRunner


class FuzzCodeErrMinRunner(Runner):
    def setup(self, config):

        super().setup(config)

        self.rv_extensions = config["rv_extensions"]

        # fuzzer generator
        classes = [RVProgramGenerator]
        if "v" in self.rv_extensions:
            classes.append(RVVProgramGenerator)
        self.programgenerator = ProgramMultiGenerator(config=config, classes=classes)

        # runner for test and code minimization on error
        subconfig = config.copy()
        subconfig["dir"] = self.get_dir()
        self.codeerrminrunner = CodeErrMinRunner(subconfig)

    def task(self):

        # generate initial code
        self.code_block = self.programgenerator.gen_code_block(
            min_fragments=self.min_fragments, max_fragments=self.max_fragments
        )

        ret = self.codeerrminrunner.run(
            blocking=True, code_block=self.code_block, **self.runkwargs
        )

        self.res_code_block = self.codeerrminrunner.res_code_block

        return ret

    def get_error_cause(self):
        return self.codeerrminrunner.get_error_cause()

    def run_handler(self, blocking, min_fragments, max_fragments, **kwargs):

        self.runkwargs = kwargs
        self.min_fragments = min_fragments
        self.max_fragments = max_fragments
        return super().run_handler(blocking=blocking, **kwargs)
