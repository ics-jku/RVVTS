#!/usr/bin/env python
# coding: utf-8
#
# (C) 2026 Katharina Ruep <katharina.ruep@jku.at>, Institute for Complex Systems, JKU Linz
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .CodeBlock import CodeFragment
from .ISG_Base import RandRegImmGenerator, RegAlloc, ProgramGenerator, grammarISG
from .ISG_RVI import (
    CSRModGenerator,
    RVRegAlloc,
    RVRandRegImmGenerator,
    RVIBoundedLoadStoreGenerator,
)

import random

# ## RISC-V FLOAT (F, D, Q, Zfh)


class RVFRegAlloc(RegAlloc):
    def __init__(self):
        super().__init__(number=32, prefix="f")


class RVFRandRegImmGenerator(RandRegImmGenerator):
    def __init__(self):
        pass

    def get_freg(self):
        return "f" + self.get_regnr(0, 31)


class RVFBoundedLoadStoreGenerator(RVIBoundedLoadStoreGenerator):
    def __init__(self, config=None):

        rvisacfg = config["rvisacfg"]
        self.xlen = rvisacfg.get_xlen()
        self.xlen_mask = (1 << self.xlen) - 1
        self.memstart = config["memstart"]
        self.memlen = config["memlen"]
        self.memend = self.memstart + self.memlen
        self.memlen_mask = (1 << self.memlen.bit_length() - 1) - 1

        self.xregs = RVRegAlloc()
        self.fregs = RVFRegAlloc()
        self.vrrig = RVFRandRegImmGenerator()

        self.has_fsingle = rvisacfg.is_float_under_test()
        self.has_fdouble = rvisacfg.is_under_test_any(["d", "q"])
        self.has_fquad = rvisacfg.is_under_test("q")
        self.has_fhalf = rvisacfg.is_under_test("zfh")

        # instructions and alignment
        self.LOAD = []
        self.STORE = []
        if self.has_fsingle:
            self.LOAD.append(("flw", 4))
            self.STORE.append(("fsw", 4))
        if self.has_fdouble:
            self.LOAD.append(("fld", 8))
            self.STORE.append(("fsd", 8))
        if self.has_fquad:
            self.LOAD.append(("flq", 16))
            self.STORE.append(("fsq", 16))
        if self.has_fhalf:
            self.LOAD.append(("flh", 2))
            self.STORE.append(("fsh", 2))

    def _gen_code(self, store=False, instr_name="", instr_alignment=1):
        # generates the marked part in given bounds
        # "<LOAD/STORE_instr> <rs2>, <imm12>(<rs1>)",
        #                     ---------------------

        # src/dst may by zero
        rs2 = self.fregs.alloc_random(self.fregs.ALL)
        # address
        rs1 = self.xregs.alloc_random(self.xregs.ALL_NOT_ZERO)
        # offset
        imm12 = self._get_int_imm(12)
        # scratch register for calculation
        rs_scratch = self.xregs.alloc_random(self.xregs.ALL_NOT_ZERO)

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

        self.fregs.free_all()
        self.xregs.free_all()

        # TODO: clobber annotation: also track memory (mem, dmem, xmem)?
        dep_ann = {rs1}
        clob_ann = {rs_scratch, rs1}
        if store:
            dep_ann.add(rs2)
        else:
            clob_ann.add(rs2)
        return (code, {"clob": clob_ann, "dep": dep_ann})


class RVFProgramGenerator(ProgramGenerator):
    def __init__(self, config=None):

        # F   | Single |  32
        # D   | Double |  64
        # Q   | Quad   | 128
        # Zfh | Half   |  16
        rvisacfg = config["rvisacfg"]
        self.has_fsingle = rvisacfg.is_float_under_test()
        self.has_fdouble = rvisacfg.is_under_test_any(["d", "q"])
        self.has_fquad = rvisacfg.is_under_test("q")
        self.has_fhalf = rvisacfg.is_under_test("zfh")

        # TODO
        self.force_frm = config["RVFProgramGenerator_force_float_frm"]

        rvisacfg = config["rvisacfg"]
        self.xlen = rvisacfg.get_xlen()

        self.csrmg = CSRModGenerator()
        self.rrig = RVRandRegImmGenerator()
        self.frrig = RVFRandRegImmGenerator()

        # use full memory (memstart, memlen) for loads
        config_partmem = config.copy()
        config_partmem["memstart"] = (
            config_partmem["memstart"] + config_partmem["quirk_sail_load_offset"]
        )
        config_partmem["memlen"] = (
            config_partmem["memlen"] - config_partmem["quirk_sail_load_offset"]
        )
        self.fblsg_load = RVFBoundedLoadStoreGenerator(config=config)

        # use only dmemory (dmemstart, dmemlen) for stores (protect program)
        config_partmem = config.copy()
        config_partmem["memstart"] = config_partmem["dmemstart"]
        config_partmem["memlen"] = config_partmem["dmemlen"]
        self.fblsg_store = RVFBoundedLoadStoreGenerator(config=config_partmem)

        self.__def_grammar()

    def gen_fragment(self, **kwargs):
        code, ann = grammarISG(self.grammar, **kwargs)
        return CodeFragment(code, ann)

    def gen_set_mstatus_en_float(self):
        return self.csrmg.gen_csr_mod("mstatus", 0x6000, [0x0000, 0x6000])

    def gen_set_frm(self):

        if self.force_frm.isdigit():
            return self.csrmg.gen_csr_mod("fcsr", (0x7 << 5), [self.force_frm << 5])
        elif self.force_frm == "RNE":
            return self.csrmg.gen_csr_mod("fcsr", (0x7 << 5), [0])
        elif self.force_frm == "RTZ":
            return self.csrmg.gen_csr_mod("fcsr", (0x7 << 5), [1 << 5])
        elif self.force_frm == "RDN":
            return self.csrmg.gen_csr_mod("fcsr", (0x7 << 5), [2 << 5])
        elif self.force_frm == "RUP":
            return self.csrmg.gen_csr_mod("fcsr", (0x7 << 5), [3 << 5])
        elif self.force_frm == "RMM":
            return self.csrmg.gen_csr_mod("fcsr", (0x7 << 5), [4 << 5])
        else:
            return self.csrmg.gen_csr_mod(
                "fcsr", (0x7 << 5), [i << 5 for i in range(7)]
            )

    def gen_set_fflags(self):
        return self.csrmg.gen_csr_mod("fcsr", 0x1F, range(0x1F))

    def gen_set_fcsr(self):
        return self.csrmg.gen_csr_mod("fcsr", 0xFF, range(0xFF))

    def get_flens(self):
        flens = []
        if self.has_fsingle:
            flens.append(".s")
        if self.has_fdouble:
            flens.append(".d")
        if self.has_fquad:
            flens.append(".q")
        if self.has_fhalf:
            flens.append(".h")

        return random.choice(flens)

    def get_mv_instr(self):
        instr = []
        # addon for F
        if self.has_fsingle:
            instr.append("fmv.x.w <xrd>, <frs1>")
            instr.append("fmv.w.x <frd>, <xrs1>")
        # addon for D and 64 bit
        if self.has_fdouble and self.xlen == 64:
            instr.append("fmv.x.d <xrd>, <frs1>")
            instr.append("fmv.d.x <frd>, <xrs1>")
        # addon for H
        if self.has_fhalf:
            instr.append("fmv.x.h <xrd>, <frs1>")
            instr.append("fmv.h.x <frd>, <xrs1>")
        return random.choice(instr)

    def get_cvt_instr(self):
        # addon for F
        instr = []
        if self.has_fsingle:
            instr.append("fcvt.w.s <xrd>, <frs1><frm>")
            instr.append("fcvt.wu.s <xrd>, <frs1><frm>")
            instr.append("fcvt.s.w <frd>, <xrs1><frm>")
            instr.append("fcvt.s.wu <frd>, <xrs1><frm>")

            if self.xlen == 64:
                instr.append("fcvt.l.s <xrd>, <frs1><frm>")
                instr.append("fcvt.lu.s <xrd>, <frs1><frm>")
                instr.append("fcvt.s.l <frd>, <xrs1><frm>")
                instr.append("fcvt.s.lu <frd>, <xrs1><frm>")

        # addon for D
        if self.has_fdouble:
            instr.append("fcvt.w.d <xrd>, <frs1><frm>")
            instr.append("fcvt.wu.d <xrd>, <frs1><frm>")
            instr.append("fcvt.d.w <frd>, <xrs1>")
            instr.append("fcvt.d.wu <frd>, <xrs1>")

            if self.xlen == 64:
                instr.append("fcvt.l.d <xrd>, <frs1><frm>")
                instr.append("fcvt.lu.d <xrd>, <frs1><frm>")
                instr.append("fcvt.d.l <frd>, <xrs1><frm>")
                instr.append("fcvt.d.lu <frd>, <xrs1><frm>")

            instr.append("fcvt.s.d <frd>, <frs1><frm>")
            instr.append("fcvt.d.s <frd>, <frs1>")

        # addon for Q
        if self.has_fquad:
            instr.append("fcvt.w.q <xrd>, <frs1><frm>")
            instr.append("fcvt.wu.q <xrd>, <frs1><frm>")
            instr.append("fcvt.q.w <frd>, <xrs1><frm>")
            instr.append("fcvt.q.wu <frd>, <xrs1><frm>")

            if self.xlen == 64:
                instr.append("fcvt.l.q <xrd>, <frs1><frm>")
                instr.append("fcvt.lu.q <xrd>, <frs1><frm>")
                instr.append("fcvt.q.l <frd>, <xrs1>")
                instr.append("fcvt.q.lu <frd>, <xrs1>")

            instr.append("fcvt.s.q <frd>, <frs1><frm>")
            instr.append("fcvt.q.s <frd>, <frs1>")
            instr.append("fcvt.d.q <frd>, <frs1><frm>")
            instr.append("fcvt.q.d <frd>, <frs1>")

        # addon for H
        if self.has_fhalf:
            instr.append("fcvt.w.h <xrd>, <frs1><frm>")
            instr.append("fcvt.wu.h <xrd>, <frs1><frm>")
            instr.append("fcvt.h.w <frd>, <xrs1><frm>")
            instr.append("fcvt.h.wu <frd>, <xrs1><frm>")

            if self.xlen == 64:
                instr.append("fcvt.l.h <xrd>, <frs1><frm>")
                instr.append("fcvt.lu.h <xrd>, <frs1><frm>")
                instr.append("fcvt.h.l <frd>, <xrs1><frm>")
                instr.append("fcvt.h.lu <frd>, <xrs1><frm>")

            instr.append("fcvt.s.h <frd>, <frs1>")
            instr.append("fcvt.h.s <frd>, <frs1><frm>")
            if self.has_fdouble:
                instr.append("fcvt.d.h <frd>, <frs1>")
                instr.append("fcvt.h.d <frd>, <frs1><frm>")
            if self.has_fquad:
                instr.append("fcvt.q.h <frd>, <frs1>")
                instr.append("fcvt.h.q <frd>, <frs1><frm>")

        return random.choice(instr)

    def get_frm(self):
        return random.choice(
            [
                "",  # none defined
                ", rne",  # Round to Nearest, ties to Even
                ", rtz",  # Round towards Zero
                ", rdn",  # Round Down (towards -INF)
                ", rup",  # Round Up (towards +INF)
                ", rmm",  # Round to Nearest, ties to Max Magnitude
                ", dyn",  # Round to Nearest, ties to Max Magnitude
            ]
        )

    def __def_grammar(self):
        self.grammar = {
            "<start>": (
                "    <line>",
                {"dep": {"mstatus.fs/vs.fs", "fcsr.rm"}},
            ),  # add rounding mode
            "<line>": [
                self.gen_set_mstatus_en_float,
                self.gen_set_fcsr,
                "<instr_f_load_store>",
                "<instr_f_compute>",
                "<instr_f_compute>",
                "<instr_f_compute>",
                "<instr_f_compute>",
            ],
            "<instr_f_config>": [
                self.gen_set_frm,
                self.gen_set_fflags,
                self.gen_set_fcsr,
            ],
            "<instr_f_load_store>": [
                "<instr_f_load>",
                "<instr_f_store>",
            ],
            "<instr_f_load>": self.fblsg_load.gen_load,
            "<instr_f_store>": self.fblsg_store.gen_store,
            "<instr_f_compute>": [
                "<instr_f_calc>",
                "<instr_f_comp>",
                "<instr_f_mod>",
                "<instr_f_check>",
                "<instr_f_cvt>",
                "<instr_f_mv>",
            ],
            "<instr_f_calc>": [
                "<instr_f_calc_nrm><frm>",
            ],
            "<instr_f_calc_nrm>": [
                "<instr_f_calc1><flen> <frd>, <frs1>",
                "<instr_f_calc2><flen> <frd>, <frs1>, <frs2>",
                "<instr_f_calc3><flen> <frd>, <frs1>, <frs2>, <frs3>",
            ],
            "<instr_f_calc1>": [
                "fsqrt",
            ],
            "<instr_f_calc2>": [
                "fadd",
                "fsub",
                "fmul",
                "fdiv",
            ],
            "<instr_f_calc3>": [
                "fmadd",
                "fmsub",
                "fnmadd",
                "fnmsub",
            ],
            "<instr_f_mod>": [
                "<instr_f_mod2><flen> <frd>, <frs1>, <frs2>",
            ],
            "<instr_f_mod2>": [
                "fsgnj",
                "fsgnjn",
                "fsgnjx",
                "fmin",
                "fmax",
            ],
            "<instr_f_check>": [
                "fclass<flen> <xrd>, <frs1>",
            ],
            "<instr_f_comp>": [
                "<instr_f_comp2><flen> <xrd>, <frs1>, <frs2>",
            ],
            "<instr_f_comp2>": [
                "feq",
                "flt",
                "fle",
            ],
            "<instr_f_mv>": self.get_mv_instr,
            "<instr_f_cvt>": self.get_cvt_instr,
            "<flen>": self.get_flens,
            "<xrd>": ("<x_reg>", {"clob": "_"}),
            "<xrs1>": ("<x_reg>", {"dep": "_"}),
            "<frd>": ("<f_reg>", {"clob": "_"}),
            "<frs1>": ("<f_reg>", {"dep": "_"}),
            "<frs2>": ("<f_reg>", {"dep": "_"}),
            "<frs3>": ("<f_reg>", {"dep": "_"}),
            "<x_reg>": self.rrig.get_reg,
            "<f_reg>": self.frrig.get_freg,
            "<frm>": self.get_frm,
        }
