#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .CodeBlock import CodeStats, CodeBlock
from .BasicRunner import Runner, RunnerOutcome, RunnerFile
from .CodeErrMinRunner import CodeErrMinRunner

import math
import glob


class TestsetCodeErrMinRunner(Runner):
    def setup(self, config):

        super().setup(config)

        if config["log"]:
            self.statslog = RunnerFile(dir=self.get_dir(), name="stats.log")

        # testlist
        self.globstr = config["testset_dir"] + "/**/" + config["testset_pattern"]
        self.testset = glob.glob(self.globstr, recursive=True)
        self.testname = ""
        self.testset_len = len(self.testset)
        self.testset_last_idx = self.testset_len - 1
        self.testset_idx = -1
        # -1 .. no subruns (run full test at once)
        self.testset_max_fragments_per_run = config["testset_max_fragments_per_run"]
        self.subruns = -1
        self.subrun = 0
        self.sub_last_state = None

        self.code_block = None
        self.res_code_block = None

        # runner for register values
        subconfig = config.copy()
        subconfig["dir"] = self.get_dir()
        self.codeerrminrunner = CodeErrMinRunner(subconfig)

    # subruns subrun laststate
    def task(self):

        # load next testcase
        self.subrun += 1
        if self.subrun > self.subruns:
            self.testset_idx += 1

            if self.testset_idx > self.testset_last_idx:
                return (RunnerOutcome.IGNORE, None)
            self.testname = self.testset[self.testset_idx]

            # load codeblock
            self.code_block_full = CodeBlock.load(self.testname)

            if self.testset_max_fragments_per_run > 0:
                self.subruns = math.ceil(
                    self.code_block_full.main_len() / self.testset_max_fragments_per_run
                )
                self.subrun = 0
            else:
                self.subruns = 1
                self.subrun = 1
            self.sub_last_state = None

        if self.testset_max_fragments_per_run > 0:
            # split testcase in subtests
            # smaller rest is handled automatically
            begin = self.subrun * self.testset_max_fragments_per_run
            end = begin + self.testset_max_fragments_per_run
            self.code_block = self.code_block_full.get_part(begin, end)

            # init from last state
            if self.sub_last_state:
                self.code_block.set_init_fragments(
                    self.sub_last_state.as_CodeFragmentList()
                )
        else:
            self.code_block = self.code_block_full

        ret = self.codeerrminrunner.run(
            blocking=True, code_block=self.code_block, **self.runkwargs
        )

        # TODO: cleaner way to read ref results
        self.sub_last_state = self.codeerrminrunner.codecomparerunner.compare_runner.CompareRunner_refcov.get_result()[
            1
        ][
            "ref:"
        ]
        self.res_code_block = self.codeerrminrunner.res_code_block

        return ret

    def task_post(self, ret):

        # handle stats
        if self.log:
            self.statslog.set_content(
                "testset_len: "
                + str(self.testset_len)
                + "\ntestset_idx: "
                + str(self.testset_idx)
                + "\nsubruns: "
                + str(self.subruns)
                + "\nsubrun: "
                + str(self.subrun)
                + "\ntestname: "
                + str(self.testname)
                + "\n"
            )

        if self.code_block:
            self.code_block.save(self.dir + "/code_block.json")
        if self.res_code_block:
            self.res_code_block.save(self.dir + "/res_code_block.json")

        return ret

    def get_error_cause(self):
        return self.codeerrminrunner.get_error_cause()

    def run_handler(self, blocking, **kwargs):

        self.runkwargs = kwargs
        return super().run_handler(blocking=blocking, **kwargs)

    def get_testset_stats(self):

        def update_stats(stats, val):
            if val < stats[0]:
                stats[0] = val
            if val > stats[1]:
                stats[1] = val
            stats[2] += val

        cstatsum = CodeStats()
        testcases = 0
        # min, max, avg
        fragments = [2**31, 0, 0]
        lines = [2**31, 0, 0]
        ins = [2**31, 0, 0]
        vins = [2**31, 0, 0]

        for t in self.testset:
            testcases += 1
            c = CodeBlock.load(t)
            cstat = c.get_stats_all()
            cstatsum.add(cstat)

            update_stats(fragments, cstat.fragments)
            update_stats(lines, cstat.lines)
            update_stats(ins, cstat.ins)
            update_stats(vins, cstat.vins)

        fragments[2] /= testcases
        lines[2] /= testcases
        ins[2] /= testcases
        vins[2] /= testcases

        return (testcases, cstatsum, fragments, lines, ins, vins)
