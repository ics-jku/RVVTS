#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#


# TODO: I, V, (F,D) -- add random init of registers


from .CodeBlock import CodeBlock, CodeFragmentList, CodeFragment

import random
import re
import copy

START_SYMBOL = "<start>"
RE_NONTERMINAL = re.compile(r"(<[^<> ]*>)")


class ExpansionException(Exception):
    def __init__(self, message):
        self.message = message


def nonterminals(expansion):
    return RE_NONTERMINAL.findall(expansion)


def is_nonterminal(s):
    return RE_NONTERMINAL.match(s)


# recursive depth first grammar isg
# NOTE: does not support recursive grammars
# TODO: implement logging
def grammarISG(
    grammar,
    start_symbol=START_SYMBOL,
    log=False,
):

    term = start_symbol
    ntsyms = nonterminals(term)

    gann = {}

    def gann_add(ann):
        # create union of annotations
        for k, e in ann.items():
            if not isinstance(e, set):
                e = {e}
            if k not in gann:
                gann[k] = e
            else:
                gann[k].update(e)

    while True:
        if len(ntsyms) == 0:
            # no more non-terminal symbols -> done
            break

        # get next symbol and expand from grammar
        ntsym = ntsyms.pop()
        exp = grammar[ntsym]

        # ensure that exp is a string
        while True:

            if isinstance(exp, str):
                # done
                break

            # exp is a list -> multiple alternatives > select one randomly
            elif isinstance(exp, list):
                exp = random.choice(exp)

            # exp is callable -> call
            elif callable(exp):
                exp = exp()

            # exp is tuple -> annotated entry
            elif isinstance(exp, tuple):
                ann = copy.deepcopy(exp[1])
                exp = exp[0]
                if not isinstance(ann, dict):
                    raise ExpansionException(
                        "Annotation in " + repr(exp) + " is not a dictionary"
                    )

                # resolve value substitutions ("_") in annotations
                val = None
                # check all keys in annotation
                for k in ann:
                    e = ann[k]
                    # do we have a substitution?
                    if e != "_":
                        continue

                    # recursively evaluate value of expression once
                    if val is None:
                        val, sann = grammarISG(grammar, start_symbol=exp)
                        exp = val
                        # add subexp annotations to global annotations
                        gann_add(sann)
                    ann[k] = {val}

                # add exp annotations to global annotations
                gann_add(ann)

            else:
                raise ExpansionException(
                    "Cannot expand " + repr(exp) + ": unknown type"
                )

        # update term and nsyms
        term = term.replace(ntsym, exp, 1)
        ntsyms = nonterminals(term)

    return (term, gann)


class RandLabelGenerator:
    def __init__(self):
        self.gen_label_cnt = 0
        self.used_label_cnt = 0

    def gen_first(self):
        self.gen_label_cnt = 0
        self.used_label_cnt = 0
        return self.gen()

    def gen(self):
        ret = "_label" + str(self.gen_label_cnt) + ":"
        self.gen_label_cnt += 1
        return ret

    def get(self):
        label = random.randint(0, self.gen_label_cnt * 2)
        if label >= self.gen_label_cnt:
            # used_label_cnt = self.gen_label_cnt
            label = self.used_label_cnt
            self.used_label_cnt += 1
        ret = "_label" + str(label)
        return ret

    def gen_last(self):
        ret = ""
        # fixup
        while self.gen_label_cnt < self.used_label_cnt:
            ret += self.gen() + "\n"
        return ret


class RegAlloc:
    def __init__(self, number=32, prefix="x"):

        self.prefix = prefix

        self.NONE = 0x0
        self.ALL = (1 << number) - 1

        self.free = self.ALL

    def free(self, reg):
        self.free |= (1 << reg) & self.ALL

    def free_all(self):
        self.free = self.ALL

    def alloc(self, reg):
        if not self.free & (1 << reg):
            return None
        self.free &= ~(1 << reg)
        return self.prefix + str(reg)

    def alloc_random(self, request_mask=0x1F):  # self.ALL):
        # short path -> no requested reg is free
        if (self.free & request_mask) == self.NONE:
            return None
        # find
        while True:
            reg = random.randint(0, 31)
            if (1 << reg) & request_mask & self.free:
                return self.alloc(reg)
        return None


class RandRegImmGenerator:
    def __init__(self):
        pass

    def get_regnr(self, min=0, max=31):
        return str(random.randint(min, max))

    def get_imm(self, bits):
        return str(random.randint(-(2 ** (bits - 1)), +(2 ** (bits - 1)) - 1))

    def get_immu(self, bits):
        return str(random.randint(0, 2**bits - 1))


class ProgramGenerator:
    def __init__(self, config=None):
        pass

    # may override
    def gen_init_fragments(self, log=False, **kwargs):
        return CodeFragmentList()

    # must override
    def gen_fragment(self, log=False, **kwargs):
        return CodeFragment()

    # may override
    def gen_deinit_fragments(self, log=False, **kwargs):
        return CodeFragmentList()

    def gen_code_block(self, min_fragments=0, max_fragments=10, log=False, **kwargs):

        fkwargs = dict(log=log, **kwargs)

        block = CodeBlock()

        if log:
            print("-------------- Init Fragments")
        block.set_init_fragments(self.gen_init_fragments(**fkwargs))

        max_line_idx = random.randint(min_fragments, max_fragments) + 1
        for fragment_idx in range(1, max_line_idx):
            if log:
                print("-------------- Fragment", fragment_idx)
            block.add(self.gen_fragment(**fkwargs))

        if log:
            print("-------------- Deinit Fragment")
        block.set_deinit_fragments(self.gen_deinit_fragments(**fkwargs))

        return block
