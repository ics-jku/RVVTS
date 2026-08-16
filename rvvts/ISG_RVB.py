#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#


# TODO: I, V, (F,D) -- add random init of registers


from .CodeBlock import CodeFragment
from .ISG_Base import ProgramGenerator, grammarISG
from .ISG_RVI import RVRandRegImmGenerator

import mergedeep

# ## RISC-V B Bit manipulation extensions (Zba, Zbb, Zbs, (Zbc))


class RVBProgramGenerator(ProgramGenerator):
    def __init__(self, config=None):

        self.rrig = RVRandRegImmGenerator()

        self.__def_grammars()

        # enable extensions
        rvisacfg = config["rvisacfg"]

        extensions = ["base"]
        if rvisacfg.is_under_test("b"):
            extensions += ["zba", "zbb", "zbs"]
        if rvisacfg.is_under_test("zbc"):
            extensions += ["zbc"]

        self.__def_grammar(extensions=extensions, xlen=rvisacfg.get_xlen())

    def gen_fragment(self, **kwargs):
        code, ann = grammarISG(self.grammar, **kwargs)
        return CodeFragment(code, ann)

    def __def_grammars(self):
        # This grammar uses dummy nodes ("# dummy") to prevent empty lists which are currently not supported by our ISG
        # TODO: fix ISG to properly handle empty nodes (or do a cleanup pass before using the grammar)

        # first two levels are extensions and xlen
        self.grammars = {
            # base grammar for all B extensions
            "base": {
                "all": {
                    "<start>": ["<line>"],
                    "<line>": ["    <instr>"],
                    "<instr>": [
                        "<R_instr> <rd>, <rs1>, <rs2>",
                    ],
                    "<R_instr>": ["# dummy"],
                    "<rd>": ("<reg>", {"clob": "_"}),
                    "<rs1>": ("<reg>", {"dep": "_"}),
                    "<rs2>": ("<reg>", {"dep": "_"}),
                    "<reg>": self.rrig.get_reg,
                },
                32: {
                    "<instr>": [
                        "<SHAMT4_instr> <rd>, <rs1>, <shamt4>",
                    ],
                    "<SHAMT4_instr>": ["# dummy"],
                    "<shamt4>": self.rrig.get_shamt4,
                },
                64: {
                    "<instr>": [
                        "<SHAMT5_instr> <rd>, <rs1>, <shamt5>",
                    ],
                    "<SHAMT5_instr>": ["# dummy"],
                    "<shamt5>": self.rrig.get_shamt5,
                },
            },
            # 30.2. Zba: Extension for Address generation, Version 1.0.0
            "zba": {
                "all": {
                    "<R_instr>": [
                        "sh1add",
                        "sh2add",
                        "sh3add",
                    ],
                },
                32: {},
                64: {
                    "<R_instr>": [
                        "add.uw",
                        "sh1add.uw",
                        "sh2add.uw",
                        "sh3add.uw",
                    ],
                    "<SHAMT5_instr>": [
                        "slli.uw",
                    ],
                },
            },
            # 30.3. Zbb: Extension for Basic bit-manipulation, Version 1.0.0
            "zbb": {
                "all": {
                    "<instr>": [
                        "<R2_instr> <rd>, <rs1>",
                    ],
                    "<R_instr>": [
                        # 30.3.1. Logical with negate
                        "andn",
                        "orn",
                        "xnor",
                        # 30.3.4. Integer minimum/maximum
                        "max",
                        "maxu",
                        "min",
                        "minu",
                        # 30.3.6. Bitwise rotation
                        "rol",
                        "ror",
                    ],
                    "<R2_instr>": [
                        # 30.3.2. Count leading/trailing zero bits
                        "clz",
                        "ctz",
                        # 30.3.3. Count population
                        "cpop",
                        # 30.3.5. Sign extension and zero extension
                        "sext.b",
                        "sext.h",
                        "zext.h",
                        # 30.3.7. OR Combine
                        "orc.b",
                        # 30.3.8. Byte-reverse
                        "rev8",
                    ],
                },
                32: {
                    "<SHAMT4_instr>": [
                        "rori",  # RV32 rori -> 4 bit shamt
                    ],
                },
                64: {
                    "<R_instr>": [
                        # 30.3.6. Bitwise rotation
                        "rolw",
                        "rorw",
                    ],
                    "<SHAMT5_instr>": [
                        # 30.3.6. Bitwise rotation
                        "rori",  # RV64 rori -> 5 bit shamt
                        "roriw",
                    ],
                    "<R2_instr>": [
                        # 30.3.2. Count leading/trailing zero bits
                        "clzw",
                        "ctzw",
                        # 30.3.3. Count population
                        "cpopw",
                    ],
                },
            },
            # 30.4. Zbc: Extension for Carry-less multiplication, Version 1.0.0
            # (NOTE: not part of B - see constructor)
            "zbc": {
                "all": {
                    "<R_instr>": [
                        "clmul",
                        "clmulh",
                        "clmulr",
                    ],
                },
                32: {},
                64: {},
            },
            # 30.5. Zbs: Extension for Single-bit instructions, Version 1.0.0
            "zbs": {
                "all": {
                    "<R_instr>": [
                        "bclr",
                        "bext",
                        "binv",
                        "bset",
                    ],
                },
                32: {
                    "<SHAMT4_instr>": [
                        # RV32 -> 4 bit shamt
                        "bclri",
                        "bexti",
                        "binvi",
                        "bseti",
                    ],
                },
                64: {
                    "<SHAMT5_instr>": [
                        # RV64 -> 5 bit shamt
                        "bclri",
                        "bexti",
                        "binvi",
                        "bseti",
                    ],
                },
            },
        }

    def __def_grammar(self, extensions=[], xlen=-1):
        self.grammar = {}

        # merge grammars
        for ext in extensions:
            self.grammar = mergedeep.merge(
                self.grammar,
                self.grammars[ext]["all"],
                self.grammars[ext][xlen],
                strategy=mergedeep.Strategy.TYPESAFE_ADDITIVE,
            )
