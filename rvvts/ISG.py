#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#


# TODO: I, V, (F,D) -- add random init of registers


from .CodeBlock import CodeBlock, CodeFragmentList, CodeFragment
from .MachineState import MachineState
from .BasicRunner import RunnerOutcome

import time
import random
import re
import numpy as np


START_SYMBOL = "<start>"
RE_NONTERMINAL = re.compile(r"(<[^<> ]*>)")


class ExpansionException(Exception):
    def __init__(self, message):
        self.message = message


def nonterminals(expansion):
    # with the expansion being the first element
    if isinstance(expansion, tuple):
        expansion = expansion[0]

    return RE_NONTERMINAL.findall(expansion)


def is_nonterminal(s):
    return RE_NONTERMINAL.match(s)


# based on
# "The Fuzzing Book"
# by Andreas Zeller, Rahul Gopinath, Marcel Böhme, Gordon Fraser, and Christian Holler
def grammarISG(
    grammar,
    start_symbol=START_SYMBOL,
    max_nonterminals=10,
    max_expansion_trials=100,
    log=False,
):
    term = start_symbol
    expansion_trials = 0

    while len(nonterminals(term)) > 0:
        symbol_to_expand = random.choice(nonterminals(term))
        expansions = grammar[symbol_to_expand]
        if callable(expansions):
            # expansions is method -> execute
            expansion = expansions()
        else:
            # expansions is list -> choose
            expansion = random.choice(expansions)
        if callable(expansion):
            # expansion is method -> execute
            expansion = expansion()

        # with the expansion being the first element
        if isinstance(expansion, tuple):
            expansion = expansion[0]

        new_term = term.replace(symbol_to_expand, expansion, 1)

        if len(nonterminals(new_term)) < max_nonterminals:
            term = new_term
            if log:
                print("%-40s" % (symbol_to_expand + " -> " + expansion), term)
            expansion_trials = 0
        else:
            expansion_trials += 1
            if expansion_trials >= max_expansion_trials:
                raise ExpansionException("Cannot expand " + repr(term))

    return term


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


class ProgramMultiGenerator(ProgramGenerator):
    def __init__(self, config=None, classes=[]):
        self.gen = []
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


# ## RISC-V BASE INTEGER


class RVRegAlloc(RegAlloc):
    def __init__(self):
        super().__init__(number=32, prefix="x")
        self.ALL_NOT_ZERO = self.ALL & ~1


class CSRModGenerator:
    def __init__(self):
        self.regs = RVRegAlloc()

    def gen_csr_mod(self, csr, mask, values):

        # get temp register
        reg = self.regs.alloc_random(self.regs.ALL_NOT_ZERO)
        code = ""

        # clear mask from csr
        code += "    li " + reg + ", " + hex(mask) + "\n"
        code += "    csrc " + csr + ", " + reg + "\n"

        # select random value
        value = random.choice(values)

        # set value in csr
        if value != 0:
            code += "    li " + reg + ", " + hex(value) + "\n"
            code += "    csrs " + csr + ", " + reg + "\n"
        # print(code)
        self.regs.free_all()
        return "\n" + code + "\n"


class RVBoundedLoadStoreGenerator:
    def __init__(self, config=None):

        self.xlen = config["xlen"]
        self.xlen_mask = (1 << self.xlen) - 1
        self.memstart = config["memstart"]
        self.memlen = config["memlen"]
        self.memend = self.memstart + self.memlen
        self.memlen_mask = (1 << self.memlen.bit_length() - 1) - 1
        self.regs = RVRegAlloc()

        # instruction and alignment
        self.LOAD_RV32 = [("lb", 1), ("lh", 2), ("lw", 4), ("lbu", 1), ("lhu", 2)]
        self.LOAD_RV64 = self.LOAD_RV32 + [("ld", 8), ("lwu", 4)]
        self.LOAD_RV128 = self.LOAD_RV64 + [("lq", 16), ("ldu", 8)]
        self.STORE_RV32 = [("sb", 1), ("sh", 2), ("sw", 4)]
        self.STORE_RV64 = self.STORE_RV32 + [("sd", 8)]
        self.STORE_RV128 = self.STORE_RV64 + [("sq", 16)]

        if self.xlen == 32:
            self.LOAD = self.LOAD_RV32
            self.STORE = self.STORE_RV32
        elif self.xlen == 64:
            self.LOAD = self.LOAD_RV64
            self.STORE = self.STORE_RV64
        elif self.xlen == 128:
            self.LOAD = self.LOAD_RV128
            self.STORE = self.STORE_RV128
        else:
            raise Exception(
                "xlen="
                + str(self.xlen)
                + " not supported! Valid values are 32, 64 or 128"
            )

    def _get_int_imm(self, bits):
        return random.randint(-(2 ** (bits - 1)), +(2 ** (bits - 1)) - 1)

    def _gen_code(self, instr_name="", instr_alignment=1):
        # generates the marked part in given bounds
        # "<LOAD/STORE_instr> <rs2>, <imm12>(<rs1>)",
        #                     ---------------------

        # src/dst may by zero
        rs2 = self.regs.alloc_random(self.regs.ALL)
        # address
        rs1 = self.regs.alloc_random(self.regs.ALL_NOT_ZERO)
        # offset
        imm12 = self._get_int_imm(12)
        # scratch register for calculation
        rs_scratch = self.regs.alloc_random(self.regs.ALL_NOT_ZERO)

        alignment_mask = (
            self.xlen_mask << (instr_alignment.bit_length() - 1)
        ) & self.xlen_mask
        mask = self.memlen_mask & alignment_mask

        code = "\n"
        # ensure, that address is below memend and proper aligned
        code += "    li " + rs_scratch + ", " + hex(mask) + "\n"
        code += "    and " + rs1 + ", " + rs1 + ", " + rs_scratch + "\n"
        # ensure, that address is above memstart
        code += "    li " + rs_scratch + ", " + hex(self.memstart - imm12) + "\n"
        code += "    add " + rs1 + ", " + rs1 + ", " + rs_scratch + "\n"
        # load/store instr
        code += "    " + instr_name + " " + rs2 + ", " + hex(imm12) + "(" + rs1 + ")\n"

        self.regs.free_all()

        return code

    def _gen(self, instr_list):
        instr = random.choice(instr_list)
        return self._gen_code(instr_name=instr[0], instr_alignment=instr[1])

    def gen_load(self):
        return self._gen(self.LOAD)

    def gen_store(self):
        return self._gen(self.STORE)

    def test(self, instr_alignment=1):
        addr = 0xFFF84121231 + self._get_int_imm(64)
        imm12 = self._get_int_imm(12)

        # TODO misalignment by imm
        # alignment_mask = ~( (1 << (instr_alignment - 1)) - 1)
        alignment_mask = (
            self.xlen_mask << (instr_alignment.bit_length() - 1)
        ) & self.xlen_mask
        # print(hex(self.memlen_mask))
        # self.memlen_mask = (1 << self.memlen.bit_length() - 2) - 1
        # mask = self.memlen_mask & alignment_mask
        # print(hex(self.memlen_mask))
        # print(hex(mask))

        # imm12 = imm12 & alignment_mask
        below = addr & self.memlen_mask & alignment_mask

        above = below + (self.memstart - imm12)

        # align = above & (alignment_mask)
        # print("align", hex(align))
        align = above

        access = align + imm12

        err = False
        if access < self.memstart:
            print("ERR BELOW")
            err = True
        if access >= self.memend:
            print("ERR ABOVE")
            err = True

        if err:
            print("amask", hex(alignment_mask))
            print("addr", hex(addr))
            print("imm ", hex(imm12))
            print("beg ", hex(self.memstart))
            print("len ", hex(self.memlen))
            print("end ", hex(self.memend))

            print("below", hex(below))
            print("above", hex(above))
            print("access", hex(access))
        return err


# ALTERNATIVE FOR LOAD WITHOUT SCRATCH REGISTER
# def get_int_imm(bits):
#     return random.randint(-2**(bits-1), +2**(bits-1)-1)
#
# def gen_load():
#     #"<STORE_instr> <rs2>, <imm12>(<rs1>)",
#     regalloc = IRegAlloc()
#     # ensure different registers & non-zero
#     # TODO: alternative: to test ld zero, ... we would need a third register instead of rs2(zero)
#     rs2 = regalloc.alloc_random(regalloc.ALL_NOT_ZERO)
#     rs1 = regalloc.alloc_random(regalloc.ALL_NOT_ZERO)
#     begin = memstart + memlen // 2
#     end = memstart + memlen
#     imm12 = get_int_imm(12)
#     #imm12 = 0x0
#     code = "\n"
#     code += "    li " + rs2 + ", 0xfff0\n" # len
#     code += "    and " + rs1 + ", " + rs1 + ", " + rs2 + "\n" # len
#     code += "    li " + rs2 + ", " + hex(begin - imm12) + "\n" # len
#     code += "    add " + rs1 + ", " + rs1 + ", " + rs2 + "\n"
#     code += "    ld " + rs2 + ", " + hex(imm12) + "(" + rs1 + ")\n"
#     return code


# x = RVBoundedLoadStoreGenerator(xlen = 64, dmemstart = 0x2000, dmemlen = 256*1024*1024)
# for i in range(10000):
#    x.test()


class RVRandRegImmGenerator(RandRegImmGenerator):
    def __init__(self):
        pass

    def get_reg(self, zero=True):
        if zero:
            min = 0
        else:
            min = 1
        return "x" + self.get_regnr(min, 31)

    def get_shamt5(self):
        return self.get_immu(5)

    def get_imm12(self):
        return self.get_imm(12)

    def get_imm12u(self):
        return self.get_immu(12)

    def get_imm20(self):
        return self.get_imm(20)

    def get_imm20u(self):
        return self.get_immu(20)


class RVProgramGenerator(ProgramGenerator):
    def __init__(self, config=None):

        self.mstate = MachineState(config)
        self.rlg = RandLabelGenerator()
        self.rrig = RVRandRegImmGenerator()

        # use full memory (memstart, memlen) for loads
        self.blsg_load = RVBoundedLoadStoreGenerator(config=config)

        # use only dmemory (dmemstart, dmemlen) for stores (protect program)
        config_partmem = config.copy()
        config_partmem["memstart"] = config_partmem["dmemstart"]
        config_partmem["memlen"] = config_partmem["dmemlen"]
        self.blsg_store = RVBoundedLoadStoreGenerator(config=config_partmem)

        self.__def_grammar()

    def gen_init_fragments(self, **kwargs):
        self.mstate.init(self.mstate.VALUE_MODE_RAND)
        ret = self.mstate.as_CodeFragmentList()
        ret.add(CodeFragment(self.rlg.gen_first()))
        return ret

    def gen_fragment(self, **kwargs):
        return CodeFragment(grammarISG(self.grammar, **kwargs))

    def gen_deinit_fragments(self, **kwargs):
        return CodeFragmentList(CodeFragment(self.rlg.gen_last()))

    def __def_grammar(self):
        self.grammar = {
            "<start>": ["<line>"],
            "<line>": [
                # "<gen_label>",
                "    <instr_calc>",
                "    <instr_calc>",
                "    <instr_calc>",
                # "    <instr_control>", #### TODO
                "    <instr_load_store>",
            ],
            "<gen_label>": self.rlg.gen,
            "<get_label>": self.rlg.get,
            "<instr_calc>": [
                "<I_instr> <rd>, <rs1>, <imm12>",
                "sltiu <rd>, <rs1>, <imm12u>",
                "<SHAMT_instr> <rd>, <rs1>, <shamt5>",
                "<U_instr> <rd>, <imm20u>",
                "<R_instr> <rd>, <rs1>, <rs2>",
            ],
            "<instr_control>": [
                # "<J_instr> <rd>, <get_label>", ### TODO
                # "jalr <rd>, <rs1>, <get_label>", ### TODO
                "<B_instr> <rs1>, <rs2>, <get_label>",
            ],
            "<instr_load_store>": [
                "<instr_load>",
                "<instr_store>",
            ],
            "<instr_load>": self.blsg_load.gen_load,
            "<instr_store>": self.blsg_store.gen_store,
            "<I_instr>": ["addi", "slti", "andi", "ori", "xori"],
            "<SHAMT_instr>": ["slli", "srli", "srai"],
            "<U_instr>": ["lui", "auipc"],
            "<R_instr>": [
                "add",
                "slt",
                "sltu",
                "and",
                "or",
                "xor",
                "sll",
                "srl",
                "sub",
                "sra",
            ],
            "<J_instr>": ["jal"],
            "<B_instr>": ["beq", "bne", "blt", "bltu", "bge", "bgeu"],
            "<rd>": ["<reg>"],
            "<rs1>": ["<reg>"],
            "<rs2>": ["<reg>"],
            "<reg>": self.rrig.get_reg,
            "<shamt5>": self.rrig.get_shamt5,
            "<imm12>": self.rrig.get_imm12,
            "<imm12u>": self.rrig.get_imm12,
            "<imm20>": self.rrig.get_imm20,
            "<imm20u>": self.rrig.get_imm20u,
        }


# ## RISC-V FLOAT


class RVFRandRegImmGenerator(RandRegImmGenerator):
    def __init__(self):
        pass

    def get_freg(self, zero=True):
        if zero:
            min = 0
        else:
            min = 1
        return "f" + self.get_regnr(min, 31)


# ## RISC-V Vector


class RVVRegAlloc(RegAlloc):
    def __init__(self):
        super().__init__(number=32, prefix="v")


class RVVRandRegImmGenerator(RandRegImmGenerator):
    def __init__(self):
        self.CNT_MAX = 32
        self.masked = 0
        self.emul = 0
        self.regs = 0
        self.cnt = 0
        self.reserved = 0x0

    def get_uimm5(self):
        return self.get_immu(5)

    def get_imm5(self):
        return self.get_imm(5)

    def get_vreg(self):
        if self.cnt == 0:
            # apply new configuration
            self.masked = random.randint(0, 1)
            self.emul = 2 ** random.randint(0, 3)
            self.regs = 32 // self.emul
            self.free = 0x0
            self.cnt = random.randint(1, self.CNT_MAX)

        # no more free registers -> start again
        if self.free == 0x0:
            self.free = ((1 << self.regs) - 1) & ~self.masked

        # prevent duplicates for first registers
        while True:
            # generate registers for given configuration
            reg_idx = random.randint(self.masked, self.regs - 1)
            # check if register is free -> return
            if (1 << reg_idx) & self.free:
                self.free &= ~(1 << reg_idx)
                break

        self.cnt -= 1
        reg = reg_idx * self.emul
        return "v" + str(reg)


class RVVBoundedLoadStoreGenerator:
    def __init__(self, config=None):

        self.xlen = config["xlen"]
        self.xlen_mask = (1 << self.xlen) - 1
        self.vector_vlen = config["vector_vlen"]
        self.vector_vlen_bytes = self.vector_vlen // 8
        self.vector_elen = config["vector_elen"]
        self.vector_elen_bytes = self.vector_elen // 8
        self.memstart = config["memstart"]
        self.memlen = config["memlen"]

        self.regs = RVRegAlloc()
        self.vrrig = RVVRandRegImmGenerator()

        # generator function, instruction, alignment, nfields, masking
        self.LOAD = []
        self.STORE = []
        for enc_eew in [8, 16, 32, 64]:

            # 7.4. Vector Unit-Stride Instructions - vector load/store
            self.LOAD.append(
                [
                    self._gen_code_unit_stride,
                    "vle" + str(enc_eew) + ".v",
                    enc_eew,
                    1,
                    True,
                ]
            )
            self.STORE.append(
                [
                    self._gen_code_unit_stride,
                    "vse" + str(enc_eew) + ".v",
                    enc_eew,
                    1,
                    True,
                ]
            )

            # 7.5. Vector Strided Instructions
            self.LOAD.append(
                [
                    self._gen_code_reg_stride,
                    "vlse" + str(enc_eew) + ".v",
                    enc_eew,
                    1,
                    True,
                ]
            )
            self.STORE.append(
                [
                    self._gen_code_reg_stride,
                    "vsse" + str(enc_eew) + ".v",
                    enc_eew,
                    1,
                    True,
                ]
            )

            # 7.6. Vector Indexed Instructions
            self.LOAD.append(
                [
                    self._gen_code_indexed,
                    "vluxei" + str(enc_eew) + ".v",
                    enc_eew,
                    1,
                    True,
                ]
            )
            self.LOAD.append(
                [
                    self._gen_code_indexed,
                    "vloxei" + str(enc_eew) + ".v",
                    enc_eew,
                    1,
                    True,
                ]
            )
            self.STORE.append(
                [
                    self._gen_code_indexed,
                    "vsuxei" + str(enc_eew) + ".v",
                    enc_eew,
                    1,
                    True,
                ]
            )
            self.STORE.append(
                [
                    self._gen_code_indexed,
                    "vsoxei" + str(enc_eew) + ".v",
                    enc_eew,
                    1,
                    True,
                ]
            )

            # 7.7. Unit-stride Fault-Only-First Loads (TODO: generate instruction with invalid reads)
            self.LOAD.append(
                [
                    self._gen_code_unit_stride,
                    "vle" + str(enc_eew) + "ff.v",
                    enc_eew,
                    1,
                    True,
                ]
            )

            # 7.8. Vector Load/Store Segment Instructions
            # start with nfields=2 (nf[2:0]=1) - see 7.2. Vector Load/Store Addressing Modes - page 31
            # nfields=1 is for regular load/stores (single value); nfields > 1 is for mult fields
            for nfields in range(2, 9):
                # 7.8.1. Vector Unit-Stride Segment Loads and Stores
                self.LOAD.append(
                    [
                        self._gen_code_unit_stride,
                        "vlseg" + str(nfields) + "e" + str(enc_eew) + ".v",
                        enc_eew,
                        nfields,
                        True,
                    ]
                )
                self.STORE.append(
                    [
                        self._gen_code_unit_stride,
                        "vsseg" + str(nfields) + "e" + str(enc_eew) + ".v",
                        enc_eew,
                        nfields,
                        True,
                    ]
                )
                self.LOAD.append(
                    [
                        self._gen_code_unit_stride,
                        "vlseg" + str(nfields) + "e" + str(enc_eew) + "ff.v",
                        enc_eew,
                        nfields,
                        True,
                    ]
                )
                # 7.8.2. Vector Strided Segment Loads and Stores
                self.LOAD.append(
                    [
                        self._gen_code_reg_stride,
                        "vlsseg" + str(nfields) + "e" + str(enc_eew) + ".v",
                        enc_eew,
                        nfields,
                        True,
                    ]
                )
                self.STORE.append(
                    [
                        self._gen_code_reg_stride,
                        "vssseg" + str(nfields) + "e" + str(enc_eew) + ".v",
                        enc_eew,
                        nfields,
                        True,
                    ]
                )
                # 7.8.3. Vector Indexed Segment Loads and Stores
                self.LOAD.append(
                    [
                        self._gen_code_indexed,
                        "vluxseg" + str(nfields) + "ei" + str(enc_eew) + ".v",
                        enc_eew,
                        nfields,
                        True,
                    ]
                )
                self.LOAD.append(
                    [
                        self._gen_code_indexed,
                        "vloxseg" + str(nfields) + "ei" + str(enc_eew) + ".v",
                        enc_eew,
                        nfields,
                        True,
                    ]
                )
                self.STORE.append(
                    [
                        self._gen_code_indexed,
                        "vsuxseg" + str(nfields) + "ei" + str(enc_eew) + ".v",
                        enc_eew,
                        nfields,
                        True,
                    ]
                )
                self.STORE.append(
                    [
                        self._gen_code_indexed,
                        "vsoxseg" + str(nfields) + "ei" + str(enc_eew) + ".v",
                        enc_eew,
                        nfields,
                        True,
                    ]
                )

            # 7.9. Vector Load/Store Whole Register Instructions - vector load
            for grp in [1, 2, 4, 8]:
                self.LOAD.append(
                    [
                        self._gen_code_unit_stride,
                        "vl" + str(grp) + "re" + str(enc_eew) + ".v",
                        enc_eew,
                        grp,
                        False,
                    ]
                )

        # 7.4. Vector Unit-Stride Instructions - mask load/store
        # special encoding -> enc_eew = 0 -> mask load/store
        self.LOAD.append([self._gen_code_unit_stride, "vlm.v", 0, 1, False])
        self.STORE.append([self._gen_code_unit_stride, "vsm.v", 0, 1, False])

        # 7.9. Vector Store Whole Register Instructions - vector store
        for grp in [1, 2, 4, 8]:
            self.STORE.append(
                [self._gen_code_unit_stride, "vs" + str(grp) + "r.v", 8, grp, False]
            )

    def _gen_code_unit_stride(self, name, enc_eew, nfields, masked):

        # base address
        rs1 = self.regs.alloc_random(self.regs.ALL_NOT_ZERO)
        # source/destination register
        vld = self.vrrig.get_vreg()

        # scratch register for calculation
        rs_scratch = self.regs.alloc_random(self.regs.ALL_NOT_ZERO)

        code = "\n"

        # ensure, that address is below memend and proper aligned
        if enc_eew == 0:
            # special encoding -> load/store mask
            # load/store always on single vector reg (vlenb)
            max_access_len = self.vector_vlen_bytes
            enc_eew = 8
        else:
            # assume max possible configuration: ( vlenb * m8 * number of fields ) [bytes]
            max_access_len = self.vector_vlen_bytes * 8 * nfields

        # upper bound
        unit_memlen = self.memlen - max_access_len
        unit_memlen_mask = (1 << unit_memlen.bit_length() - 1) - 1
        alignment = enc_eew // 8
        alignment_mask = (
            self.xlen_mask << (alignment.bit_length() - 1)
        ) & self.xlen_mask
        mask = unit_memlen_mask & alignment_mask
        code += "    li " + rs_scratch + ", " + hex(mask) + "\n"
        code += "    and " + rs1 + ", " + rs1 + ", " + rs_scratch + "\n"

        # ensure, that address is above memstart
        code += "    li " + rs_scratch + ", " + hex(self.memstart) + "\n"
        code += "    add " + rs1 + ", " + rs1 + ", " + rs_scratch + "\n"

        # load/store instr
        code += "    " + name + " " + vld + ", " + "(" + rs1 + ")"
        if masked:
            code += ", v0.t"
        code += "\n"

        self.regs.free_all()
        return code

    # Generate instructions from 7.5. Vector Strided Instructions and 7.8.2. Vector Strided Segment Loads and Stores
    # Difference to other generators: Instead of using run-time values from registers and modifying then according
    # to bounds, we explicitly generate random values and set registers accordingly.
    def _gen_code_reg_stride(self, name, enc_eew, nfields, masked):

        # base address
        rs1 = self.regs.alloc_random(self.regs.ALL_NOT_ZERO)
        # byte stride (allow zero)
        rs2 = self.regs.alloc_random(self.regs.ALL)
        # source/destination register
        vld = self.vrrig.get_vreg()

        # size of single element read
        element_read_size = nfields * enc_eew // 8

        # assume max possible configuration: ( vlenb * m8 * number of fields ) [bytes]
        max_access_len = self.vector_vlen_bytes * 8 * nfields

        # first addr outside of mem area
        memend = self.memstart + self.memlen - element_read_size - 1

        code = "\n"

        # generate a base address within range and proper alignment

        base_addr = random.sample(range(self.memstart, memend, element_read_size), 1)[0]
        code += "    li " + rs1 + ", " + hex(base_addr) + "\n"

        if rs2 != "zero" and rs2 != "x0":
            # generate a byte stride, so that all memory accesses stay in range
            alignment = enc_eew // 8
            max_nr_accesses = max_access_len // alignment
            # maximum negative stride in range with alignment
            memlen_before = base_addr - self.memstart
            max_neg_stride = (
                (memlen_before // max_nr_accesses) // alignment
            ) * alignment
            # maximum positive stride in range with alignment
            memlen_after = memend - base_addr
            max_pos_stride = (
                (memlen_after // max_nr_accesses) // alignment
            ) * alignment
            # choose stride randomly from given range
            byte_stride = random.sample(
                range(-max_neg_stride, max_pos_stride + 1, alignment), 1
            )[0]
            code += "    li " + rs2 + ", " + hex(byte_stride) + "\n"
            # last_addr = base_addr + byte_stride * max_nr_accesses
            # if last_addr >= memend:
            #    print("ERROR")

        # load/store instr
        code += "    " + name + " " + vld + ", " + "(" + rs1 + "), " + rs2
        if masked:
            code += ", v0.t"
        code += "\n"

        self.regs.free_all()
        return code

    # NOTE: The number of bits encoded in the instruction determines the eww of the index
    # vector, *NOT* the size of the load/store (sew of data vector). Therefore: Alignment depends
    # on the current eew set in vtype
    # TODO: We don't know lmul at generation time, but we have to make sure that vand of mask succeeds
    # to get valid adresse ranges for the subsequent load/store. The current solution is to only use
    # v8 and v16 registers, but this limits the variability of the instructions (always the same vs2
    # registers
    def _gen_code_indexed(self, name, enc_eew, nfields, masked):

        # base address
        rs1 = self.regs.alloc_random(self.regs.ALL_NOT_ZERO)
        # index vector (see TODO above)
        # vs2 = self.vrrig.get_vreg()
        vs2 = "v8"
        # source/destination register
        vld = self.vrrig.get_vreg()

        # registers to save vtype and vl
        rs_vtype = self.regs.alloc_random(self.regs.ALL_NOT_ZERO)
        rs_vl = self.regs.alloc_random(self.regs.ALL_NOT_ZERO)

        # scratch registers for calculation
        rs_scratch = self.regs.alloc_random(self.regs.ALL_NOT_ZERO)
        # vs_scratch = self.vrrig.get_vreg() (see TODO above)
        vs_scratch = "v16"

        code = "\n"

        # we need to modifiy the index vector register (sew) -> save vtype and vl
        code += "    csrr " + rs_vtype + ", vtype\n"
        code += "    csrr " + rs_vl + ", vl\n"

        # upper bound
        # set vtype to edit mask according to encoded eew but keep other settings
        # mask out sew and save in scratch
        code += (
            "    andi "
            + rs_scratch
            + ", "
            + rs_vtype
            + ", "
            + hex(~np.uint8(7 << 3))
            + "\n"
        )
        # set new sew from enc_eew (TODO: update vl?)
        code += (
            "    ori "
            + rs_scratch
            + ", "
            + rs_scratch
            + ", "
            + hex(((enc_eew // 8).bit_length() - 1) << 3)
            + "\n"
        )
        # code += "    vsetvl x0, " + rs_vl + ", " + rs_scratch + "\n"
        code += "    vsetvl " + rs_vl + ", " + rs_vl + ", " + rs_scratch + "\n"

        memlen_half_mask = (1 << self.memlen.bit_length() - 2) - 1
        # eew in vtype -> unknown -> assume nfields * 64 bit
        alignment = nfields * 64 // 8
        alignment_mask = (
            self.xlen_mask << (alignment.bit_length() - 1)
        ) & self.xlen_mask
        mask = memlen_half_mask & alignment_mask
        code += "    li " + rs_scratch + ", " + hex(mask) + "\n"
        # mask base_addr to memlen/2
        code += "    and " + rs1 + ", " + rs1 + ", " + rs_scratch + "\n"
        # mask all indices to memlen/2
        code += "    vand.vx " + vs2 + ", " + vs_scratch + ", " + rs_scratch + "\n"

        # ensure, that base_addr is above memstart
        code += "    li " + rs_scratch + ", " + hex(self.memstart) + "\n"
        code += "    add " + rs1 + ", " + rs1 + ", " + rs_scratch + "\n"

        # restore vtype and vl
        code += "    vsetvl x0, " + rs_vl + ", " + rs_vtype + "\n"

        # load/store instr
        code += "    " + name + " " + vld + ", " + "(" + rs1 + "), " + vs2
        if masked:
            code += ", v0.t"
        code += "\n"

        self.regs.free_all()
        return code

    def _gen(self, instr_list):
        instr = random.choice(instr_list)
        masked = False
        # print(instr)
        if instr[4]:
            masked = bool(random.getrandbits(1))
        return instr[0](instr[1], instr[2], instr[3], masked)

    def gen_load(self):
        return self._gen(self.LOAD)

    def gen_store(self):
        return self._gen(self.STORE)


class RVVProgramGenerator(ProgramGenerator):
    def __init__(self, config=None):

        self.has_float = sum(e in config["rv_extensions"] for e in "fdq") > 0

        self.csrmg = CSRModGenerator()
        self.rrig = RVRandRegImmGenerator()
        self.vrrig = RVVRandRegImmGenerator()
        self.frrig = RVFRandRegImmGenerator()

        # use full memory (memstart, memlen) for loads
        self.vblsg_load = RVVBoundedLoadStoreGenerator(config=config)

        # use only dmemory (dmemstart, dmemlen) for stores (protect program)
        config_partmem = config.copy()
        config_partmem["memstart"] = config_partmem["dmemstart"]
        config_partmem["memlen"] = config_partmem["dmemlen"]
        self.vblsg_store = RVVBoundedLoadStoreGenerator(config=config_partmem)

        self.__def_grammar()

    def gen_fragment(self, **kwargs):
        return CodeFragment(grammarISG(self.grammar, **kwargs))

    def gen_set_mstatus_en_vector(self):
        return self.csrmg.gen_csr_mod("mstatus", 0x600, [0x000, 0x600])

    def gen_set_mstatus_en_float(self):
        if self.has_float:
            return self.csrmg.gen_csr_mod("mstatus", 0x6000, [0x0000, 0x6000])
        else:
            return ""

    def gen_set_frm(self):
        if self.has_float:
            return self.csrmg.gen_csr_mod(
                "fcsr", (0x7 << 5), list((i << 5) for i in range(2**3))
            )
        else:
            return ""

    def gen_set_vxrm(self):
        return self.csrmg.gen_csr_mod("vxrm", 0x3, list(range(2**2)))

    def __def_grammar(self):
        self.grammar = {
            "<start>": ["    <line>"],
            "<line>": [
                "<instr_v_config>",
                "<instr_v_load_store>",
                "<instr_v_compute>",
                "<instr_v_compute>",
                "<instr_v_compute>",
                "<instr_v_compute>",
            ],
            "<instr_v_config>": [
                "<instr_v_config_vset>",
                "<instr_v_config_csrs>",
            ],
            "<instr_v_config_vset>": [
                "vsetvl <rd>, <rs1>, <rs2>",
                "vsetvli <rd>, <rs1>, <vtypei>",
                "vsetivli <rd>, <uimm5>, <vtypei>",
            ],
            "<instr_v_config_csrs>": [
                # enable/disable vector extension
                self.gen_set_mstatus_en_vector,
                # enable/disable floating point (vector floating point)
                self.gen_set_mstatus_en_float,
                # set floating point rounding mode
                self.gen_set_frm,
                # set vector fixed point rounding mode
                self.gen_set_vxrm,
            ],
            "<instr_v_load_store>": [
                "<instr_v_load>",
                "<instr_v_store>",
            ],
            # TODO: by using skip_on_exception we can use random loads here instead
            "<instr_v_load>": self.vblsg_load.gen_load,
            # TODO: event with skip_on_exception this is useful to prevent modifications of code
            # however: random code modification can be part of fuzzing!?
            "<instr_v_store>": self.vblsg_store.gen_store,
            "<vtypei>": ["<vsew>, <vlmul>, <vta>, <vma>"],
            "<vsew>": ["e8", "e16", "e32", "e64"],
            "<vmv_nr>": ["1", "2", "4", "8"],
            "<vlmul>": ["mf8", "mf4", "mf2", "m1", "m2", "m4", "m8"],
            "<vta>": ["tu", "ta"],
            "<vma>": ["mu", "ma"],
            "<instr_v_compute>": [
                "<instr_v_vector_integer>",
                "<instr_v_fixed_point>",
                "<instr_v_floating_point>",
                "<instr_v_vector_reduction>",
                "<instr_v_vector_mask>",
                "<instr_v_vector_permutation>",
            ],
            # ++++ 11. VECTOR INTEGER
            "<instr_v_vector_integer>": [
                # 11.1. single width int add/sub
                "vadd<.vv>",
                "vadd<.vx>",
                "vadd<.vi>",
                "vsub<.vv>",
                "vsub<.vx>",
                "vrsub<.vx>",
                "vrsub<.vi>",
                # 11.2. widening int add/sub
                "vwaddu<.vv>",
                "vwaddu<.vx>",
                "vwsubu<.vv>",
                "vwsubu<.vx>",
                "vwadd<.vv>",
                "vwadd<.vx>",
                "vwsub<.vv>",
                "vwsub<.vx>",
                "vwaddu<.wv>",
                "vwaddu<.wx>",
                "vwsubu<.wv>",
                "vwsubu<.wx>",
                "vwadd<.wv>",
                "vwadd<.wx>",
                "vwsub<.wv>",
                "vwsub<.wx>",
                # 11.3 int extension
                "vzext<.vfX>",
                "vsext<.vfX>",
                # 11.4. int add-with-carry / substract-with-borrow
                "vadc<.vvm>",
                "vadc<.vxm>",
                "vadc<.vim>",
                "vmadc<.vvm>",
                "vmadc<.vxm>",
                "vmadc<.vim>",
                "vmadc<.vv_novm>",
                "vmadc<.vx_novm>",
                "vmadc<.vi_novm>",
                "vsbc<.vvm>",
                "vsbc<.vxm>",
                "vmsbc<.vvm>",
                "vmsbc<.vxm>",
                "vmsbc<.vv_novm>",
                "vmsbc<.vx_novm>",
                # 11.5. bitwise logic
                "vand<.vv>",
                "vand<.vx>",
                "vand<.vi>",
                "vor<.vv>",
                "vor<.vx>",
                "vor<.vi>",
                "vxor<.vv>",
                "vxor<.vx>",
                "vxor<.vi>",
                # 11.6. single-width shift
                "vsll<.vv>",
                "vsll<.vx>",
                "vsll<.vi_uimm>",
                "vsrl<.vv>",
                "vsrl<.vx>",
                "vsrl<.vi_uimm>",
                "vsra<.vv>",
                "vsra<.vx>",
                "vsra<.vi_uimm>",
                # 11.7. narrowing int right shift
                "vnsrl<.wv>",
                "vnsrl<.wx>",
                "vnsrl<.wi>",
                "vnsra<.wv>",
                "vnsra<.wx>",
                "vnsra<.wi>",
                # 11.8. int compare
                "vmseq<.vv>",
                "vmseq<.vx>",
                "vmseq<.vi>",
                "vmsne<.vv>",
                "vmsne<.vx>",
                "vmsne<.vi>",
                "vmsltu<.vv>",
                "vmsltu<.vx>",
                "vmslt<.vv>",
                "vmslt<.vx>",
                "vmsleu<.vv>",
                "vmsleu<.vx>",
                "vmsleu<.vi>",
                "vmsle<.vv>",
                "vmsle<.vx>",
                "vmsle<.vi>",
                "vmsgtu<.vx>",
                "vmsgtu<.vi>",
                "vmsgt<.vx>",
                "vmsgt<.vi>",
                # 11.9. int min/max
                "vminu<.vv>",
                "vminu<.vx>",
                "vmin<.vv>",
                "vmin<.vx>",
                "vmaxu<.vv>",
                "vmaxu<.vx>",
                "vmax<.vv>",
                "vmax<.vx>",
                # 11.10. single-width int mult
                "vmul<.vv>",
                "vmul<.vx>",
                "vmulh<.vv>",
                "vmulh<.vx>",
                "vmulhu<.vv>",
                "vmulhu<.vx>",
                "vmulhsu<.vv>",
                "vmulhsu<.vx>",
                # 11.11. int divide
                "vdivu<.vv>",
                "vdivu<.vx>",
                "vdiv<.vv>",
                "vdiv<.vx>",
                "vremu<.vv>",
                "vremu<.vx>",
                "vrem<.vv>",
                "vrem<.vx>",
                # 11.12. widening int mult
                "vwmul<.vv>",
                "vwmul<.vx>",
                "vwmulu<.vv>",
                "vwmulu<.vx>",
                "vwmulsu<.vv>",
                "vwmulsu<.vx>",
                # 11.13 single-width int multiply-add
                "vmacc<.vv_mac>",
                "vmacc<.vx_mac>",
                "vnmsac<.vv_mac>",
                "vnmsac<.vx_mac>",
                "vmadd<.vv_mac>",
                "vmadd<.vx_mac>",
                "vnmsub<.vv_mac>",
                "vnmsub<.vx_mac>",
                # 11.14. widening int multiply-add
                "vwmaccu<.vv_mac>",
                "vwmaccu<.vx_mac>",
                "vwmacc<.vv_mac>",
                "vwmacc<.vx_mac>",
                "vwmaccsu<.vv_mac>",
                "vwmaccsu<.vx_mac>",
                "vwmaccus<.vx_mac>",
                # 11.15. int merge
                "vmerge<.vvm>",
                "vmerge<.vxm>",
                "vmerge<.vim>",
                # 11.16. int move
                "vmv.v.v <vd>, <vs1>",
                "vmv.v.x <vd>, <rs1>",
                "vmv.v.i <vd>, <imm5>",
            ],
            # ++++ 12. FIXED POINT
            "<instr_v_fixed_point>": [
                # 12.1. single-width saturating add/sub
                "vsaddu<.vv>",
                "vsaddu<.vx>",
                "vsaddu<.vi>",
                "vsadd<.vv>",
                "vsadd<.vx>",
                "vsadd<.vi>",
                "vssub<.vv>",
                "vssub<.vx>",
                "vssubu<.vv>",
                "vssubu<.vx>",
                # 12.2. single-width averaging add/sub
                "vaaddu<.vv>",
                "vaaddu<.vx>",
                "vaadd<.vv>",
                "vaadd<.vx>",
                "vasubu<.vv>",
                "vasubu<.vx>",
                "vasub<.vv>",
                "vasub<.vx>",
                # 12.3. single-width fractional mul with rounding and saturation
                "vsmul<.vv>",
                "vsmul<.vx>",
                # 12.4. single-width scaling shifts
                "vssrl<.vv>",
                "vssrl<.vx>",
                "vssrl<.vi_uimm>",
                "vssra<.vv>",
                "vssra<.vx>",
                "vssra<.vi_uimm>",
                # 12.5. narrowing fixed-point clip
                "vnclipu<.wv>",
                "vnclipu<.wx>",
                "vnclipu<.wi>",
                "vnclip<.wv>",
                "vnclip<.wx>",
                "vnclip<.wi>",
            ],
            # ++++ 13. FLOATING POINT
            "<instr_v_floating_point>": [
                # 13.1. exception flags -> no instructions
                # 13.2. single-width fp add/sub
                "vfadd<.vv>",
                "vfadd<.vf>",
                "vfsub<.vv>",
                "vfsub<.vf>",
                "vfrsub<.vf>",
                # 13.3. widening fp add/sub
                "vfwadd<.vv>",
                "vfwadd<.vf>",
                "vfwsub<.vv>",
                "vfwsub<.vf>",
                "vfwadd<.wv>",
                "vfwadd<.wf>",
                "vfwsub<.wv>",
                "vfwsub<.wf>",
                # 13.4. single-width fp mult/div
                "vfmul<.vv>",
                "vfmul<.vf>",
                "vfdiv<.vv>",
                "vfdiv<.vf>",
                "vfrdiv<.vf>",
                # 13.5. widening fp mult
                "vfwmul<.vv>",
                "vfwmul<.vf>",
                # 13.6. single-width fp fused mul-add
                "vfmacc<.vv>",
                "vfmacc<.vf2>",
                "vfnmacc<.vv>",
                "vfnmacc<.vf2>",
                "vfmsac<.vv>",
                "vfmsac<.vf2>",
                "vfnmsac<.vv>",
                "vfnmsac<.vf2>",
                "vfmadd<.vv>",
                "vfmadd<.vf2>",
                "vfnmadd<.vv>",
                "vfnmadd<.vf2>",
                "vfmsub<.vv>",
                "vfmsub<.vf2>",
                "vfnmsub<.vv>",
                "vfnmsub<.vf2>",
                # 13.7. widening fp fused mult-add
                "vfwmacc<.vv>",
                "vfwmacc<.vf2>",
                "vfwnmacc<.vv>",
                "vfwnmacc<.vf2>",
                "vfwmsac<.vv>",
                "vfwmsac<.vf2>",
                "vfwnmsac<.vv>",
                "vfwnmsac<.vf2>",
                # 13.8. fp square-root
                "vfsqrt<.v>",
                # 13.9. fp reciprocal square-root estimate
                "vfrsqrt7<.v>",
                # 13.10. fp reciprocal estimate
                "vfrec7<.v>",
                # 13.11. fp min/max
                "vfmin<.vv>",
                "vfmin<.vf>",
                "vfmax<.vv>",
                "vfmax<.vf>",
                # 13.12. fp sign-injection
                "vfsgnj<.vv>",
                "vfsgnj<.vf>",
                "vfsgnjn<.vv>",
                "vfsgnjn<.vf>",
                "vfsgnjx<.vv>",
                "vfsgnjx<.vf>",
                # 13.13. fp compare
                "vmfeq<.vv>",
                "vmfeq<.vf>",
                "vmfne<.vv>",
                "vmfne<.vf>",
                "vmflt<.vv>",
                "vmflt<.vf>",
                "vmfle<.vv>",
                "vmfle<.vf>",
                "vmfgt<.vf>",
                "vmfge<.vf>",
                # 13.14. fp classify
                "vfclass<.v>",
                # 13.15. fp merge
                "vfmerge<.vfm>",
                # 13.16. fp move
                "vfmv.v.f <vd>, <fs1>",
                # 13.17. fp/int convert
                "vfcvt.xu.f<.v>",
                "vfcvt.x.f<.v>",
                "vfcvt.rtz.xu.f<.v>",
                "vfcvt.rtz.x.f<.v>",
                "vfcvt.f.xu<.v>",
                "vfcvt.f.x<.v>",
                # 13.18. widening fp/int convert
                "vfwcvt.xu.f<.v>",
                "vfwcvt.x.f<.v>",
                "vfwcvt.rtz.xu.f<.v>",
                "vfwcvt.rtz.x.f<.v>",
                "vfwcvt.f.xu<.v>",
                "vfwcvt.f.x<.v>",
                "vfwcvt.f.f<.v>",
                # 13.19. narrowing fp/int convert
                "vfncvt.xu.f<.w>",
                "vfncvt.x.f<.w>",
                "vfncvt.rtz.xu.f<.w>",
                "vfncvt.rtz.x.f<.w>",
                "vfncvt.f.xu<.w>",
                "vfncvt.f.x<.w>",
                "vfncvt.f.f<.w>",
                "vfncvt.rod.f.f<.w>",
            ],
            # ++++ 14. VECTOR REDUCTION
            "<instr_v_vector_reduction>": [
                # 14.1. single-width int reduction
                "vredsum<.vs>",
                "vredmaxu<.vs>",
                "vredmax<.vs>",
                "vredminu<.vs>",
                "vredmin<.vs>",
                "vredand<.vs>",
                "vredor<.vs>",
                "vredxor<.vs>",
                # 14.2. widening int reduction
                "vwredsumu<.vs>",
                "vwredsum<.vs>",
                # 14.3. single-width fp reduction
                "vfredosum<.vs>",
                "vfredusum<.vs>",
                "vfredmax<.vs>",
                "vfredmin<.vs>",
                # 14.4. widening fp reduction
                "vfwredosum<.vs>",
                "vfwredusum<.vs>",
            ],
            # ++++ 15. VECTOR MASK
            "<instr_v_vector_mask>": [
                # 15.1. mask-register logical
                "vmand<.mm>",
                "vmandn<.mm>",
                "vmnand<.mm>",
                "vmxor<.mm>",
                "vmor<.mm>",
                "vmnor<.mm>",
                "vmorn<.mm>",
                "vmxnor<.mm>",
                # 15.2. count population in mask
                "vcpop<.m>",
                # 15.3. find-first-set mask bit
                "vfirst<.m>",
                # 15.4. set-before-first mask bit
                "vmsbf<.m2>",
                # 15.5. set-including-first mask bit
                "vmsif<.m2>",
                # 15.6. set-only-first mask bit
                "vmsof<.m2>",
                # 15.7. examples -> no instructions
                # 15.8. iota
                "viota<.m2>",
                # 15.9. element index
                "vid<.v2>",
            ],
            # ++++ 16. VECTOR PERMUTATION
            "<instr_v_vector_permutation>": [
                # 16.1. int scalar move
                "vmv.x.s <rd>, <vs2>",
                "vmv.s.x <vd>, <rs1>",
                # 16.2. fp scalar move
                "vfmv.f.s <fd>, <vs2>",
                "vfmv.s.f <vd>, <fs1>",
                # 16.3. slide
                # 16.3.1. slideup
                "vslideup<.vx>",
                "vslideup<.vi_uimm>",
                # 16.3.2. slidedown
                "vslidedown<.vx>",
                "vslidedown<.vi_uimm>",
                # 16.3.3. slide1up
                "vslide1up<.vx>",
                "vfslide1up<.vf>",
                # 16.3.4. slide1down
                "vslide1down<.vx>",
                "vfslide1down<.vf>",
                # 16.4. gathering
                "vrgather<.vv>",
                "vrgatherei16<.vv>",
                "vrgather<.vx>",
                "vrgather<.vi_uimm>",
                # 16.5. compress
                "vcompress<.vm>",
                # 16.6. whole vector register move
                "vmv<vmv_nr>r<.v_nom>",
            ],
            # TODO: CHECK USAGE OF IMM vs UIMM
            "<.vv>": [".vv <vd>, <vs2>, <vs1><vm>"],
            "<.vx>": [".vx <vd>, <vs2>, <rs1><vm>"],
            "<.vi>": [".vi <vd>, <vs2>, <imm5><vm>"],
            # widening
            "<.wv>": [".wv <vd>, <vs2>, <vs1><vm>"],
            "<.wx>": [".wx <vd>, <vs2>, <rs1><vm>"],
            "<.wi>": [".wi <vd>, <vs2>, <uimm5><vm>"],
            # integer extension
            "<.vfX>": ["<.vfY> <vd>, <vs2><vm>"],
            "<.vfY>": [".vf2", ".vf4", ".vf8"],
            # sum with carry / diff with borrow
            "<.vvm>": [".vvm <vd>, <vs2>, <vs1>, v0"],
            "<.vxm>": [".vxm <vd>, <vs2>, <rs1>, v0"],
            "<.vim>": [".vim <vd>, <vs2>, <imm5>, v0"],
            # (alternatives without mask/<vm>)
            "<.vv_novm>": [".vv <vd>, <vs2>, <vs1>"],
            "<.vx_novm>": [".vx <vd>, <vs2>, <rs1>"],
            "<.vi_novm>": [".vi <vd>, <vs2>, <imm5>"],
            # bit shift
            "<.vi_uimm>": [".vi <vd>, <vs2>, <uimm5><vm>"],
            # mac
            "<.vv_mac>": [".vv <vd>, <vs1>, <vs2><vm>"],
            "<.vx_mac>": [".vx <vd>, <rs1>, <vs2><vm>"],
            # float
            "<.vf>": [".vf <vd>, <vs2>, <fs1><vm>"],
            "<.wf>": [".wf <vd>, <vs2>, <fs1><vm>"],
            "<.vf2>": [".vf <vd>, <fs1>, <vs2><vm>"],
            "<.v>": [".v <vd>, <vs2><vm>"],
            "<.w>": [".w <vd>, <vs2><vm>"],
            "<.vfm>": [".vfm <vd>, <vs2>, <fs1>, v0"],
            # reduction
            "<.vs>": [".vs <vd>, <vs2>, <vs1><vm>"],
            # mask
            "<.mm>": [".mm <vd>, <vs2>, <vs1>"],
            "<.m>": [".m <rd>, <vs2><vm>"],
            "<.m2>": [".m <vd>, <vs2><vm>"],
            "<.v2>": [".v <vd><vm>"],
            # perm
            "<.vm>": [".vm <vd>, <vs2>, <vs1>"],
            "<.v_nom>": [".v <vd>, <vs2>"],
            # masking
            "<vm>": ["", ", v0.t"],
            # integer registers
            "<rd>": ["<reg>"],
            "<rs1>": ["<reg>"],
            "<rs2>": ["<reg>"],
            "<reg>": self.rrig.get_reg,
            # vector registers
            "<vd>": ["<vreg>"],
            "<vs1>": ["<vreg>"],
            "<vs2>": ["<vreg>"],
            "<vreg>": self.vrrig.get_vreg,
            # floating point registers
            "<fd>": ["<freg>"],
            "<fs1>": ["<freg>"],
            "<freg>": self.frrig.get_freg,
            # imm values
            "<uimm5>": self.vrrig.get_uimm5,
            "<imm5>": self.vrrig.get_imm5,
        }


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
