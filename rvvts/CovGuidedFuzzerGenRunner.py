#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

import os
import random

from .CodeBlock import CodeBlock
from .BasicRunner import Runner, RunnerOutcome, RunnerFile
from .RefCovRunner import RISCVOVPSIMCoverageRunner
from .CodeCheckRunner import CodeCheckRunner
from .ISG import ProgramMultiGenerator, RVProgramGenerator, RVVProgramGenerator


class CovGuidedFuzzerGenRunner(Runner):
    def setup(self, config):

        # force not indexed directory (only for this runner)
        # to be able to continue previously generated runs
        myconfig = config.copy()
        myconfig["RunnerDirNotIndexed"] = True

        super().setup(myconfig)

        self.allow_exceptions = config["CovGuidedFuzzerGen_allow_exceptions"]
        self.rv_extensions = config["rv_extensions"]

        # TODO: make configurable
        self.THRESH_REPEAT_EXTEND = 10
        self.THRESH_NO_EXTEND_ALLOW_REDUCE_COV = 100
        self.THRESH_NO_EXTEND_TRY_REDUCE = 110
        self.THRESH_TRY_REDUCE = 10

        self.TESTCASE_CODE_FILENAME = self.get_dir() + "/testcase_code.json"
        self.STATE_INIT = 0
        self.STATE_EXTEND = 1
        self.STATE_REDUCE = 2
        self.cnt_state = 0
        self.cnt_no_extend = 0
        self.state = self.STATE_INIT

        self.code = None

        self.generates = 0
        self.ignores = 0
        self.timeouts = 0
        self.errors = 0
        self.unknown_faults = 0
        self.completes = 0
        self.exceptions = 0
        self.valids = 0
        self.extensions = 0
        self.extensions_redcov = 0
        self.reductions = 0
        self.code_len = 0
        self.coverage = (0, 0)
        self.coverage_last = (0, 0)

        self.error_cause = "unknown"

        if config["log"]:
            self.statslog = RunnerFile(dir=self.get_dir(), name="stats.log")

        # fuzzer generator
        classes = [RVProgramGenerator]
        if "v" in self.rv_extensions:
            classes.append(RVVProgramGenerator)
        self.programgenerator = ProgramMultiGenerator(config=config, classes=classes)

        subconfig_check = config.copy()
        subconfig_check["dir"] = self.get_dir()
        # force enable coverage and disable sum
        subconfig_check["RefCovRunner_coverage"] = RISCVOVPSIMCoverageRunner
        subconfig_check["RISCVOVPSIMCover_sum_enable"] = False

        if self.allow_exceptions:
            subconfig_check["stop_on_exception"] = False
            subconfig_check["skip_on_exception"] = True
        else:
            # don't allow exceptions -> bail out early on exceptions
            subconfig_check["stop_on_exception"] = True
            subconfig_check["skip_on_exception"] = False

        # runner for checks (exc) and coverage
        self.codecheckrunner = CodeCheckRunner(config=subconfig_check)

    def check_code(self, code):
        ret = self.codecheckrunner.run(
            blocking=True, code=code.as_code(), **self.runkwargs
        )

        self.generates += 1

        if ret[0] != RunnerOutcome.COMPLETE:
            if ret[0] == RunnerOutcome.IGNORE:
                self.ignores += 1
                return None
            elif ret[0] == RunnerOutcome.TIMEOUT:
                # TODO: improve in future -> try to remove timeout
                self.timeouts += 1
                return None
            elif ret[0] == RunnerOutcome.ERROR:
                print(ret)
                self.errors += 1
                return None
            else:
                # paranoia fallback (unkown error -> stop)
                self.unknown_faults += 1
                return None

        self.completes += 1

        mstate_ref = ret[1]["ref:"]
        if mstate_ref.state[1]["#exceptions"] != 0:
            self.exceptions += 1
            if not self.allow_exceptions:
                return None

        self.valids += 1

        cov_percent = ret[1]["cov:"]["current"]["coverage"]["percent"]
        cov_points = ret[1]["cov:"]["current"]["coverage"]["points"]
        return (cov_points, cov_percent)

    def gen_code(self):
        # try generate
        code_new = self.programgenerator.gen_code_block(
            min_fragments=self.min_start_fragments,
            max_fragments=self.max_start_fragments,
        )

        # check and coverage
        coverage = self.check_code(code_new)
        if coverage:
            self.code = code_new
            self.code_len = code_new.main_len()
            self.coverage = coverage
            return True

        self.code = None
        self.code_len = 0
        self.coverage = (0, 0)
        return False

    def load_code(self, filename):
        # try load
        code_new = None
        try:
            if os.path.isfile(filename):
                code_new = CodeBlock.load(filename)
        except Exception:
            code_new = None

        if code_new:
            # check and coverage
            coverage = self.check_code(code_new)
            if coverage:
                self.code = code_new
                self.code_len = code_new.main_len()
                self.coverage = coverage
                return True

        self.code = None
        self.code_len = 0
        self.coverage = (0, 0)
        return False

    def save_code(self, filename):
        if self.code:
            self.code.save(filename)

    def init(self):
        ret = self.load_code(self.TESTCASE_CODE_FILENAME)
        if not ret:
            ret = self.gen_code()
        if ret:
            self.state = self.STATE_EXTEND
            # stop subiteration loop after init -> early result
            return False
        return True

    def try_extend(self):
        # TODO: make this more efficient
        code_new = CodeBlock(
            init_fragments=self.code.init_fragments,
            deinit_fragments=self.code.deinit_fragments,
        )
        code_orig_main = self.code.main_fragments
        code_new.main_fragments.add_list(code_orig_main)

        fragments_new = self.programgenerator.gen_code_block(1, 1).main_fragments
        len = code_orig_main.len()
        if len <= 1:
            ins = len
        else:
            ins = random.randint(0, len)
        code_new.main_fragments.elements.insert(ins, fragments_new)

        coverage = self.check_code(code_new)

        if coverage and coverage[0] >= self.coverage[0]:
            # valid and coverage did not drop -> success
            self.extensions += 1
            self.code = code_new
            self.coverage = coverage
            self.cnt_no_extend = 0

            # repeat
            self.cnt_state += 1
            if self.cnt_state >= self.THRESH_REPEAT_EXTEND:
                self.cnt_state = 0
                self.state = self.STATE_REDUCE

        else:
            # extension failed

            # check if stuck in local maximum -> extend with allowed reduction in coverage
            self.cnt_no_extend += 1
            if (
                coverage
                and self.cnt_no_extend >= self.THRESH_NO_EXTEND_ALLOW_REDUCE_COV
            ):
                # valid and above threshold -> accept, even if coverage lower
                self.extensions_redcov += 1
                self.code = code_new
                self.coverage = coverage
                self.cnt_no_extend = 0
            elif self.cnt_no_extend >= self.THRESH_NO_EXTEND_TRY_REDUCE:
                self.cnt_no_extend = 0
                self.cnt_state = 0
                self.state = self.STATE_REDUCE

        return True

    def try_reduce(self):
        # TODO: make this more efficient
        code_new = CodeBlock(
            init_fragments=self.code.init_fragments,
            deinit_fragments=self.code.deinit_fragments,
        )
        code_orig_main = self.code.main_fragments

        len = code_orig_main.len()
        if len <= 1:
            # too small -> abort
            self.cnt_state = 0
            self.state = self.STATE_EXTEND
            return True

        A = random.randint(0, len - 1)
        codeA = code_orig_main.get_part(0, A)
        B = A + random.randint(1, 2)
        codeC = code_orig_main.get_part(B, len)

        code_new.main_fragments.add_list(codeA)
        code_new.main_fragments.add_list(codeC)

        coverage = self.check_code(code_new)

        # REDUCE AS LONG AS SUCCESSFUL
        self.cnt_state += 1

        if coverage and coverage[0] >= self.coverage[0]:
            # valid and coverage not reduced
            self.reductions += 1
            self.code = code_new
            self.coverage = coverage
            # success -> retry again 10 times
            self.cnt_state = 0

        if self.cnt_state >= self.THRESH_TRY_REDUCE:
            self.cnt_state = 0
            self.state = self.STATE_EXTEND

        return True

    def iteration(self):

        # init: try load and generate of initial code
        if self.state == self.STATE_INIT:
            ret = self.init()

        elif self.state == self.STATE_EXTEND:
            ret = self.try_extend()

        elif self.state == self.STATE_REDUCE:
            ret = self.try_reduce()

        # update code_len
        if self.code:
            self.code_len = self.code.main_len()
        else:
            self.code_len = 0

        return ret

    def task(self):
        for i in range(self.subiterations):
            ret = self.iteration()
            if not ret:
                break
        return (
            RunnerOutcome.COMPLETE,
            (self.code_len, self.coverage[0], self.coverage[1]),
        )

    def get_error_cause(self):
        return self.error_cause

    def task_post(self, ret):

        # handle stats
        if self.log:
            self.statslog.set_content(
                "generates: "
                + str(self.generates)
                + "\nignores: "
                + str(self.ignores)
                + "\ntimeouts: "
                + str(self.timeouts)
                + "\nerrors: "
                + str(self.errors)
                + "\nunknown_faults: "
                + str(self.unknown_faults)
                + "\ncompletes: "
                + str(self.completes)
                + "\nexceptions: "
                + str(self.exceptions)
                + "\nvalids: "
                + str(self.valids)
                + "\nextensions: "
                + str(self.extensions)
                + "\nextensions_redcov: "
                + str(self.extensions_redcov)
                + "\nreductions: "
                + str(self.reductions)
                + "\ncodelen: "
                + str(self.code_len)
                + "\ncoverage_points: "
                + str(self.coverage[0])
                + "\ncoverage_percent: "
                + str(self.coverage[1])
                + "\n"
            )

        # save code if coverage points increased
        if self.coverage[0] > self.coverage_last[0]:
            self.save_code(self.TESTCASE_CODE_FILENAME)

        self.coverage_last = self.coverage
        return ret

    def run_handler(
        self,
        blocking,
        subiterations,
        min_start_fragments,
        max_start_fragments,
        **kwargs
    ):

        self.runkwargs = kwargs
        self.subiterations = subiterations
        self.min_start_fragments = min_start_fragments
        self.max_start_fragments = max_start_fragments
        return super().run_handler(blocking=blocking, **kwargs)
