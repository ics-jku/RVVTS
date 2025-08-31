#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-25 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

import os
import glob
from .CodeBlock import CodeBlock, CodeFragment
from .BasicRunner import Runner, RunnerOutcome, RunnerFile
from .CodeCheckRunner import CodeCheckRunner
from .CodeCompareRunner import CodeCompareRunner


def delta_code_reduction(runner, code, log=False, **kwargs):

    start = 0
    end = code.main_len()

    bad_code = code
    bad_ret = (RunnerOutcome.INVALID, None)
    bad = end
    good = -1
    test = bad // 2

    while bad - good > 1:

        if log:
            print("good=", good, "bad=", bad, "test=", test, end=" -> ")

        test_code = code.get_part(start, test)
        ret = runner.run(blocking=True, code=test_code.as_code(), **kwargs)
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


# TODO: integrate in class and rework/cleanup return
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
    # "good code" causes error -> minimization failed
    if res[0] != RunnerOutcome.COMPLETE:
        return (False, False, res, None, None)
    # get state code
    ref_mstate = res[1]["ref:"]

    # build program with state and bad instruction

    minimized_code = CodeBlock(
        init_fragments=good_code.init_fragments,
        deinit_fragments=good_code.deinit_fragments,
    )
    # add bad fragment
    minimized_fragment = code.main_fragments.get_part(good_idx, bad_idx)
    minimized_code.add(
        CodeFragment("    // INSTRUCTION (" + str(minimized_fragment.get_ann()) + ")")
    )
    minimized_code.add(minimized_fragment)
    # ############# try to minimize with minimized state

    # TODO: minimize state here
    minimized_code.set_init_fragments(
        ref_mstate.as_CodeFragmentList(minimized_fragment.get_ann())
    )

    # test, if init code succeeed (as wanted!)
    res = codecomparerunner.run(
        blocking=True, code=minimized_code.init_fragments.as_code(), **kwargs
    )
    if res[0] != RunnerOutcome.COMPLETE:
        # NOTE 1 (see also below at callee):
        # state init itself fails -> we can go two ways here:
        # 1. track original fail: we report a fail -> we get a reduced case of the original fail
        # return (False, res, None, None)
        # 2. track state init fail: we repeat code reduction and minimization for the state
        return (False, True, res, None, minimized_code)

    # test, if minimized_state fails (as wanted!)
    res = codecomparerunner.run(blocking=True, code=minimized_code.as_code(), **kwargs)
    if res[0] == RunnerOutcome.ERROR:
        return (True, True, res, ref_mstate, minimized_code)

    # ############# does not fail -> try to minimize with full minimized state

    # create testcase with full state
    minimized_code.set_init_fragments(ref_mstate.as_CodeFragmentList())

    # test, if init code succeeed (as wanted!)
    res = codecomparerunner.run(
        blocking=True, code=minimized_code.init_fragments.as_code(), **kwargs
    )
    if res[0] != RunnerOutcome.COMPLETE:
        # see NOTE 1 from above
        return (False, False, res, None, minimized_code)

    # test, if minimized fails (as wanted!)
    res = codecomparerunner.run(blocking=True, code=minimized_code.as_code(), **kwargs)
    if res[0] != RunnerOutcome.ERROR:
        return (False, False, res, None, None)

    return (True, False, res, ref_mstate, minimized_code)


class CodeErrMinRunner(Runner):
    def setup(self, config):

        super().setup(config)

        self.rv_extensions = config["rv_extensions"]

        self.CODE_STATUS_EXECUTED = "0: executed"
        self.CODE_STATUS_REDUCED = "1: reduced"
        self.CODE_STATUS_MINIMIZED = "2: minimized"
        self.CODE_STATUS_MINIMIZED_STATE = "4: minimized_state"
        self.code_status = None

        # TODO: move these to a list -> simplify code
        self.tests = 0
        self.completes = 0
        self.ignores = 0
        self.timeouts = 0
        self.unknown_faults = 0
        self.errors = 0
        self.reductions = 0
        self.minimizations_state = 0
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
        # runners for intermediate steps (no coverage)
        self.codecomparerunner_red = CodeCompareRunner(config=subconfig_check)
        self.codecomparerunner_min = self.codecomparerunner_red

        # runner for register values
        self.codecheckrunner = CodeCheckRunner(config=subconfig_check)

        self.reset_run()

    def reset_run(self):
        self.orig_code_block = None
        self.orig_end_ref_mstate = None
        self.orig_end_dut_mstate = None

        self.res_code_block = None
        self.res_end_ref_mstate = None
        self.res_end_dut_mstate = None

        self.red_code_block = None
        self.red_end_ref_mstate = None
        self.red_end_dut_mstate = None

        self.min_code_block = None
        self.min_beg_mstate = None
        self.min_end_ref_mstate = None
        self.min_end_dut_mstate = None

        for f in glob.glob(self.dir + "/??_*.json"):
            os.remove(f)

    def redmin_code(self, code_block, recursion=False):

        code_status = self.CODE_STATUS_EXECUTED
        res_code_block = code_block

        # TEST INIT FRAGMENTS
        res = self.codecomparerunner_red.run(
            blocking=True,
            code=CodeBlock(main_fragments=code_block.init_fragments).as_code(),
            **self.runkwargs,
        )
        if res[0] != RunnerOutcome.COMPLETE:
            if recursion:
                # we are already investigating the init fragments recursively -> stop
                return (code_status, res_code_block, None)
            else:
                # the state initialization itself is the problem -> redmin state itself
                code_block = CodeBlock(
                    main_fragments=code_block.init_fragments,
                )
                return self.redmin_code(code_block, recursion=True)

        # TRY TO REDUCE

        (good_idx, bad_idx, reduced_code, ret_reduced) = delta_code_reduction(
            runner=self.codecomparerunner_red,
            code=code_block,
            log=False,
            **self.runkwargs,
        )
        if good_idx < 0:
            # the state initialization itself is the problem -> may not happen (was checked before)
            return (code_status, code_block, None)

        code_status = self.CODE_STATUS_REDUCED
        res_code_block = reduced_code
        self.red_code_block = res_code_block
        self.red_end_ref_mstate = self.codecomparerunner_red.compare_runner.ref_mstate
        self.red_end_dut_mstate = self.codecomparerunner_red.compare_runner.dut_mstate

        # TRY TO MINIMIZE

        (success, success_min_state, ret_minimize, min_beg_mstate, minimized_code) = (
            code_minimize(
                codecheckrunner=self.codecheckrunner,
                codecomparerunner=self.codecomparerunner_min,
                rv_extensions=self.rv_extensions,
                code=code_block,
                good_idx=good_idx,
                bad_idx=bad_idx,
                **self.runkwargs,
            )
        )
        if not success:
            # minimization failed
            if recursion or (minimized_code is None):
                # recursion or other error -> minimization failed -> return reduction result
                return (code_status, res_code_block, ret_reduced)
            else:
                # NOTE 1 (see also above in code_minimize):
                # we got an the state initialization that caused problems -> redmin state
                code_block = CodeBlock(
                    main_fragments=minimized_code.init_fragments,
                )
                return self.redmin_code(code_block, recursion=True)

        if success_min_state:
            code_status = self.CODE_STATUS_MINIMIZED_STATE
        else:
            code_status = self.CODE_STATUS_MINIMIZED

        res_code_block = minimized_code
        self.min_code_block = res_code_block
        self.min_beg_mstate = min_beg_mstate
        self.min_end_ref_mstate = self.codecomparerunner_min.compare_runner.ref_mstate
        self.min_end_dut_mstate = self.codecomparerunner_min.compare_runner.dut_mstate

        bad_ins = str(
            code_block.main_fragments.get_part(good_idx, good_idx + 1).as_list()[-1]
        )
        bad_ins = bad_ins.strip().split("\n")[-1]  # last line
        bad_ins = bad_ins.strip().split()[0]  # instr
        self.error_cause = bad_ins
        self.instr_errors[bad_ins] = self.instr_errors.get(bad_ins, 0) + 1

        return (code_status, res_code_block, ret_minimize)

    def task(self):

        # test
        ret = self.codecomparerunner.run(
            blocking=True, code=self.orig_code_block.as_code(), **self.runkwargs
        )

        self.error_cause = "unknown"
        self.res_code_block = self.orig_code_block
        self.res_end_ref_mstate = self.codecomparerunner.compare_runner.ref_mstate
        self.res_end_dut_mstate = self.codecomparerunner.compare_runner.dut_mstate
        self.orig_end_ref_mstate = self.res_end_ref_mstate
        self.orig_end_dut_mstate = self.res_end_dut_mstate
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

        (code_status, res_code_block, ret2) = self.redmin_code(self.res_code_block)
        if code_status == self.CODE_STATUS_EXECUTED:
            # nothing to do
            pass
        elif code_status == self.CODE_STATUS_REDUCED:
            self.reductions += 1
            ret = ret2
        elif code_status == self.CODE_STATUS_MINIMIZED:
            self.reductions += 1
            self.minimizations += 1
        elif code_status == self.CODE_STATUS_MINIMIZED_STATE:
            self.reductions += 1
            self.minimizations_state += 1
            ret = ret2
        else:
            raise Exception("internal error: invalid code_status from redmin")

        self.code_status = code_status
        self.res_code_block = res_code_block
        return ret

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
                + "\nminimizations_state: "
                + str(self.minimizations_state)
                + "\n"
            )

        if ret[0] == RunnerOutcome.ERROR:
            # if error -> re-run for later backup (e.g. ArchiveRunner)
            ret = self.codecomparerunner.run(
                blocking=True, code=self.res_code_block.as_code(), **self.runkwargs
            )
            self.res_end_ref_mstate = self.codecomparerunner.compare_runner.ref_mstate
            self.res_end_dut_mstate = self.codecomparerunner.compare_runner.dut_mstate

        # helper for saving mstate and code_blocks if not None
        def save_data(data, filename):
            if data is None:
                return
            data.save(self.dir + "/" + filename)

        save_data(self.orig_code_block, "00_orig_code_block.json")
        save_data(self.orig_end_ref_mstate, "00_orig_end_ref_mstate.json")
        save_data(self.orig_end_dut_mstate, "00_orig_end_dut_mstate.json")

        save_data(self.red_code_block, "01_red_code_block.json")
        save_data(self.red_end_ref_mstate, "01_red_end_ref_mstate.json")
        save_data(self.red_end_dut_mstate, "01_red_end_dut_mstate.json")

        save_data(self.min_code_block, "02_min_code_block.json")
        save_data(self.min_beg_mstate, "02_min_beg_mstate.json")
        save_data(self.min_end_ref_mstate, "02_min_end_ref_mstate.json")
        save_data(self.min_end_dut_mstate, "02_min_end_dut_mstate.json")

        save_data(self.res_code_block, "99_res_code_block.json")
        save_data(self.res_end_ref_mstate, "99_res_end_ref_mstate.json")
        save_data(self.res_end_dut_mstate, "99_res_end_dut_mstate.json")

        return ret

    def run_handler(self, blocking, code_block, **kwargs):

        self.reset_run()
        self.runkwargs = kwargs
        self.orig_code_block = code_block

        return super().run_handler(blocking=blocking, **kwargs)
