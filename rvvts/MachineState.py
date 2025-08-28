#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-25 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .CodeBlock import CodeFragmentList, CodeFragment

import os
import random
import copy
import jsonpickle
import hashlib

RVREGS_IDX_DICT = {
    "zero": 0,
    "ra": 1,
    "sp": 2,
    "gp": 3,
    "tp": 4,
    "t0": 5,
    "t1": 6,
    "t2": 7,
    "fp": 8,
    "s1": 9,
    "a0": 10,
    "a1": 11,
    "a2": 12,
    "a3": 13,
    "a4": 14,
    "a5": 15,
    "a6": 16,
    "a7": 17,
    "s2": 18,
    "s3": 19,
    "s4": 20,
    "s5": 21,
    "s6": 22,
    "s7": 23,
    "s8": 24,
    "s9": 25,
    "s10": 26,
    "s11": 27,
    "t3": 28,
    "t4": 29,
    "t5": 30,
    "t6": 31,
}


class MachineState:

    @classmethod
    def load(cls, filename):
        with open(filename, "r") as file:
            json_data = file.read()
            return jsonpickle.decode(json_data)
        return None

    def __init__(self, config, state=None):
        self.FORMAT_MAX_NAME_WIDTH = 20
        self.FORMAT_MAX_VALUE_WIDTH = 16

        self.VALUE_MODE_ZERO = 0
        self.VALUE_MODE_RAND = 1
        self.config = config
        self.xlen = config["xlen"]
        self.rv_extensions = config["rv_extensions"]
        self.has_float = sum(e in self.rv_extensions for e in "fdq") > 0
        self.has_vector = "v" in self.rv_extensions

        self.quirk_ara_csrs = config.get("quirk_ara_csrs", False)

        # decoded state
        self.dstate = {}
        if not state:
            self.init(self.VALUE_MODE_ZERO)
        else:
            self.from_state(state)

    def __str__(self):
        return self.as_string()

    def __repr__(self):
        return self.__str__()

    def duplicate(self):
        return MachineState(copy.deepcopy(self.config), copy.deepcopy(self.state))

    def save(self, filename):
        json_data = jsonpickle.encode(self)
        with open(filename, "w") as file:
            file.write(json_data)

    def gen_value_from_selection(self, value_mode, last_value, mask, values):
        last_value = last_value & ~mask
        if value_mode == self.VALUE_MODE_ZERO:
            return last_value
        elif value_mode == self.VALUE_MODE_RAND:
            return last_value | random.choice(values)
        else:
            raise Exception("invalid value_mode " + str(value_mode))

    def gen_value(self, value_mode, min, max):
        if value_mode == self.VALUE_MODE_ZERO:
            return min
        elif value_mode == self.VALUE_MODE_RAND:
            return random.randint(min, max)
        else:
            raise Exception("invalid value_mode " + str(value_mode))

    def gen_byte_values(self, value_mode, len):
        if value_mode == self.VALUE_MODE_ZERO:
            return bytes(len)
        elif value_mode == self.VALUE_MODE_RAND:
            return random.randbytes(len)
        else:
            raise Exception("invalid value_mode " + str(value_mode))

    def dstate_add(self, parent, child, value):
        if parent not in self.dstate:
            self.dstate[parent] = {}
        self.dstate[parent][child] = value

    def dstate_entry_as_string(self, parent):
        if parent in self.dstate:
            # use decompressed values
            return str(self.dstate[parent])
        else:
            # fallback to raw value
            return str(self.state[1][parent])

    def dstate_decode_mstatus_fsvs(self):
        rname = "mstatus.fs/vs"
        rval = self.state[1].get(rname, None)
        if rval is None:
            return

        status = ["off", "initial", "clean", "dirty"]

        FS_SHIFT = 13
        FS_MASK = 3 << FS_SHIFT
        fs = (rval & FS_MASK) >> FS_SHIFT
        self.dstate_add(rname, "fs", status[fs])

        VS_SHIFT = 9
        VS_MASK = 3 << VS_SHIFT
        vs = (rval & VS_MASK) >> VS_SHIFT
        self.dstate_add(rname, "vs", status[vs])

    def dstate_decode_fcsr(self):
        rname = "fcsr"
        rval = self.state[1].get(rname, None)
        if rval is None:
            return

        # exception flags
        self.dstate_add(rname, "nx", True if rval & (1 << 0) else False)
        self.dstate_add(rname, "uf", True if rval & (1 << 1) else False)
        self.dstate_add(rname, "of", True if rval & (1 << 2) else False)
        self.dstate_add(rname, "dz", True if rval & (1 << 3) else False)
        self.dstate_add(rname, "nv", True if rval & (1 << 4) else False)

        # rounding mode
        RM = [
            "rne(0b000)",
            "rtz(0b001)",
            "rdn(0b010)",
            "rup(0b011)",
            "rmm(0b100)",
            "res0(0b101)",
            "res1(0b110)",
            "dyn(0b111)",
        ]
        RM_SHIFT = 5
        RM_MASK = 7 << RM_SHIFT
        rm = (rval & RM_MASK) >> RM_SHIFT
        self.dstate_add(rname, "rm", RM[rm])

        # reserved field
        res = rval >> 8
        self.dstate_add(rname, "res", res)

    def dstate_decode_vtype(self):
        rname = "vtype"
        rval = self.state[1].get(rname, None)
        if rval is None:
            return

        VILL_MASK = 1 << (self.xlen - 1)
        self.dstate_add(rname, "vill", True if rval & VILL_MASK else False)
        VMA_MASK = 1 << 7
        self.dstate_add(rname, "vma", True if rval & VMA_MASK else False)
        VTA_MASK = 1 << 6
        self.dstate_add(rname, "vta", True if rval & VTA_MASK else False)

        VSEW = [
            "e8(0b000)",
            "e16(0b001)",
            "e32(0b010)",
            "e64(0b011)",
            "res0(0b100)",
            "res1(0b101)",
            "res2(0b110)",
            "res3(0b111)",
        ]
        VSEW_SHIFT = 3
        VSEW_MASK = 7 << VSEW_SHIFT
        vsew = (rval & VSEW_MASK) >> VSEW_SHIFT
        self.dstate_add(rname, "vsew", VSEW[vsew])

        VLMUL = [
            "m1(0b000)",
            "m2(0b001)",
            "m4(0b010)",
            "m8(0b011)",
            "res0(0b100)",
            "mf8(0b101)",
            "mf4(0b110)",
            "mf2(0b111)",
        ]
        VLMUL_SHIFT = 0
        VLMUL_MASK = 7 << VLMUL_SHIFT
        vlmul = (rval & VLMUL_MASK) >> VLMUL_SHIFT
        self.dstate_add(rname, "vlmul", VLMUL[vlmul])

        res = rval & ~VILL_MASK
        res = res >> 8
        self.dstate_add(rname, "res", res)

    def dstate_decode_vcsr(self):
        rname = "vcsr"
        rval = self.state[1].get(rname, None)
        if rval is None:
            return

        # vxsat
        self.dstate_add(rname, "vxsat", True if rval & (1 << 0) else False)

        # vector fixed point rounding mode
        VXRM = ["rnu(0b00)", "rne(0b01)", "rdn(0b10)", "rod(0b11)"]
        VXRM_SHIFT = 1
        VXRM_MASK = 3 << VXRM_SHIFT
        vxrm = (rval & VXRM_MASK) >> VXRM_SHIFT
        self.dstate_add(rname, "vxrm", VXRM[vxrm])

        # reserved field
        res = rval >> 3
        self.dstate_add(rname, "res", res)

    def dstate_decode(self):
        self.dstate_decode_mstatus_fsvs()
        self.dstate_decode_fcsr()
        self.dstate_decode_vtype()
        self.dstate_decode_vcsr()

    # generate vcsr from vxrm and vxsat
    def gen_vcsr(self):
        return (self.state[1]["vxrm"] << 1) | self.state[1]["vxsat"]

    def check_vcsr(self):
        if self.has_vector:
            if self.gen_vcsr() != self.state[1]["vcsr"]:
                raise Exception("vxrm + vxsat does not match vcsr")

    def update(self):
        if self.has_vector:
            self.check_vcsr()
        self.dstate_decode()

    def init_iregs(self, value_mode):
        max_regval = (2 ** self.config["xlen"]) - 1
        for regname in RVREGS_IDX_DICT:
            self.state[0][regname] = self.gen_value(value_mode, 0, max_regval)
        self.state[0]["zero"] = 0
        self.state[0]["pc"] = 0

    def init_fregs(self, value_mode):
        if not self.has_float:
            return

        if "f" in self.rv_extensions:
            float_flen = 32
        if "d" in self.rv_extensions:
            float_flen = 64
        if "q" in self.rv_extensions:
            float_flen = 128
        float_flenb = float_flen // 8

        for i in range(0, 32):
            regname = "f" + str(i)
            self.state[1][regname] = self.gen_byte_values(value_mode, float_flenb)

    def init_vregs(self, value_mode):
        if not self.has_vector:
            return

        vector_vlenb = self.config["vector_vlen"] // 8
        for i in range(0, 32):
            regname = "v" + str(i)
            self.state[1][regname] = self.gen_byte_values(value_mode, vector_vlenb)

    def init(self, value_mode):
        self.state = [{}, {}]

        # MISC
        for key in ["xmemhash", "dmemhash"]:
            self.state[1][key] = "########################################"
        for key in ["lastPC", "#exceptions"]:
            self.state[1][key] = 0
        # I (+priv) state
        self.state[1]["mstatus.fs/vs"] = 0
        self.init_iregs(value_mode)

        # FP state
        if self.has_float:
            self.state[1]["mstatus.fs/vs"] = self.gen_value_from_selection(
                value_mode, self.state[1]["mstatus.fs/vs"], 0x6000, [0x0000, 0x6000]
            )
            self.state[1]["fcsr"] = self.gen_value_from_selection(
                value_mode, 0, (0x7 << 5), list((i << 5) for i in range(2**3))
            )
            self.init_fregs(value_mode)

        # V state
        if self.has_vector:

            self.state[1]["mstatus.fs/vs"] = self.gen_value_from_selection(
                value_mode, self.state[1]["mstatus.fs/vs"], 0x600, [0x000, 0x600]
            )
            vlmul = self.gen_value(value_mode, -3, 3)
            vsew = self.gen_value(value_mode, 0, 3)
            vma = self.gen_value(value_mode, 0, 1)
            vta = self.gen_value(value_mode, 0, 1)
            vtype = (
                (vma << 7) | (vta << 6) | (vsew << 3) | (vlmul & ((1 << 3) - 1))
            )  # TODO: vill = 0 (TODO quirk_ara_csrs - vill can not be set on ARA)
            vsew_val = 8 << vsew
            if vlmul >= 0:
                vlmul_val = 1 << vlmul
            else:
                vlmul_val = 1 / (1 << (-vlmul))
            vector_vlenb = self.config["vector_vlen"] // 8
            vlmax = int(vector_vlenb // vsew_val * vlmul_val)
            self.state[1]["vtype"] = vtype
            self.state[1]["vl"] = self.gen_value(
                value_mode, 0, vlmax
            )  # TODO -> according vtype
            self.state[1]["vlenb"] = 0
            self.state[1]["vstart"] = 0

            if self.quirk_ara_csrs:
                # vxrm is not writable on ARA -> prevent other values than 0
                vxrm_range = [0]
            else:
                vxrm_range = list(range(2**2))
            self.state[1]["vxrm"] = self.gen_value_from_selection(
                value_mode, 0, 0x3, vxrm_range
            )
            self.state[1]["vxsat"] = 0  # TODO
            self.state[1]["vcsr"] = self.gen_vcsr()

            self.init_vregs(value_mode)

        self.update()

    # randomize date in registers
    def randomize_registers(self):
        self.init_iregs(self.VALUE_MODE_RAND)
        self.init_fregs(self.VALUE_MODE_RAND)
        self.init_vregs(self.VALUE_MODE_RAND)

    def from_state(self, state):
        # TODO: check structure ?!
        self.state = state
        self.update()

    def as_string(self):
        output = ""

        regs = self.state[0]
        output += "REG".ljust(self.FORMAT_MAX_NAME_WIDTH, " ") + "VALUE\n"
        for regname in regs.keys():
            val = regs[regname]
            if regname != "pc":
                regname = regname + "(x" + str(RVREGS_IDX_DICT[regname]) + ")"
            regname = regname.ljust(self.FORMAT_MAX_NAME_WIDTH, " ")
            output += (
                regname
                + f"{val:#0{self.FORMAT_MAX_VALUE_WIDTH+2}x}("
                + str(val)
                + ")\n"
            )

        def state_entry_as_string(sname, val):
            res = ""
            if isinstance(val, bool):
                val = str(val)
            elif isinstance(val, int):
                val = f"{val:#0{self.FORMAT_MAX_VALUE_WIDTH+2}x}(" + str(val) + ")"
            elif isinstance(val, bytes):
                val = " ".join("{:02x}".format(x) for x in val)
            else:
                val = str(val)

            if len(val) < 48:
                sname = sname.ljust(self.FORMAT_MAX_NAME_WIDTH, " ")
                res += sname + str(val)
            else:
                res += sname + "\n"
                res += val
            return res

        output += "\n"
        output += "STATE".ljust(self.FORMAT_MAX_NAME_WIDTH, " ") + "VALUE\n"
        state = self.state[1]
        for sname in state.keys():
            val = state[sname]
            output += state_entry_as_string(sname, val) + "\n"
            # output dstats
            dstatekeys = self.dstate.get(sname, {}).keys()
            for dsname in dstatekeys:
                dval = self.dstate[sname][dsname]
                output += state_entry_as_string(" " + sname + "." + dsname, dval) + "\n"

        return output

    def compare(self, other, diff_full=False):
        output = ""
        is_equal = True

        regs_ref = self.state[0]
        regs_dut = other.state[0]
        output += (
            "REG".ljust(self.FORMAT_MAX_NAME_WIDTH, " ")
            + "REF".ljust(48, " ")
            + "DUT".ljust(48, " ")
            + "DIFF\n"
        )
        for regname in regs_ref.keys():
            val_ref = regs_ref[regname]
            val_dut = regs_dut[regname]
            entry_is_equal = True
            if val_ref != val_dut:
                entry_is_equal = False
                is_equal = False

            if regname != "pc":
                regname = regname + "(x" + str(RVREGS_IDX_DICT[regname]) + ")"
            regname = regname.ljust(self.FORMAT_MAX_NAME_WIDTH, " ")

            if diff_full or not entry_is_equal:
                if not entry_is_equal:
                    diff = "X"
                else:
                    diff = ""
                output += (
                    regname
                    + f"{val_ref:#0{self.FORMAT_MAX_VALUE_WIDTH+2}x}".ljust(48, " ")
                    + f"{val_dut:#0{self.FORMAT_MAX_VALUE_WIDTH+2}x}".ljust(48, " ")
                    + diff
                    + "\n"
                )

        def state_entry_compare(sname, val_ref, val_dut, diff_full):
            is_equal = True
            res = ""
            if val_ref != val_dut:
                is_equal = False

            if isinstance(val_ref, bool) and isinstance(val_dut, bool):
                val_ref_str = str(val_ref)
                val_dut_str = str(val_dut)
            elif isinstance(val_ref, int) and isinstance(val_dut, int):
                val_ref_str = (
                    f"{val_ref:#0{self.FORMAT_MAX_VALUE_WIDTH+2}x}("
                    + str(val_ref)
                    + ")"
                )
                val_dut_str = (
                    f"{val_dut:#0{self.FORMAT_MAX_VALUE_WIDTH+2}x}("
                    + str(val_dut)
                    + ")"
                )
            elif isinstance(val_ref, bytes) and isinstance(val_dut, bytes):
                val_ref_str = " ".join("{:02x}".format(x) for x in val_ref)
                val_dut_str = " ".join("{:02x}".format(x) for x in val_dut)
            else:
                val_ref_str = str(val_ref)
                val_dut_str = str(val_dut)

            if diff_full or not is_equal:
                if not is_equal:
                    diff = "X"
                else:
                    diff = ""
                if len(val_ref_str) < 48 and len(val_dut_str) < 48:
                    sname = sname.ljust(self.FORMAT_MAX_NAME_WIDTH, " ")
                    val_ref_str = val_ref_str.ljust(48, " ")
                    val_dut_str = val_dut_str.ljust(48, " ")
                    res += sname + str(val_ref_str) + str(val_dut_str) + diff
                else:
                    sname = sname.ljust(self.FORMAT_MAX_NAME_WIDTH + 48 + 48, " ")
                    res += sname + diff + "\n"
                    res += val_ref_str + "\n"
                    res += val_dut_str + "\n"

                    def str_helper(a, b):
                        if a == b:
                            return "  "
                        else:
                            return "^^"

                    res += " ".join(
                        [str_helper(a, b) for a, b in zip(val_ref, val_dut)]
                    )

            return (is_equal, res)

        output += "\n"
        output += (
            "STATE".ljust(self.FORMAT_MAX_NAME_WIDTH, " ")
            + "REF".ljust(48, " ")
            + "DUT".ljust(48, " ")
            + "DIFF\n"
        )
        state_ref = self.state[1]
        state_dut = other.state[1]
        for sname in state_ref.keys():
            val_ref = state_ref[sname]
            val_dut = state_dut[sname]
            (entry_is_equal, res) = state_entry_compare(
                sname, val_ref, val_dut, diff_full
            )
            if not entry_is_equal:
                is_equal = False
            if diff_full or not entry_is_equal:
                output += res + "\n"
            # output dstats
            dstatekeys = self.dstate.get(sname, {}).keys()
            for dsname in dstatekeys:
                dval_ref = self.dstate[sname][dsname]
                dval_dut = other.dstate[sname][dsname]
                (entry_is_equal, res) = state_entry_compare(
                    " " + sname + "." + dsname, dval_ref, dval_dut, diff_full
                )
                if diff_full or not entry_is_equal:
                    output += res + "\n"

        return (is_equal, output)

    def as_CodeFragmentList(self):

        def gen_byte_data(symname, values):
            data = (symname + ":").ljust(9) + ".byte "
            for value in values:
                data += f"{value:#0{2+2}x}" + ","
            return data[:-1] + ""

        f = CodeFragmentList()

        if self.has_float:

            if "f" in self.rv_extensions:
                inst_fload = "flw"
            if "d" in self.rv_extensions:
                inst_fload = "fld"
            if "q" in self.rv_extensions:
                inst_fload = "flq"

            code = """\
    // FLOATINGPOINT STATE DATA
    j _float_data_end
    .align 4\n"""
            for i in range(0, 32):
                symname = "_reg_f" + str(i)
                regname = "f" + str(i)
                code += gen_byte_data(symname, self.state[1][regname]) + "\n"
            code += """\
_float_data_end:
    // FLOATINTPOINT STATE\n"""
            for i in range(0, 32):
                symname = "_reg_f" + str(i)
                regname = "f" + str(i)
                code += "    la t0, " + symname + "\n"
                code += "    " + inst_fload + "  " + regname + ", 0(t0)\n"
            f.add(CodeFragment(code))

            f.add(
                CodeFragment(
                    """\
    // restore fcsr = {dval}
    li t0, {val}
    csrrw zero, fcsr, t0\n""".format(
                        dval=self.dstate_entry_as_string("fcsr"),
                        val=hex(self.state[1]["fcsr"]),
                    )
                )
            )

        if self.has_vector:
            code = """\
    // VECTOR STATE DATA
    j _vector_data_end
    .align 4\n"""
            for i in range(0, 32):
                symname = "_reg_v" + str(i)
                regname = "v" + str(i)
                code += gen_byte_data(symname, self.state[1][regname]) + "\n"
            code += """\
_vector_data_end:
    // VECTOR STATE (clear potential vill with vsetvli)
    vsetvli t0, zero, e8, ta, ma\n"""
            for i in range(0, 32):
                symname = "_reg_v" + str(i)
                regname = "v" + str(i)
                code += "    la t0, " + symname + "\n"
                code += "    vl1r.v " + regname + ", (t0)\n"

            f.add(CodeFragment(code))

            f.add(
                CodeFragment(
                    """\
    // restore vl = {vl_dval}
    li t0, {vl_val}
    // restore vtype = {vtype_dval}
    li t1, {vtype_val}
    vsetvl zero, t0, t1\n""".format(
                        vl_dval=self.state[1]["vl"],
                        vl_val=hex(self.state[1]["vl"]),
                        vtype_dval=self.dstate_entry_as_string("vtype"),
                        vtype_val=hex(self.state[1]["vtype"]),
                    )
                )
            )

            for csr in ["vstart", "vcsr"]:
                f.add(
                    CodeFragment(
                        """\
    // restore {name} = {dval}
    li t0, {val}
    csrrw zero, {name}, t0\n""".format(
                            name=csr,
                            dval=self.dstate_entry_as_string(csr),
                            val=hex(self.state[1][csr]),
                        )
                    )
                )

        f.add(CodeFragment("    // STATE"))
        f.add(
            CodeFragment(
                """\

    // restore mstatus.fs/vs = {dval}
    li t0, 0x6600
    csrc mstatus, t0
    li t0, {val}
    csrs mstatus, t0\n""".format(
                    dval=self.dstate_entry_as_string("mstatus.fs/vs"),
                    val=hex(self.state[1]["mstatus.fs/vs"]),
                )
            )
        )

        f.add(CodeFragment("    // restore registers"))
        for regname, regval in self.state[0].items():
            if regname == "pc" or regname == "zero":
                continue
            f.add(
                CodeFragment(
                    (
                        "    li x" + str(RVREGS_IDX_DICT[regname]) + ", " + hex(regval)
                    ).ljust(33)
                    + "// "
                    + regname
                )
            )

        return f


class StateDump:
    def get_len(self):
        return 0

    def gen_save(self):
        pass

    def gen_load(self, values):
        pass

    def extract(self, dumpfile):
        pass


class RegStateDump(StateDump):
    def __init__(self, config=None, addr=None, offset=0, reglist=[5, 6, 7]):
        self.memstart = config["memstart"]
        self.addr = addr
        self.offset = offset
        self.reglist = reglist
        xlen = config["xlen"]
        self.xlenb = xlen // 8
        if xlen == 32:
            self.inst_sreg = "sw"
            self.inst_lreg = "lw"
        elif xlen == 64:
            self.inst_sreg = "sd"
            self.inst_lreg = "ld"
        else:
            raise Exception(
                "xlen=" + str(xlen) + " not supported! Valid values are 32, or 64"
            )

    def get_len(self):
        return len(self.reglist) * self.xlenb

    # save to mem
    def gen_save(self):
        code = ""
        for i in range(len(self.reglist)):
            code += self._gen_store(
                reg="x" + str(self.reglist[i]), offset=self.offset + i * self.xlenb
            )
        return code

    # restore from mem
    def gen_load(self):
        code = ""
        for i in range(len(self.reglist)):
            code += self._gen_load(
                reg="x" + str(self.reglist[i]), offset=self.offset + i * self.xlenb
            )
        return code

    # set to values
    def gen_set(self, values):
        code = ""
        for i in range(len(self.reglist)):
            code += "    li x" + str(self.reglist[i]) + ", " + hex(values[i]) + "\n"
        return code

    # extract from dump file
    def extract(self, dumpfile):
        values = []
        dumpfile.seek(self.addr - self.memstart + self.offset)
        for i in self.reglist:
            val = dumpfile.read(self.xlenb)
            values.append(int.from_bytes(val, byteorder="little"))
        return values

    def _gen_load_store(self, store=False, reg="x0", offset=0):
        code = "    "
        if store:
            code += self.inst_sreg
        else:
            code += self.inst_lreg
        code += " " + reg + ", " + str(offset) + "(gp)\n"
        return code

    def _gen_load(self, reg="x0", offset=0):
        return self._gen_load_store(reg=reg, offset=offset)

    def _gen_store(self, reg="x0", offset=0):
        return self._gen_load_store(store=True, reg=reg, offset=offset)


class VRegStateDump(StateDump):
    def __init__(self, config=None, addr=None, offset=0, reglist=None):
        self.memstart = config["memstart"]
        self.addr = addr
        self.offset = offset
        self.reglist = reglist
        self.vlenb = config["vector_vlen"] // 8

    def get_len(self):
        return len(self.reglist) * self.vlenb

    # save to mem
    def gen_save(self):
        # clear potential vill
        code = "    vsetvli t0, zero, e8, m1, ta, ma\n"
        code += "    addi t0, gp, " + str(self.offset) + "\n"
        for i in range(len(self.reglist)):
            code += self._gen_store(reg="v" + str(self.reglist[i]))
            code += "    addi t0, t0, " + str(self.vlenb) + "\n"
        return code

    # restore from mem
    def gen_load(self):
        # clear potential vill
        code = "    vsetvli t0, zero, e8, m1, ta, ma\n"
        code += "    addi t0, gp, " + str(self.offset) + "\n"
        for i in range(len(self.reglist)):
            code += self._gen_load(reg="v" + str(self.reglist[i]))
            code += "    addi t0, t0, " + str(self.vlenb) + "\n"
        return code

    # set to values
    def gen_set(self, values):
        raise Exception("not implemented")

    # extract from dump file
    def extract(self, dumpfile):
        values = []
        dumpfile.seek(self.addr - self.memstart + self.offset)
        for i in self.reglist:
            val = dumpfile.read(self.vlenb)
            values.append(val)
        return values

    def _gen_load_store(self, store=False, reg="v0"):
        code = "    "
        if store:
            code += "vs1r.v"
        else:
            code += "vl1r.v"
        code += " " + reg + ", (t0)\n"
        return code

    def _gen_load(self, reg="v0", offset=0):
        return self._gen_load_store(reg=reg)

    def _gen_store(self, reg="v0", offset=0):
        return self._gen_load_store(store=True, reg=reg)


# defines a full state dump for build and run
class DumpFile:
    def __init__(self, config=None, filename="", addr=None):

        self.dumpfile_reserve = config["dumpfile_reserve"]
        self.rv_extensions = config["rv_extensions"]
        self.memstart = config["memstart"]
        self.memlen = config["memlen"]
        self.xmemstart = config["xmemstart"]
        self.xmemlen = config["xmemlen"]
        self.dmemstart = config["dmemstart"]
        self.dmemlen = config["dmemlen"]
        self.keep_dumpfile = config.get("DumpFile_keep_dumpfile", False)
        self.filename = filename
        self.addr = addr
        self.len = 0

        # for temporary register (save/restore (t0,t1,t2))
        self.tmpregstore = RegStateDump(
            config=config, addr=addr, offset=self.len, reglist=[5, 6, 7]
        )
        self.len += self.tmpregstore.get_len()

        # store/dump last pc, exception counter, mstatus
        self.estate = RegStateDump(
            config=config, addr=addr, offset=self.len, reglist=[5, 6, 7]
        )
        self.len += self.estate.get_len()

        # save all fregs
        float_flen = 0
        if "f" in self.rv_extensions:
            float_flen = 32
        if "d" in self.rv_extensions:
            float_flen = 64
        if "q" in self.rv_extensions:
            float_flen = 128
        if float_flen > 0:
            # store/dump fcsr
            config["float_flen"] = float_flen
            self.fstate = RegStateDump(
                config=config, addr=addr, offset=self.len, reglist=[5]
            )
            self.len += self.fstate.get_len()
            self.fregs = FDQRegStateDump(
                config=config,
                addr=addr,
                offset=self.len,
                reglist=[i for i in range(32)],
            )
            self.len += self.fregs.get_len()

        # save all vregs
        if "v" in self.rv_extensions:
            # store/dump vtype, vl, vlenb, vstart, vxrm, vxsat, vcsr
            self.vstate = RegStateDump(
                config=config,
                addr=addr,
                offset=self.len,
                reglist=[5, 6, 7, 8, 9, 10, 11],
            )
            self.len += self.vstate.get_len()
            self.vregs = VRegStateDump(
                config=config,
                addr=addr,
                offset=self.len,
                reglist=[i for i in range(32)],
            )
            self.len += self.vregs.get_len()

    def get_len(self):
        return self.len

    def get_addr(self):
        return self.addr

    def get_filename(self):
        return self.filename

    def delete(self):
        if os.path.exists(self.filename):
            os.remove(self.filename)

    def sha1(self, dumpfile, start=0, len=0):
        BUF_SIZE = 65536

        # get size
        dumpfile.seek(0, 2)
        size = dumpfile.tell()

        # check bounds
        if len == 0 or len > size:
            len = size

        # set to start
        dumpfile.seek(start)

        # init
        sha1 = hashlib.sha1()

        # while len:
        while True:
            readlen = min(len, BUF_SIZE)
            data = dumpfile.read(readlen)
            len -= readlen
            # safety
            if not data:
                break
            sha1.update(data)

        return sha1.hexdigest()

    def extract(self):
        ret = {}
        with open(self.filename, "rb") as file:
            # exclude dump area from xmemhash (TODO: cleanup the whole dumpfile_reserve handling)
            ret["xmemhash"] = self.sha1(
                file,
                self.xmemstart - self.memstart,
                self.xmemlen - self.dumpfile_reserve,
            )
            ret["dmemhash"] = self.sha1(
                file, self.dmemstart - self.memstart, self.dmemlen
            )
            val = self.estate.extract(file)
            ret["lastPC"] = val[0]
            ret["#exceptions"] = val[1]
            ret["mstatus.fs/vs"] = val[2]

            if sum(e in self.rv_extensions for e in "fdq"):
                val = self.fstate.extract(file)
                ret["fcsr"] = val[0]

                val = self.fregs.extract(file)
                i = 0
                for freg in val:
                    ret["f" + str(i)] = freg
                    i += 1

            if "v" in self.rv_extensions:
                val = self.vstate.extract(file)
                ret["vtype"] = val[0]
                ret["vl"] = val[1]
                ret["vlenb"] = val[2]
                ret["vstart"] = val[3]
                ret["vxrm"] = val[4]
                ret["vxsat"] = val[5]
                ret["vcsr"] = val[6]

                val = self.vregs.extract(file)
                i = 0
                for vreg in val:
                    ret["v" + str(i)] = vreg
                    i += 1

        if not self.keep_dumpfile:
            self.delete()

        return ret


class FDQRegStateDump(StateDump):
    def __init__(self, config=None, addr=None, offset=0, reglist=None):
        self.memstart = config["memstart"]
        self.addr = addr
        self.reglist = reglist
        float_flen = config["float_flen"]
        self.flenb = float_flen // 8

        # make sure offset is aligned to float_flen
        self.alignment_offset = self.flenb - (offset % self.flenb)
        self.offset = offset + self.alignment_offset
        self.len = len(self.reglist) * self.flenb + self.alignment_offset

        if self.flenb == 4:
            self.inst_sreg = "fsw"
            self.inst_lreg = "flw"
        elif self.flenb == 8:
            self.inst_sreg = "fsd"
            self.inst_lreg = "fld"
        elif self.flenb == 16:
            self.inst_sreg = "fsq"
            self.inst_lreg = "flq"
        else:
            raise Exception("Invalid floating point flen " + str(self.float_flen))

    def get_len(self):
        return self.len

    # save to mem
    def gen_save(self):
        code = ""
        for i in range(len(self.reglist)):
            code += self._gen_store(regnr=self.reglist[i])
        return code

    # restore from mem
    def gen_load(self):
        code = ""
        for i in range(len(self.reglist)):
            code += self._gen_load(regnr=self.reglist[i])
        return code

    # set to values
    def gen_set(self, values):
        raise Exception("not implemented")

    # extract from dump file
    def extract(self, dumpfile):
        values = []
        dumpfile.seek(self.addr - self.memstart + self.offset)
        for i in self.reglist:
            val = dumpfile.read(self.flenb)
            values.append(val)
        return values

    def _gen_load_store(self, store=False, regnr=0):
        regoffset = self.offset + regnr * self.flenb
        code = "    "
        if store:
            code += self.inst_sreg
        else:
            code += self.inst_lreg
        code += " f" + str(regnr) + ", " + str(regoffset) + "(gp)\n"
        return code

    def _gen_load(self, regnr=0, offset=0):
        return self._gen_load_store(regnr=regnr)

    def _gen_store(self, regnr=0, offset=0):
        return self._gen_load_store(store=True, regnr=regnr)
