#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .CodeBlock import CodeBlock, CodeFragment
from .BasicRunner import Runner, RunnerOutcome, RunnerFile
from .CodeCheckRunner import CodeCheckRunner
from .CodeCompareRunner import CodeCompareRunner


def delta_code_reduction(runner, code, log=False):

    start = 0
    end = code.main_len()

    bad_code = code
    bad_ret = (RunnerOutcome.INVALID, None)
    bad = end
    good = 0
    test = bad // 2

    while bad - good > 1:

        if log:
            print("good=", good, "bad=", bad, "test=", test, end=" -> ")

        test_code = code.get_part(start, test)
        ret = runner.run(timeout=2.0, blocking=True, code=test_code.as_code())
        if ret[0] != RunnerOutcome.COMPLETE:
            if log:
                print("bad")
            # first half bad -> reduce
            bad = test
            bad_code = test_code
            bad_ret = ret
            test -= (bad - good) // 2
        else:
            if log:
                print("good")
            good = test
            test += (bad - good) // 2
            if test > end:
                # TODO
                print("ERROR")
                return None

    return (good, bad, bad_code, bad_ret)


def gen_byte_data(symname, values):
    data = (symname + ":").ljust(9) + ".byte "
    for value in values:
        data += f"{value:#0{2+2}x}" + ","
    return data[:-1] + ""


def code_minimize(
    codecheckrunner: CodeCheckRunner,
    codecomparerunner: CodeCompareRunner,
    code: CodeBlock,
    good_idx,
    bad_idx,
    rv_extensions="",
    **kwargs,
):

    # use good code to create state (registers)
    good_code = code.get_part(0, good_idx)
    res = codecheckrunner.run(blocking=True, code=good_code.as_code(), **kwargs)

    # TODO: check res for error -> exception?

    # build program with state and bad instruction

    minimized_code = CodeBlock(
        init_fragments=good_code.init_fragments,
        deinit_fragments=good_code.deinit_fragments,
    )

    # add state code
    ref_mstate = res[1]["ref:"]
    minimized_code.set_init_fragments(ref_mstate.as_CodeFragmentList())
    # add bad fragment
    minimized_code.add(CodeFragment("    // INSTRUCTION"))
    minimized_code.add(code.main_fragments.get_part(good_idx, bad_idx))

    # test, if minimized fails (as wanted!)
    res = codecomparerunner.run(blocking=True, code=minimized_code.as_code(), **kwargs)

    return (res, minimized_code)


class CodeErrMinRunner(Runner):
    def setup(self, config):

        super().setup(config)

        self.rv_extensions = config["rv_extensions"]

        self.CODE_STATUS_EXECUTED = "0: executed"
        self.CODE_STATUS_REDUCED = "1: reduced"
        self.CODE_STATUS_MINIMIZED = "2: minimized"
        self.code_status = None

        self.tests = 0
        self.completes = 0
        self.ignores = 0
        self.timeouts = 0
        self.unknown_faults = 0
        self.errors = 0
        self.reductions = 0
        self.minimizations = 0
        self.instr_errors = {}

        if config["log"]:
            self.status = RunnerFile(dir=self.get_dir(), name="code_status.log")
            self.statslog = RunnerFile(dir=self.get_dir(), name="stats.log")

        subconfig_compare = config.copy()
        subconfig_compare["dir"] = self.get_dir()
        subconfig_check = subconfig_compare.copy()
        # disable coverage in check runner -> performance
        subconfig_check["RefCovRunner_coverage"] = None

        # runner for tests
        self.codecomparerunner = CodeCompareRunner(config=subconfig_compare)

        # runner for register values
        self.codecheckrunner = CodeCheckRunner(config=subconfig_check)

    def task(self):

        # test
        ret = self.codecomparerunner.run(
            blocking=True, code=self.code_block.as_code(), **self.runkwargs
        )

        self.error_cause = "unknown"
        self.res_code_block = self.code_block
        self.code_status = self.CODE_STATUS_EXECUTED
        self.tests += 1

        if ret[0] == RunnerOutcome.COMPLETE:
            self.completes += 1
            return ret
        elif ret[0] == RunnerOutcome.IGNORE:
            self.ignores += 1
            return ret
        elif ret[0] == RunnerOutcome.TIMEOUT:
            # TODO: improve in future -> try to remove timeout
            self.timeouts += 1
            return ret
        elif ret[0] != RunnerOutcome.ERROR:
            # paranoia fallback (unkown error -> stop)
            self.unknown_faults += 1
            return ret
        self.errors += 1

        # TRY TO REDUCE

        (good_idx, bad_idx, reduced_code, ret_reduced) = delta_code_reduction(
            runner=self.codecomparerunner, code=self.code_block, log=False
        )
        # CAUTION: good_idx == 0 does not indicate a failed reduction.
        # It rather indicates that the first instruction is failing
        # if good_idx == 0:
        #    # no reduction possible -> return original result
        #    return ret
        self.reductions += 1
        self.code_status = self.CODE_STATUS_REDUCED
        self.res_code_block = reduced_code

        # TRY TO MINIMIZE

        (ret_minimize, minimized_code) = code_minimize(
            codecheckrunner=self.codecheckrunner,
            codecomparerunner=self.codecomparerunner,
            rv_extensions=self.rv_extensions,
            code=self.code_block,
            good_idx=good_idx,
            bad_idx=bad_idx,
            **self.runkwargs,
        )
        if ret_minimize[0] != RunnerOutcome.ERROR:
            # minimization failed -> return reduction result
            return ret_reduced
        self.minimizations += 1
        self.code_status = self.CODE_STATUS_MINIMIZED
        self.res_code_block = minimized_code

        bad_ins = str(
            self.code_block.main_fragments.get_part(good_idx, good_idx + 1).as_list()[
                -1
            ]
        )
        bad_ins = bad_ins.strip().split("\n")[-1]  # last line
        bad_ins = bad_ins.strip().split()[0]  # instr
        self.error_cause = bad_ins
        self.instr_errors[bad_ins] = self.instr_errors.get(bad_ins, 0) + 1

        return ret_minimize

    def get_error_cause(self):
        return self.error_cause

    def task_post(self, ret):

        # handle stats
        if self.log:
            self.status.set_content(self.code_status + "\n")
            self.statslog.set_content(
                "tests: "
                + str(self.tests)
                + "\ncompletes: "
                + str(self.completes)
                + "\nignores: "
                + str(self.ignores)
                + "\ntimeouts: "
                + str(self.timeouts)
                + "\nunknown_faults: "
                + str(self.unknown_faults)
                + "\nerrors: "
                + str(self.errors)
                + "\nreductions: "
                + str(self.reductions)
                + "\nminimizations: "
                + str(self.minimizations)
                + "\n"
            )

        self.code_block.save(self.dir + "/code_block.json")
        self.res_code_block.save(self.dir + "/res_code_block.json")

        if ret[0] != RunnerOutcome.ERROR:
            return ret

        # if error -> re-run for later backup (e.g. ArchiveRunner)
        return self.codecomparerunner.run(
            blocking=True, code=self.res_code_block.as_code(), **self.runkwargs
        )

    def run_handler(self, blocking, code_block, **kwargs):

        self.runkwargs = kwargs
        self.code_block = code_block
        return super().run_handler(blocking=blocking, **kwargs)
