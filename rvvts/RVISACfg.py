#!/usr/bin/env python
# coding: utf-8
#
# (C) 2026 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from collections import OrderedDict


class RVISACfg:

    class RVExtensions:
        def __init__(self, xlen=32, vlen=0, velen=0):

            self.xlen = xlen
            self.vlen = vlen
            self.velen = velen
            self.flen = 0
            self.fset_max = ""
            self.fload_max = ""
            self.fstore_max = ""
            self.ext = OrderedDict(
                [
                    ("m", False),
                    ("f", False),
                    ("d", False),
                    ("q", False),
                    ("c", False),
                    ("b", False),
                    ("v", False),
                    ("zbc", False),
                    ("zfh", False),
                    ("zicsr", False),
                    ("zifencei", False),
                ]
            )
            self.update_float()

        def update_float(self):
            # TODO: fset_max -> consider xlen (.w/.d)
            if self.is_set("q"):
                self.flen = 128
                self.fset_max = "fcvt.q.w"
                self.fload_max = "flq"
                self.fstore_max = "fsq"
            elif self.is_set("d"):
                self.flen = 64
                self.fset_max = "fcvt.d.w"
                self.fload_max = "fld"
                self.fstore_max = "fsd"
            # Note: zfh requires f -> so if we have zfh we still have 32 bit f registers
            elif self.is_set_any(["f", "zfh"]):
                self.flen = 32
                self.fset_max = "fcvt.s.w"
                self.fload_max = "flw"
                self.fstore_max = "fsw"
            else:
                self.flen = 0
                self.fload_max = ""
                self.fstore_max = ""

        def get_xlen(self):
            return self.xlen

        def get_vlen(self):
            return self.vlen

        def get_velen(self):
            return self.velen

        def get_flen(self):
            return self.flen

        def get_fset_max(self):
            return self.fset_max

        def get_fload_max(self):
            return self.fload_max

        def get_fstore_max(self):
            return self.fstore_max

        def set(self, exts):
            if not isinstance(exts, list):
                exts = [exts]
            for ext in exts:
                ext = ext.casefold()
                if ext not in self.ext.keys():
                    raise Exception(f"RVExtension: unsupported extension to set {ext}")
                self.ext[ext] = True
            self.update_float()

        def is_set_any(self, exts):
            ret = False
            if not isinstance(exts, list):
                exts = [exts]
            for ext in exts:
                if self.ext.get(ext.casefold(), False):
                    ret = True
            return ret

        def is_set_all(self, exts):
            c = 0
            if not isinstance(exts, list):
                exts = [exts]
            for ext in exts:
                if self.ext.get(ext.casefold(), False):
                    c += 1
            return c == len(exts)

        def is_set(self, ext):
            return self.ext.get(ext.casefold(), False)

        def get_enabled(self):
            return [ext for ext, val in self.ext.items() if val]

        def to_isa_str_raw(self, enabled_extensions):
            isa_str = ["", ""]
            for ext in enabled_extensions:
                if len(ext) == 1:
                    isa_str[0] += ext
                else:
                    if ext.startswith("z"):
                        isa_str[1] += "_" + ext
                    else:
                        raise Exception(
                            f"RVExtension: Invalid extension {ext} in given extension list"
                        )
            return "".join(map(str, isa_str))

        def to_isa_str(self):
            enabled_ext = [ext for ext, val in self.ext.items() if val]
            return f"rv{self.xlen}i" + self.to_isa_str_raw(enabled_ext)

        # used for spike
        def to_isa_str_alt(self):
            enabled_ext = [ext for ext, val in self.ext.items() if val]
            if self.is_set("v"):
                enabled_ext.remove("v")
                enabled_ext.append(f"zvl{self.vlen}b")
                enabled_ext.append(f"zve{self.velen}d")
            return f"rv{self.xlen}i" + self.to_isa_str_raw(enabled_ext)

        def __repr__(self):
            return (
                f"(extensions = {self.to_isa_str()}, flen = {self.flen}, fload_max = {self.fload_max}"
                + f"fstore_max = {self.fstore_max}, vlen = {self.vlen}, velen = {self.velen})"
            )

    def __init__(self, xlen=64, extensions_under_test=[], vlen=128, velen=64):
        self.ext_under_test = self.RVExtensions(xlen=xlen, vlen=vlen, velen=velen)
        self.ext_needed = self.RVExtensions(
            xlen=xlen, vlen=vlen, velen=velen
        )  # with dependencies
        self.set_ext(extensions_under_test)

    # apply extenions to "under_test" and "needed"
    def set_ext(self, exts):
        self.ext_under_test.set(exts)
        self.ext_needed.set(exts)

        # resolve dependencies in "needed"
        if self.ext_needed.is_set("v"):
            self.ext_needed.set("d")
            self.ext_needed.set("m")
        if self.ext_needed.is_set("q"):
            self.ext_needed.set("d")
        if self.ext_needed.is_set_any(["d", "zfh"]):
            self.ext_needed.set("f")
        # always needed (for instrumentation
        self.ext_needed.set("zicsr")
        self.ext_needed.set("zifencei")

    def get_xlen(self):
        return self.ext_needed.get_xlen()

    def get_flen(self):
        return self.ext_needed.get_flen()

    def get_fset_max(self):
        return self.ext_needed.get_fset_max()

    def get_fload_max(self):
        return self.ext_needed.get_fload_max()

    def get_fstore_max(self):
        return self.ext_needed.get_fstore_max()

    def get_vlen(self):
        return self.ext_needed.get_vlen()

    def get_velen(self):
        return self.ext_needed.get_velen()

    def is_under_test(self, ext):
        return self.ext_under_test.is_set(ext)

    def is_under_test_any(self, ext):
        return self.ext_under_test.is_set_any(ext)

    def is_under_test_all(self, ext):
        return self.ext_under_test.is_set_all(ext)

    def is_needed(self, ext):
        return self.ext_needed.is_set(ext)

    def is_needed_any(self, ext):
        return self.ext_needed.is_set_any(ext)

    def is_needed_all(self, ext):
        return self.ext_needed.is_set_all(ext)

    def get_under_test(self):
        return self.ext_under_test.get_enabled()

    def get_needed(self):
        return self.ext_needed.get_enabled()

    def is_float_needed(self):
        return self.is_needed_any(["zfh", "f", "d", "q"])

    def is_float_under_test(self):
        return self.is_under_test_any(["zfh", "f", "d", "q"])

    def to_isa_str(self):
        return self.ext_needed.to_isa_str()

    def to_isa_str_alt(self):
        return self.ext_needed.to_isa_str_alt()

    def __repr__(self):
        return f"(under_test = {self.ext_under_test}, needed = {self.ext_needed})"
