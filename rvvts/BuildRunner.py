#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
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
        rv_extensions = config["rv_extensions"] + "_zifencei"

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
        handle_exceptions = stop_on_exception or skip_on_exception
        self.breakpoint = xmemstart + 4

        # START CODE
        self.asmhdr = """
# START CODE
.globl _start
_start:         # @xmemstart
    # jump to real start
    j _begin
_stop:          # @xmemstart + 4 -> breakpoint
    # end of execution
    nop
    fence.i
    j _stop

# dummy HTIF symbols (needed for qemu)
tohost: .dword 0
.size tohost, 8
fromhost: .dword 0
.size fromhost, 8
"""

        # END CODE
        self.asmhdr += f"""
# END CODE (save state)
_end_of_exec:
    csrrw gp, mscratch, gp

    # save integer registers
{self.dumpfile.istate.gen_save(x3gp_in_mscratch = True)}\

    # reset tmpregstore (get clean memhash)
    li x5, 0 # t0
    li x6, 0 # t1
    li x7, 0 # t2
{self.dumpfile.tmpregstore.gen_save()}\

    # save/update state (x5 and x6 already hold last pc and exc counter)
    # (NOTE: last pc comes either from _after_last_instr or from stop_on_exception (see exception handler))
{self.dumpfile.estate.gen_load()}\
    li x9, 0x6600
    csrr x7, mstatus
    and x7, x7, x9
{self.dumpfile.estate.gen_save()}
"""

        if has_float:
            self.asmhdr += f"""\
    # save float state (maybe disabled by test code -> re-enable)
    li x5, 0x6000
    csrs mstatus, x5
    csrr x5, fcsr
{self.dumpfile.fstate.gen_save()}\
    # save float registers
{self.dumpfile.fregs.gen_save()}
"""

        if has_vector:
            self.asmhdr += f"""\
    # save vector state (maybe disabled by test code -> re-enable)
    li x5, 0x600
    csrs mstatus, x5
    csrr x5, vtype
    csrr x6, vl
    csrr x7, vlenb
    csrr x8, vstart
    csrr x9, vxrm
    csrr x10, vxsat
    csrr x11, vcsr
{self.dumpfile.vstate.gen_save()}\
    # save vector registers
{self.dumpfile.vregs.gen_save()}\
"""

        self.asmhdr += """
    # restore gp
    csrrw gp, mscratch, gp

    # loop
    j _stop      # jump to xmemstart + 8 (pre-breakpoint)
"""

        # EXCEPTIONS HANDLING CODE
        if handle_exceptions:
            self.asmhdr += f"""
    # EXCEPTION HANDLER (implements stop or skip&count)
_exc_handler:
    # save context
    csrrw gp, mscratch, gp
{self.dumpfile.tmpregstore.gen_save()}\

    # handle state (load all, modify, store all)
{self.dumpfile.estate.gen_load()}\
    # save adress of last instruction (exception)
    csrr x5, mepc
    # increment exception counter
    addi x6, x6, 1
{self.dumpfile.estate.gen_save()}\
"""
            if skip_on_exception:
                self.asmhdr += f"""
    # skip on exception: restore context and jump back to next instruction (ra+4)
    # TODO: handle compressed (ra+2)
    addi x5, x5, 4
    csrw mepc, x5
{self.dumpfile.tmpregstore.gen_load()}\
    csrrw gp, mscratch, gp
    mret
"""
            elif stop_on_exception:
                self.asmhdr += f"""
    # stop on exception: restore context and jump to stop
{self.dumpfile.tmpregstore.gen_load()}\
    csrrw gp, mscratch, gp
    j _end_of_exec
"""
            else:
                raise Exception(
                    "exception handling active, but no mode (skip or stop) defined"
                )

        # BEGIN CODE
        self.asmhdr += f"""
    # BEGIN CODE
_begin:
    # set pointer to memory area of dumpfile data (mscratch)
    li gp, {hex(self.dumpfile.get_addr())}
    csrw mscratch, gp
"""

        if handle_exceptions:
            self.asmhdr += f"""
    # setup exception handling
    # set vector to _exc_handler (stop/skip on exc)
    la t0, _exc_handler
    csrw mtvec, t0
    # disable interrupt, timer, swint (exceptions only)
    # mie.MEIE=0, mie.MTIE=0, mie.MSIE=0
    li t0, 0x000
    csrw mie, t0
    # init state (exception counter, last exec pc)
{self.dumpfile.estate.gen_set([0, 0, 0])}\
{self.dumpfile.estate.gen_save()}
"""

        mstatus_comment = "    # setup mstatus:\n"
        mstatus = 0
        if has_float:
            mstatus_comment += "    # - enable float (mstatus.fs, 0x6000)\n"
            mstatus |= 0x6000
        if has_vector:
            mstatus_comment += "    # - enable vector (mstatus.vs, 0x600)\n"
            mstatus |= 0x600
        self.asmhdr += f"""\
{mstatus_comment}\
    li t0, {hex(mstatus)}
    csrw mstatus, t0\n
"""

        if has_float:
            if has_float_single:
                instr = "fcvt.s.w"
            if has_float_double:
                instr = "fcvt.d.w"
            if has_float_quad:
                instr = "fcvt.q.w"
            self.asmhdr += "    # init float registers\n"
            for i in range(0, 32):
                self.asmhdr += "    " + instr + " f" + str(i) + ", zero\n"

        if has_vector:
            self.asmhdr += """
    # reset vector vl to max
    vsetvli t0, zero, e8, ta, ma\n
"""

        # add register poison
        self.asmhdr += "    # init integer registers\n"
        for i in range(1, 32):
            self.asmhdr += "    li x" + str(i) + ", " + str(i) + "\n"

        self.asmhdr += "\n# -------- START OF TEST CODE --------\n"

        # TAIL CODE (after test code)
        self.asmtail = f"""\
# -------- END OF TEST CODE --------
_after_last_instr:

    # STORE LAST PC
    # (Note: Might be set by stop_on_exception (see exception handler) -> can't be moved to _stop!)
    # save context
    csrrw gp, mscratch, gp
{self.dumpfile.tmpregstore.gen_save()}\
    # handle state (load all, modify, store all)
{self.dumpfile.estate.gen_load()}\
    # update address of last instruction in test
    la   x5, _after_last_instr
    addi x5, x5, -4
{self.dumpfile.estate.gen_save()}\
    # restore context
{self.dumpfile.tmpregstore.gen_load()}\
    csrrw gp, mscratch, gp
    j _end_of_exec
"""

        # CREATE COMMAND
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
