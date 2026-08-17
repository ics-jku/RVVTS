#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .CodeBlock import CodeFragment, CodeFragmentList
from .MachineState import MachineState
from .ISG_Base import (
    RandLabelGenerator,
    RandRegImmGenerator,
    RegAlloc,
    ProgramGenerator,
    grammarISG,
)

import random

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

        return ("\n" + code + "\n", {"clob": {reg, csr}})


# TODO: generalize (-> ISG_Base)
class RVIBoundedLoadStoreGenerator:
    def __init__(self, config=None):

        self.xlen = config["rvisacfg"].get_xlen()
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

    def _gen_code(self, store=False, instr_name="", instr_alignment=1):
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

        # TODO: clobber annotation: also track memory (mem, dmem, xmem)?
        dep_ann = {rs1}
        clob_ann = {rs_scratch, rs1}
        if store:
            dep_ann.add(rs2)
        else:
            clob_ann.add(rs2)
        return (code, {"clob": clob_ann, "dep": dep_ann})

    def _gen(self, store):
        if store:
            instr_list = self.STORE
        else:
            instr_list = self.LOAD
        instr = random.choice(instr_list)
        return self._gen_code(store, instr_name=instr[0], instr_alignment=instr[1])

    def gen_load(self):
        return self._gen(False)

    def gen_store(self):
        return self._gen(True)

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


# x = RVIBoundedLoadStoreGenerator(xlen = 64, dmemstart = 0x2000, dmemlen = 256*1024*1024)
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

    def get_shamt4(self):
        return self.get_immu(4)

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
        config_partmem = config.copy()
        config_partmem["memstart"] = (
            config_partmem["memstart"] + config_partmem["quirk_sail_load_offset"]
        )
        config_partmem["memlen"] = (
            config_partmem["memlen"] - config_partmem["quirk_sail_load_offset"]
        )
        self.blsg_load = RVIBoundedLoadStoreGenerator(config=config_partmem)

        # use only dmemory (dmemstart, dmemlen) for stores (protect program)
        config_partmem = config.copy()
        config_partmem["memstart"] = config_partmem["dmemstart"]
        config_partmem["memlen"] = config_partmem["dmemlen"]
        self.blsg_store = RVIBoundedLoadStoreGenerator(config=config_partmem)

        self.__def_grammar()

    def gen_init_fragments(self, **kwargs):
        self.mstate.init(self.mstate.VALUE_MODE_RAND)
        ret = self.mstate.as_CodeFragmentList()
        ret.add(CodeFragment(self.rlg.gen_first()))
        return ret

    def gen_fragment(self, **kwargs):
        code, ann = grammarISG(self.grammar, **kwargs)
        return CodeFragment(code, ann)

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
            "<rd>": ("<reg>", {"clob": "_"}),
            "<rs1>": ("<reg>", {"dep": "_"}),
            "<rs2>": ("<reg>", {"dep": "_"}),
            "<reg>": self.rrig.get_reg,
            "<shamt5>": self.rrig.get_shamt5,
            "<imm12>": self.rrig.get_imm12,
            "<imm12u>": self.rrig.get_imm12,
            "<imm20>": self.rrig.get_imm20,
            "<imm20u>": self.rrig.get_imm20u,
        }
