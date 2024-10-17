#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import ProcessTimeoutRunner, RunnerFile
from .MachineState import DumpFile, RegStateDump


class BuildRunner(ProcessTimeoutRunner):
    def setup(self, config):

        super().setup(config)

        stop_on_exception = config["stop_on_exception"]
        skip_on_exception = config["skip_on_exception"]
        xmemstart = config["xmemstart"]
        xmemlen = config["xmemlen"]
        rv_extensions = config["rv_extensions"]

        xlen = config["xlen"]
        self.xlenb = xlen // 8
        if xlen == 32:
            march = "rv32i" + rv_extensions
            mabi = "ilp32"
        elif xlen == 64:
            march = "rv64i" + rv_extensions
            mabi = "lp64"
        else:
            raise Exception(
                "xlen=" + str(xlen) + " not supported! Valid values are 32, or 64"
            )

        rv_extensions = config["rv_extensions"]
        has_float_single = "f" in rv_extensions
        has_float_double = "d" in rv_extensions
        has_float_quad = "q" in rv_extensions
        if has_float_quad:
            raise Exception("Quad-precision floating-point not supported yet!")
        has_float = has_float_single or has_float_double or has_float_quad

        has_vector = "v" in rv_extensions

        if self.log:
            self.codefile = RunnerFile(dir=self.get_dir(), name="code.S")
        self.asmfile = RunnerFile(dir=self.get_dir(), name="program.S")
        self.linkerscript = RunnerFile(
            dir=self.get_dir(),
            name="linker.lds",
            content='OUTPUT_ARCH( "riscv" )\n'
            + "MEMORY { MEM(rwx): org = "
            + hex(xmemstart)
            + ", len = "
            + hex(xmemlen - config["dumpfile_reserve"])
            + "}\n"
            + "SECTIONS {.text :  { *(.text) } > MEM }\n"
            + "ENTRY(_start)\n",
        )

        # dumpfile (temp regs, exception counter, last pc, ...)
        self.dumpfile = DumpFile(
            config=config, addr=xmemstart + xmemlen - config["dumpfile_reserve"]
        )

        # dump register file (only for setting - no store)
        self.regset = RegStateDump(config=config, reglist=[i for i in range(32)])

        # add asm header and program end code (for breakpoint)
        self.breakpoint = xmemstart + 4
        self.asmhdr = """
.globl _start
_start:         # @xmemstart
    # jump to real start
    j _begin
_stop:          # @xmemstart + 4 -> breakpoint
    # jump to real end
    j _end

# dummy HTIF symbols (needed for qemu)
tohost: .dword 0
.size tohost, 8
fromhost: .dword 0
.size fromhost, 8

_end:
    # reset tmpregstore (get clean memhash)
    csrrw gp, mscratch, gp
    li    t0, 0
    li    t1, 0
    li    t2, 0
"""
        self.asmhdr += self.dumpfile.tmpregstore.gen_save()

        self.asmhdr += "    # save/update state\n"
        # x5 and x6 already hold last pc and exc counter
        self.asmhdr += self.dumpfile.estate.gen_load()
        self.asmhdr += "    li   x9, 0x6600\n"
        self.asmhdr += "    csrr x7, mstatus\n"
        self.asmhdr += "    and  x7, x7, x9\n"
        self.asmhdr += self.dumpfile.estate.gen_save()

        if has_float:
            # float maybe disabled by test-code -> enable before reading state
            self.asmhdr += "    # enable and save float state\n"
            self.asmhdr += "    li   x5, 0x6000\n"
            self.asmhdr += "    csrs mstatus, x5\n"
            self.asmhdr += "    csrr x5, fcsr\n"
            self.asmhdr += self.dumpfile.fstate.gen_save()
            self.asmhdr += "    # save float registers\n"
            self.asmhdr += self.dumpfile.fregs.gen_save()

        if has_vector:
            # vector maybe disabled by test-code -> enable before reading state
            self.asmhdr += "    # enable and save vector state\n"
            self.asmhdr += "    li   x5, 0x600\n"
            self.asmhdr += "    csrs mstatus, x5\n"
            self.asmhdr += "    csrr x5, vtype\n"
            self.asmhdr += "    csrr x6, vl\n"
            self.asmhdr += "    csrr x7, vlenb\n"
            self.asmhdr += "    csrr x8, vstart\n"
            self.asmhdr += "    csrr x9, vxrm\n"
            self.asmhdr += "    csrr x10, vxsat\n"
            self.asmhdr += "    csrr x11, vcsr\n"
            self.asmhdr += self.dumpfile.vstate.gen_save()
            self.asmhdr += "    # save vector registers\n"
            self.asmhdr += self.dumpfile.vregs.gen_save()
        self.asmhdr += """

    # restore gp
    csrrw gp, mscratch, gp

    # loop
    j _stop      # jump to xmemstart + 4 (breakpoint)

_begin:
"""
        # set pointer to memory area of dumpfile data (mscratch)
        self.asmhdr += "    li gp, " + hex(self.dumpfile.get_addr()) + "\n"
        self.asmhdr += "    csrw mscratch, gp\n"

        # BEGIN: EXCEPTIONS
        if stop_on_exception or skip_on_exception:
            self.asmhdr += """
# Stop/Skip on exception
    # jump over exception handling code
    j _exc_end
    # exc vector
_exc_handler:
"""
            self.asmhdr += "    # save context\n"
            self.asmhdr += "    csrrw gp, mscratch, gp\n"
            self.asmhdr += self.dumpfile.tmpregstore.gen_save()

            self.asmhdr += "    # handle state (load all, modify, store all)\n"
            self.asmhdr += self.dumpfile.estate.gen_load()
            self.asmhdr += "    # save adress of last instruction (exception)\n"
            self.asmhdr += "    csrr x5, mepc\n"
            self.asmhdr += "    # increment exception counter\n"
            self.asmhdr += "    addi x6, x6, 1\n"
            self.asmhdr += self.dumpfile.estate.gen_save()

            if skip_on_exception:
                self.asmhdr += (
                    "    # skip on exception: modify mepc to next instruction (ra+4)\n"
                )
                self.asmhdr += "    addi x5, x5, 4\n"
                self.asmhdr += "    csrw mepc, x5\n"

            self.asmhdr += "    # restore context\n"
            self.asmhdr += self.dumpfile.tmpregstore.gen_load()
            self.asmhdr += "    csrrw gp, mscratch, gp\n"

            if skip_on_exception:
                self.asmhdr += """
    # skip on exception: jump back to next instruction (ra+4)
    mret
"""
            else:
                self.asmhdr += """
    # stop on exception: jump to end
    j _stop
"""
            self.asmhdr += """
_exc_end:
    # set vector to _vector (stop/skip on exc)
    la t0, _exc_handler
    csrw mtvec, t0
    # disable interrupt, timer, swint (exceptions only)
    # mie.MEIE=0, mie.MTIE=0, mie.MSIE=0
    li t0, 0x000
    csrw mie, t0
    # init state (exception counter, last exec pc)
"""
            self.asmhdr += self.dumpfile.estate.gen_set([0, 0, 0])
            self.asmhdr += self.dumpfile.estate.gen_save()
        # END: EXCEPTIONS

        self.asmhdr += "    # set mstatus (disabled ints, features)\n"
        self.asmhdr += "    li t0, 0\n"
        if has_float:
            self.asmhdr += "    # Enable floating point\n"
            self.asmhdr += "    li t1, 0x6000   // MSTATUS_FS\n"
            self.asmhdr += "    or t0, t0, t1\n"
        if has_vector:
            self.asmhdr += "    # Enable vector\n"
            self.asmhdr += "    li t1, 0x600    // MSTATUS_VS\n"
            self.asmhdr += "    or t0, t0, t1\n"
        self.asmhdr += "    csrw mstatus, t0\n"

        if has_float:
            self.asmhdr += "// init fp registers\n"
            if has_float_single:
                instr = "fcvt.s.w"
            if has_float_double:
                instr = "fcvt.d.w"
            if has_float_quad:
                instr = "fcvt.q.w"
            for i in range(0, 32):
                self.asmhdr += "    " + instr + " f" + str(i) + ", zero\n"

        if has_vector:
            self.asmhdr += """
    # Vector: reset vl to max
    vsetvli t0, zero, e8, ta, ma
"""

        # add register poison
        for i in range(1, 32):
            self.asmhdr += "    li x" + str(i) + ", " + str(i) + "\n"
        self.asmhdr += "\n# start of test code\n"

        # add end code
        self.asmtail = "_after_last_instr:\n"
        self.asmtail += "# end of test code\n\n"
        self.asmtail += "    # save context\n"
        self.asmtail += "    csrrw gp, mscratch, gp\n"
        self.asmtail += self.dumpfile.tmpregstore.gen_save()
        self.asmtail += "    # handle state (load all, modify, store all)\n"
        self.asmtail += self.dumpfile.estate.gen_load()
        self.asmtail += "    # update address of last instruction in test\n"
        self.asmtail += "    la   x5, _after_last_instr\n"
        self.asmtail += "    addi x5, x5, -4\n"
        self.asmtail += self.dumpfile.estate.gen_save()
        self.asmtail += "    # restore context\n"
        self.asmtail += self.dumpfile.tmpregstore.gen_load()
        self.asmtail += "    csrrw gp, mscratch, gp\n"
        self.asmtail += "    j _stop\n"

        # create command
        super().set_program(
            [
                config["gcc_bin"],
                self.asmfile.get_name(),
                "-o",
                config["binary"],
                "-march=" + march,
                "-mabi=" + mabi,
                "-nostartfiles",
                "-Wl,--no-relax",
                "-T",
                self.linkerscript.get_name(),
            ]
        )

    def get_breakpoint(self):
        return self.breakpoint

    def run_handler(self, code="", regstate=None, **kwargs):
        if self.log:
            self.codefile.set_content(code)
        if regstate is not None:
            code = self.regset.gen_set(regstate)
        code = self.asmhdr + "\n" + code + "\n" + self.asmtail
        self.asmfile.set_content(code)
        return super().run_handler(**kwargs)
