#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .CodeBlock import CodeFragment
from .ISG_Base import RandRegImmGenerator, RegAlloc, ProgramGenerator, grammarISG
from .ISG_RVI import CSRModGenerator, RVRegAlloc, RVRandRegImmGenerator
from .ISG_RVF import RVFRandRegImmGenerator

import random
import numpy as np

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

        rvisacfg = config["rvisacfg"]
        self.xlen = rvisacfg.get_xlen()
        self.xlen_mask = (1 << self.xlen) - 1
        self.vector_vlen = rvisacfg.get_vlen()
        self.vector_vlen_bytes = self.vector_vlen // 8
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

    def _gen_code_unit_stride(self, store, name, enc_eew, nfields, masked):

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

        # TODO: clobber annotation: also track memory (mem, dmem, xmem)?
        dep_ann = {rs1}
        clob_ann = {rs_scratch, rs1}
        if store:
            dep_ann.add(vld)
        else:
            clob_ann.add(vld)
        if masked:
            dep_ann.add("vmask")
        return (code, {"clob": clob_ann, "dep": dep_ann})

    # Generate instructions from 7.5. Vector Strided Instructions and 7.8.2. Vector Strided Segment Loads and Stores
    # Difference to other generators: Instead of using run-time values from registers and modifying then according
    # to bounds, we explicitly generate random values and set registers accordingly.
    def _gen_code_reg_stride(self, store, name, enc_eew, nfields, masked):

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

        # TODO: clobber annotation: also track memory (mem, dmem, xmem)?
        dep_ann = set()
        clob_ann = {rs1, rs2}
        if store:
            dep_ann.add(vld)
        else:
            clob_ann.add(vld)
        if masked:
            dep_ann.add("vmask")
        return (code, {"clob": clob_ann, "dep": dep_ann})

    # NOTE: The number of bits encoded in the instruction determines the eww of the index
    # vector, *NOT* the size of the load/store (sew of data vector). Therefore: Alignment depends
    # on the current eew set in vtype
    # TODO: We don't know lmul at generation time, but we have to make sure that vand of mask succeeds
    # to get valid adresse ranges for the subsequent load/store. The current solution is to only use
    # v8 and v16 registers, but this limits the variability of the instructions (always the same vs2
    # registers
    def _gen_code_indexed(self, store, name, enc_eew, nfields, masked):

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

        # TODO: clobber annotation: also track memory (mem, dmem, xmem)?
        # NOTE: although vtype should be saved and restored, we have to mark it as dependency
        # and clobbered in case anything goes wrong
        dep_ann = {"vl", "vtype", rs1, vs_scratch}
        clob_ann = {"vstart", "vl", "vtype", rs_vtype, rs_vl, rs_scratch, rs1}
        if store:
            dep_ann.add(vld)
        else:
            clob_ann.add(vld)
        if masked:
            dep_ann.add("vmask")
        return (code, {"clob": clob_ann, "dep": dep_ann})

    def _gen(self, store):
        if store:
            instr_list = self.STORE
        else:
            instr_list = self.LOAD
        instr = random.choice(instr_list)
        masked = False
        # print(instr)
        if instr[4]:
            masked = bool(random.getrandbits(1))
        return instr[0](store, instr[1], instr[2], instr[3], masked)

    def gen_load(self):
        return self._gen(False)

    def gen_store(self):
        return self._gen(True)


class RVVProgramGenerator(ProgramGenerator):
    def __init__(self, config=None):

        self.has_float = config["rvisacfg"].is_float_under_test()

        self.quirk_ara_csrs = config.get("quirk_ara_csrs", False)

        self.csrmg = CSRModGenerator()
        self.rrig = RVRandRegImmGenerator()
        self.vrrig = RVVRandRegImmGenerator()
        self.frrig = RVFRandRegImmGenerator()

        # use full memory (memstart, memlen) for loads
        config_partmem = config.copy()
        config_partmem["memstart"] = (
            config_partmem["memstart"] + config_partmem["quirk_sail_load_offset"]
        )
        config_partmem["memlen"] = (
            config_partmem["memlen"] - config_partmem["quirk_sail_load_offset"]
        )
        self.vblsg_load = RVVBoundedLoadStoreGenerator(config=config_partmem)

        # use only dmemory (dmemstart, dmemlen) for stores (protect program)
        config_partmem = config.copy()
        config_partmem["memstart"] = config_partmem["dmemstart"]
        config_partmem["memlen"] = config_partmem["dmemlen"]
        self.vblsg_store = RVVBoundedLoadStoreGenerator(config=config_partmem)

        self.__def_grammar()

    def gen_fragment(self, **kwargs):
        code, ann = grammarISG(self.grammar, **kwargs)
        return CodeFragment(code, ann)

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
        if self.quirk_ara_csrs:
            # vxrm is not writable on ARA -> prevent other values than 0
            vxrm_range = [0]
        else:
            vxrm_range = list(range(2**2))
        return self.csrmg.gen_csr_mod("vxrm", 0x3, vxrm_range)

    def __def_grammar(self):
        self.grammar = {
            "<start>": ("    <line>", {"dep": {"mstatus.fs/vs"}}),
            "<line>": [
                "<instr_v_config>",
                ("<instr_v_load_store>", {"dep": {"vstart", "vtype", "vl"}}),
                ("<instr_v_compute>", {"dep": {"vstart", "vtype", "vl"}}),
                ("<instr_v_compute>", {"dep": {"vstart", "vtype", "vl"}}),
                ("<instr_v_compute>", {"dep": {"vstart", "vtype", "vl"}}),
                ("<instr_v_compute>", {"dep": {"vstart", "vtype", "vl"}}),
            ],
            "<instr_v_config>": [
                ("<instr_v_config_vset>", {"clob": {"vstart", "vtype", "vl"}}),
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
                (
                    "<instr_v_fixed_point>",
                    {"dep": {"vxrm", "vxsat", "vcsr"}, "clob": {"vxsat", "vcsr"}},
                ),
                ("<instr_v_floating_point>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
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
                ("vfredosum<.vs>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
                ("vfredusum<.vs>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
                ("vfredmax<.vs>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
                ("vfredmin<.vs>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
                # 14.4. widening fp reduction
                ("vfwredosum<.vs>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
                ("vfwredusum<.vs>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
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
                ("vfmv.f.s <fd>, <vs2>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
                ("vfmv.s.f <vd>, <fs1>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
                # 16.3. slide
                # 16.3.1. slideup
                "vslideup<.vx>",
                "vslideup<.vi_uimm>",
                # 16.3.2. slidedown
                "vslidedown<.vx>",
                "vslidedown<.vi_uimm>",
                # 16.3.3. slide1up
                "vslide1up<.vx>",
                ("vfslide1up<.vf>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
                # 16.3.4. slide1down
                "vslide1down<.vx>",
                ("vfslide1down<.vf>", {"dep": {"fcsr"}, "clob": {"fcsr"}}),
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
            "<.vvm>": ".vvm <vd>, <vs2>, <vs1>, <vm2>",
            "<.vxm>": ".vxm <vd>, <vs2>, <rs1>, <vm2>",
            "<.vim>": ".vim <vd>, <vs2>, <imm5>, <vm2>",
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
            "<.vfm>": ".vfm <vd>, <vs2>, <fs1>, <vm2>",
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
            "<vm>": [
                "",
                (", v0.t", {"dep": "vmask"}),
            ],
            "<vm2>": ("v0", {"dep": "vmask"}),
            # integer registers
            "<rd>": ("<reg>", {"clob": "_"}),
            "<rs1>": ("<reg>", {"dep": "_"}),
            "<rs2>": ("<reg>", {"dep": "_"}),
            "<reg>": self.rrig.get_reg,
            # vector registers
            "<vd>": ("<vreg>", {"clob": "_", "dep": "_"}),
            "<vs1>": ("<vreg>", {"dep": "_"}),
            "<vs2>": ("<vreg>", {"dep": "_"}),
            "<vreg>": self.vrrig.get_vreg,
            # floating point registers
            "<fd>": ("<freg>", {"clob": "_"}),
            "<fs1>": ("<freg>", {"dep": "_"}),
            "<freg>": self.frrig.get_freg,
            # imm values
            "<uimm5>": self.vrrig.get_uimm5,
            "<imm5>": self.vrrig.get_imm5,
        }
