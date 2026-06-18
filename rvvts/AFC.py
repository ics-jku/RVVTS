#!/usr/bin/env python
# coding: utf-8
#
# (C) 2025-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

import os
import re


# AFC Categorizer base class and default
class AFC:
    def __init__(self, config=None):
        # override in derived classes
        self.AFC_Categorizer = "NONE"
        self.AVAIL_CATEGORIES = ["NOCAT"]
        self.AVAIL_ATTRIBUTES = []

    def run(self, dir, res_code_block, res_end_ref_mstate, res_end_dut_mstate):
        # categorize
        category, attributes = self._categorize(
            dir, res_code_block, res_end_ref_mstate, res_end_dut_mstate
        )

        # write report
        with open(os.path.join(dir, "AFC_report.log"), "w") as f:
            f.write(f"AFC Categorizer: {self.AFC_Categorizer}\n")
            f.write(f"AVAIL CATEGORIES: {self.AVAIL_CATEGORIES}\n")
            f.write(f"AVAIL ATTRIBUTES: {self.AVAIL_ATTRIBUTES}\n")
            f.write(f"CATEGORY: {category}\n")
            f.write(f"ATTRIBUTES: {attributes}\n")

        # return results
        return category, attributes

    # override in derived classes
    def _categorize(self, dir, res_code_block, res_end_ref_mstate, res_end_dut_mstate):
        # default: nocat, no attributes
        return self.AVAIL_CATEGORIES[0], []


# AFC Categorizer for PULP Ara
# presented in
# "
# Manfred Schlägl, Jonas Reichhardt, and Daniel Große.
# From generation to failure categorization:
# An open-source automated RTL verification framework for RVV.
# In ACM Great Lakes Symposium on VLSI (GLSVLSI), 2026.
# "
class AFC_Ara(AFC):
    def __init__(self, config=None):
        super().__init__(config)

        # override
        self.AFC_Categorizer = "Ara"
        self.AVAIL_CATEGORIES = [
            "UNKNOWN",
            "ARA_HANG",
            "PCERR",
            "VCSR_ONLY",
            "VCSR",
            "EXC_INVALID_ACCEPT",
            "EXC_INVALID_REJECT",
            "VLENB",
            "MSTATUS_STRANGE_VAL",
            "MSTATUS_EXT_REF",
            "MSTATUS_EXT_DUT",
            "MSTATUS_DIFF",
            "VTYPE_VILL_SET_ERROR",
            "VTYPE_INVALID_ACCEPT",
            "VTYPE_VILL_CLEAR_ERROR",
            "VTYPE_INVALID_REJECT",
            "VTYPE_DIFF",
            "VL_ONLY",
            "VSTART_WEXC",
            "VSTART_WOEXC",
            "FCSR_FFLAGS_ONLY",
            "FCSR_ONLY",
            "XMEM_ONLY",
            "DMEM_ONLY",
            "IREG_ONLY",
            "FREG_ONLY",
            "FREG_FCSR_ONLY",
            "VREG_ONLY",
            "VREG_FCSR_ONLY",
            "VALREG_ONLY",
        ]

    # override
    def _categorize(self, dir, res_code_block, res_end_ref_mstate, res_end_dut_mstate):

        def tgrepmult(text, patterns):
            res = [[] for i in patterns]

            pms = []
            for pattern in patterns:
                pms.append(re.compile(pattern))

            for line in text.split("\n"):
                for idx, pm in enumerate(pms):
                    if pm.match(line):
                        res[idx].append(line)

            return res

        IALL = 0
        IIREG = 1
        IPC = 2
        IXMEM = 3
        IDMEM = 4
        ILASTPC = 5
        IEXC = 6
        IMSTAT = 7
        IFCSR = 8
        IFREG = 9
        IVLENB = 10
        IVTYPE = 11
        IVL = 12
        IVSTART = 13
        IVCSR = 14
        IVREG = 15
        IVTYPE_OK = 16
        IEXC_OK = 17

        # diff and extract attributes to investigate
        mstate_diff = res_end_ref_mstate.compare(res_end_dut_mstate, diff_full=True)[1]
        ps = r"^"
        pe = r".*X$"

        # FOR DEBUG
        # with open(os.path.join(dir, "AFC_debug.log"), "w") as f:
        #    f.write(str(res_end_ref_mstate))
        #    f.write(str(res_end_dut_mstate))
        #    f.write(
        #        str(res_end_ref_mstate.compare(res_end_dut_mstate, diff_full=False)[1])
        #    )

        patterns = [
            ps + r"[#0-9a-zA-Z].* " + pe,
            ps + r"[0-9a-zA-Z].*\(x\d\d?\) " + pe,
            ps + r"pc " + pe,
            ps + r"xmemhash " + pe,
            ps + r"dmemhash " + pe,
            ps + r"lastPC " + pe,
            ps + r"#exceptions " + pe,
            ps + r"mstatus.fs/vs " + pe,
            ps + r"fcsr " + pe,
            ps + r"f\d\d? " + pe,
            ps + r"vlenb " + pe,
            ps + r"vtype " + pe,
            ps + r"vl " + pe,
            ps + r"vstart " + pe,
            ps + r"(vxrm|vxsat|vcsr) " + pe,
            ps + r"v\d\d? " + pe,
            ps + r"vtype " + ".*$",
            ps + r"#exceptions " + ".*$",
        ]
        r = tgrepmult(mstate_diff, patterns)
        n_all0 = len(r[IALL])
        n_all1 = sum(len(x) for x in r) - n_all0 - len(r[IVTYPE_OK]) - len(r[IEXC_OK])

        # sanity check
        if n_all0 != n_all1:
            print(f"AFC_Ara: ERROR: is: {str(n_all1)}, should be: {str(n_all0)}")
            print('------ should be (contains also "_OK" matches')
            for i in r[(IALL + 1) :]:
                for j in i:
                    print(j)
            print('------ is (contains only not "_OK" matches')
            for i in r[IALL]:
                print(i)
            print("------")
            raise Exception(
                "AFC_Ara: Internal Error! -> Checkout output and contact developers"
            )

        # classify
        category = "UNKNOWN"

        if res_end_dut_mstate.state[1]["lastPC"] == -1:
            category = "ARA_HANG"

        elif len(r[IPC]) or len(r[ILASTPC]):
            category = "PCERR"

        elif len(r[IVCSR]) == n_all0:
            category = "VCSR_ONLY"

        elif len(r[IVCSR]):
            # vcsr, vxrm, vxsat and others
            category = "VCSR"

        elif len(r[IEXC]):
            if len(r[IEXC]) > 1:
                print("AFC_Ara: ERROR: more than one exception entries")
                print(r)
                raise Exception(
                    "AFC_Ara: Internal Error! -> Checkout output and contact developers"
                )

            tmp = re.split(r"  *", r[IEXC][0])
            cref = int(tmp[1].split("(")[0], 16)
            cdut = int(tmp[2].split("(")[0], 16)
            if cref > cdut:
                category = "EXC_INVALID_ACCEPT"
            elif cref < cdut:
                category = "EXC_INVALID_REJECT"
            else:
                print("AFC_Ara: ERROR: exceptions match")
                print(r)
                raise Exception(
                    "AFC_Ara: Internal Error! -> Checkout output and contact developers"
                )

        elif len(r[IVLENB]):
            category = "VLENB"

        # TODO MSTATUS.FS/VS contains only FS and VS -> MSTATUS_STRANGE_VAL can never happen!!!
        elif len(r[IMSTAT]):
            if len(r[IMSTAT]) > 1:
                print("AFC_Ara: ERROR: more than one mstat entries")
                print(r)
                raise Exception(
                    "AFC_Ara: Internal Error! -> Checkout output and contact developers"
                )

            tmp = re.split(r"  *", r[IMSTAT][0])
            cref = int(tmp[1].split("(")[0], 16)
            cdut = int(tmp[2].split("(")[0], 16)

            if cref == cdut:
                print("AFC_Ara: ERROR: mstatus matches")
                print(r)
                raise Exception(
                    "AFC_Ara: Internal Error! -> Checkout output and contact developers"
                )

            if cref & 0xFFFF_FFFF_FFFF_99FF or cdut & 0xFFFF_FFFF_FFFF_99FF:
                category = "MSTATUS_STRANGE_VAL"
            else:
                cbref = cref.bit_count()
                cbdut = cdut.bit_count()
                if cbref > cbdut:
                    category = "MSTATUS_EXT_REF"
                elif cbref < cbdut:
                    category = "MSTATUS_EXT_DUT"
                else:
                    category = "MSTATUS_DIFF"

        elif len(r[IVTYPE]):
            if len(r[IVTYPE]) > 1:
                print("AFC_Ara: ERROR: more than one vtype entries")
                print(r)
                raise Exception(
                    "AFC_Ara: Internal Error! -> Checkout output and contact developers"
                )

            tmp = re.split(r"  *", r[IVTYPE][0])
            cref = int(tmp[1].split("(")[0], 16)
            cdut = int(tmp[2].split("(")[0], 16)

            if cref == cdut:
                print("AFC_Ara: ERROR: vtype matches")
                print(r)
                raise Exception(
                    "AFC_Ara: Internal Error! -> Checkout output and contact developers"
                )

            cref_vill = cref & 0x8000_0000_0000_0000
            cdut_vill = cdut & 0x8000_0000_0000_0000
            cref_rest = cref & ~0x8000_0000_0000_0000
            cdut_rest = cdut & ~0x8000_0000_0000_0000

            vtype_valid_zero = False
            if cref_rest == 0 and cdut_rest == 0:
                vtype_valid_zero = True

            if cref_vill and (not cdut_vill):
                if vtype_valid_zero:
                    # vill is differnt, but the value is ok, so it must be a VILL set error
                    category = "VTYPE_VILL_SET_ERROR"
                else:
                    # vill is different but some value is not 0, so it must be invalid accept
                    category = "VTYPE_INVALID_ACCEPT"
            elif (not cref_vill) and cdut_vill:
                if vtype_valid_zero:
                    # vill is differnt, but the value is ok, so it must be a VILL clear error
                    category = "VTYPE_VILL_CLEAR_ERROR"
                else:
                    # vill is different but some value is not 0, so it must be invalid reject
                    category = "VTYPE_INVALID_REJECT"
            else:
                category = "VTYPE_DIFF"

        elif len(r[IVL]) == n_all0:
            category = "VL_ONLY"

        elif len(r[IVSTART]):
            # exception missmatch already handled above -> cref == cdut
            tmp = re.split(r"  *", r[IEXC_OK][0])
            cref = int(tmp[1].split("(")[0], 16)
            if cref > 0:
                category = "VSTART_WEXC"
            else:
                category = "VSTART_WOEXC"

        elif len(r[IFCSR]) == n_all0:
            tmp = re.split(r"  *", r[IFCSR][0])
            cref = int(tmp[1].split("(")[0], 16)
            cdut = int(tmp[2].split("(")[0], 16)

            fflags_ref = cref & 0x1F
            fflags_dut = cdut & 0x1F
            rest_ref = cref & ~0x1F
            rest_dut = cref & ~0x1F
            #            frm_ref = cref & 0xe0
            #            frm_dut = cdut & 0xe0
            if fflags_ref != fflags_dut and rest_ref == rest_dut:
                category = "FCSR_FFLAGS_ONLY"
            else:
                category = "FCSR_ONLY"

        elif len(r[IXMEM]) == n_all0:
            category = "XMEM_ONLY"
        elif len(r[IDMEM]) == n_all0:
            category = "DMEM_ONLY"

        elif len(r[IIREG]) == n_all0:
            category = "IREG_ONLY"

        elif len(r[IFREG]) == n_all0:
            category = "FREG_ONLY"
        elif (
            len(r[IFREG])
            and len(r[IFCSR])
            and ((len(r[IFREG]) + len(r[IFCSR])) == n_all0)
        ):
            category = "FREG_FCSR_ONLY"

        elif len(r[IVREG]) == n_all0:
            category = "VREG_ONLY"
        elif (
            len(r[IVREG])
            and len(r[IFCSR])
            and ((len(r[IVREG]) + len(r[IFCSR])) == n_all0)
        ):
            category = "VREG_FCSR_ONLY"

        elif (len(r[IIREG]) + len(r[IFREG]) + len(r[IVREG])) == n_all0:
            category = "VALREG_ONLY"

        # default: nocat, no attributes
        return category, []
