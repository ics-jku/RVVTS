#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#


# TODO: I, V, (F,D) -- add random init of registers


from .BasicRunner import RunnerOutcome
from .CodeBlock import CodeFragmentList
from .ISG_Base import ProgramGenerator
from .ISG_RVI import RVProgramGenerator
from .ISG_RVB import RVBProgramGenerator
from .ISG_RVV import RVVProgramGenerator

import random
import time


class ProgramMultiGenerator(ProgramGenerator):
    def __init__(self, config=None, classes=None):

        self.rvisacfg = config["rvisacfg"]
        self.gen = []

        if classes is None:
            # no classes explicitly given -> generate based on config
            classes = [RVProgramGenerator]
            if self.rvisacfg.is_under_test("b") or self.rvisacfg.is_under_test("zbc"):
                classes.append(RVBProgramGenerator)
            if self.rvisacfg.is_under_test("v"):
                classes.append(RVVProgramGenerator)

        for gen_class in classes:
            self.gen.append(gen_class(config))

    def gen_init_fragments(self, **kwargs):
        fragments = CodeFragmentList()
        for gen in self.gen:
            fragments.add_list(gen.gen_init_fragments(**kwargs))
        return fragments

    def gen_deinit_fragments(self, **kwargs):
        fragments = CodeFragmentList()
        for gen in self.gen:
            fragments.add_list(gen.gen_deinit_fragments(**kwargs))
        return fragments

    def gen_fragment(self, **kwargs):
        return random.choice(self.gen).gen_fragment(**kwargs)


def ISG_run(
    program_generator=None,
    codecomparerunner=None,
    min_fragments=2,
    max_fragments=100,
    runner=None,
    iter=1000,
    timeout=1,
    **kwargs
):

    errors = 0
    ignores = 0
    timeouts = 0

    start = time.clock_gettime(time.CLOCK_MONOTONIC)
    for i in range(iter):
        print(
            "\r",
            i + 1,
            "/",
            iter,
            " ",
            ignores,
            " ignores",
            " ",
            errors,
            " errors",
            " ",
            timeouts,
            " timeouts",
            end="",
        )

        code = program_generator.gen_code_block(
            min_fragments=min_fragments, max_fragments=max_fragments
        )

        ret = codecomparerunner.run(
            blocking=True, code=code.as_code(), timeout=timeout, **kwargs
        )
        if ret[0] == RunnerOutcome.TIMEOUT:
            timeouts += 1
        elif ret[0] == RunnerOutcome.IGNORE:
            ignores += 1
        elif ret[0] != RunnerOutcome.COMPLETE:
            errors += 1
        #    return code
        #    print()
        #    print(ret[0])
        #    print(ret[1])
        #    print(code)
        #    print("CHECK")
        #    return
        # else:
        #    validcodelist.append(code)
    print(
        "\r",
        i + 1,
        "/",
        iter,
        " ",
        ignores,
        " ignores",
        " ",
        errors,
        " errors",
        " ",
        timeouts,
        " timeouts",
    )
    end = time.clock_gettime(time.CLOCK_MONOTONIC)
    diff = end - start
    print(iter, " iterations in ", diff, "seconds")
    print(diff / iter, " seconds per iteration")
    print(iter / diff, " iterations per second")
