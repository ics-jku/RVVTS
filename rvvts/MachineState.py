#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
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
        self.VALUE_MODE_ZERO = 0
        self.VALUE_MODE_RAND = 1
        self.config = config
        self.rv_extensions = config["rv_extensions"]
        self.has_float = sum(e in self.rv_extensions for e in "fdq") > 0
        self.has_vector = "v" in self.rv_extensions
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

    # generate vcsr from vxrm and vxsat
    def gen_vcsr(self):
        return (self.state[1]["vxrm"] << 1) | self.state[1]["vxsat"]

    def check_vcsr(self):
        if self.gen_vcsr() != self.state[1]["vcsr"]:
            raise Exception("vxrm + vxsat does not match vcsr")

    def check(self):
        # TODO improve
        self.check_vcsr()

    def init_iregs(self, value_mode):
        max_regval = (2 ** self.config["xlen"]) - 1
        for regname in RVREGS_IDX_DICT:
            self.state[0][regname] = self.gen_value(value_mode, 0, max_regval)
        self.state[0]["zero"] = 0

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
            self.state[1]["vxrm"] = self.gen_value_from_selection(
                value_mode, 0, 0x3, list(range(2**2))
            )
            self.state[1]["vxsat"] = 0  # TODO
            self.state[1]["vcsr"] = self.gen_vcsr()
            vlmul = self.gen_value(value_mode, -3, 3)
            vsew = self.gen_value(value_mode, 0, 3)
            vma = self.gen_value(value_mode, 0, 1)
            vta = self.gen_value(value_mode, 0, 1)
            vtype = (
                (vma << 7) | (vta << 6) | (vsew << 3) | (vlmul & ((1 << 3) - 1))
            )  # TODO: vill = 0
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
            self.state[1]["vstart"] = 0  # TODO

            self.init_vregs(value_mode)

        self.check()

    # randomize date in registers
    def randomize_registers(self):
        self.init_iregs(self.VALUE_MODE_RAND)
        self.init_fregs(self.VALUE_MODE_RAND)
        self.init_vregs(self.VALUE_MODE_RAND)

    def from_state(self, state):
        # TODO: check structure ?!
        self.state = state
        self.check()

    def as_string(self):
        output = ""

        regs = self.state[0]
        output += "REG".ljust(16, " ") + "VALUE\n"
        for regname in regs.keys():
            val = regs[regname]
            if regname != "pc":
                regname = regname + "(x" + str(RVREGS_IDX_DICT[regname]) + ")"
            regname = regname.ljust(16, " ")
            output += regname + f"{val:#0{16+2}x}(" + str(val) + ")\n"

        output += "\n"
        output += "STATE".ljust(16, " ") + "VALUE\n"
        state = self.state[1]
        for sname in state.keys():
            val = state[sname]
            if isinstance(val, int):
                val = f"{val:#0{16+2}x}(" + str(val) + ")"
            elif isinstance(val, bytes):
                val = " ".join("{:02x}".format(x) for x in val)
            else:
                val = str(val)

            if len(val) < 48:
                sname = sname.ljust(16, " ")
                output += sname + str(val) + "\n"
            else:
                output += sname + "\n"
                output += val + "\n"

        return output

    def compare(self, other):
        output = ""
        is_equal = True

        regs_ref = self.state[0]
        regs_dut = other.state[0]
        output += (
            "REG".ljust(16, " ")
            + "REF".ljust(48, " ")
            + "DUT".ljust(48, " ")
            + "DIFF\n"
        )
        for regname in regs_ref.keys():
            val_ref = regs_ref[regname]
            val_dut = regs_dut[regname]
            if val_ref != val_dut:
                diff = "X"
                is_equal = False
            else:
                diff = ""
            if regname != "pc":
                regname = regname + "(x" + str(RVREGS_IDX_DICT[regname]) + ")"
            regname = regname.ljust(16, " ")
            output += (
                regname
                + f"{val_ref:#0{16+2}x}".ljust(48, " ")
                + f"{val_dut:#0{16+2}x}".ljust(48, " ")
                + diff
                + "\n"
            )

        output += "\n"
        output += (
            "STATE".ljust(16, " ")
            + "REF".ljust(48, " ")
            + "DUT".ljust(48, " ")
            + "DIFF\n"
        )
        state_ref = self.state[1]
        state_dut = other.state[1]
        for sname in state_ref.keys():
            val_ref = state_ref[sname]
            val_dut = state_dut[sname]
            if val_ref != val_dut:
                diff = "X"
                is_equal = False
            else:
                diff = ""

            if isinstance(val_ref, int) and isinstance(val_dut, int):
                val_ref_str = f"{val_ref:#0{16+2}x}(" + str(val_ref) + ")"
                val_dut_str = f"{val_dut:#0{16+2}x}(" + str(val_dut) + ")"
            elif isinstance(val_ref, bytes) and isinstance(val_dut, bytes):
                val_ref_str = " ".join("{:02x}".format(x) for x in val_ref)
                val_dut_str = " ".join("{:02x}".format(x) for x in val_dut)
            else:
                val_ref_str = str(val_ref)
                val_dut_str = str(val_dut)

            if len(val_ref_str) < 48 and len(val_dut_str) < 48:
                sname = sname.ljust(16, " ")
                val_ref_str = val_ref_str.ljust(48, " ")
                val_dut_str = val_dut_str.ljust(48, " ")
                output += sname + str(val_ref_str) + str(val_dut_str) + diff + "\n"
            else:
                sname = sname.ljust(16 + 48 + 48, " ")
                output += sname + diff + "\n"
                output += val_ref_str + "\n"
                output += val_dut_str + "\n"

                def str_helper(a, b):
                    if a == b:
                        return "  "
                    else:
                        return "^^"

                output += (
                    " ".join([str_helper(a, b) for a, b in zip(val_ref, val_dut)])
                    + "\n"
                )

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

            f.add(CodeFragment("    // FLOATINGPOINT STATE DATA"))
            f.add(CodeFragment("    j _float_data_end"))
            f.add(CodeFragment("    .align 4"))
            for i in range(0, 32):
                symname = "_reg_f" + str(i)
                regname = "f" + str(i)
                f.add(CodeFragment(gen_byte_data(symname, self.state[1][regname])))
            f.add(CodeFragment("_float_data_end:"))
            f.add(CodeFragment("    // FLOATINTPOINT STATE"))
            for i in range(0, 32):
                symname = "_reg_f" + str(i)
                regname = "f" + str(i)
                f.add(CodeFragment("    la t0, " + symname))
                f.add(CodeFragment("    " + inst_fload + "  " + regname + ", 0(t0)"))
            for csr in ["fcsr"]:
                f.add(CodeFragment("    li t0, " + hex(self.state[1][csr])))
                f.add(CodeFragment("    csrrw zero, " + csr + ", t0"))

        if self.has_vector:
            f.add(CodeFragment("    // VECTOR STATE DATA"))
            f.add(CodeFragment("    j _vector_data_end"))
            f.add(CodeFragment("    .align 4"))
            for i in range(0, 32):
                symname = "_reg_v" + str(i)
                regname = "v" + str(i)
                f.add(CodeFragment(gen_byte_data(symname, self.state[1][regname])))
            f.add(CodeFragment("_vector_data_end:"))
            f.add(CodeFragment("    // VECTOR STATE"))
            # clear potential vill
            f.add(CodeFragment("    vsetvli t0, zero, e8, ta, ma"))
            for i in range(0, 32):
                symname = "_reg_v" + str(i)
                regname = "v" + str(i)
                f.add(CodeFragment("    la t0, " + symname))
                f.add(CodeFragment("    vl1r.v " + regname + ", (t0)"))
            f.add(CodeFragment("    li t0, " + hex(self.state[1]["vl"])))
            f.add(CodeFragment("    li t1, " + hex(self.state[1]["vtype"])))
            f.add(CodeFragment("    vsetvl zero, t0, t1"))
            for csr in ["vstart", "vcsr"]:
                f.add(CodeFragment("    li t0, " + hex(self.state[1][csr])))
                f.add(CodeFragment("    csrrw zero, " + csr + ", t0"))

        f.add(CodeFragment("    // STATE"))
        f.add(CodeFragment("    // restore mstatus"))
        # TODO: CLEANUP / IMPROVE
        f.add(CodeFragment("    li t0, 0x6600"))
        f.add(CodeFragment("    csrc mstatus, t0"))
        f.add(CodeFragment("    li t0, " + hex(self.state[1]["mstatus.fs/vs"])))
        f.add(CodeFragment("    csrs mstatus, t0"))

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
