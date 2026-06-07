# coding: utf-8

# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License

# Global base configuration for RVVTS
# (Overrride in custom config; only change if you know what you are doing!)

memstart = 0x80000000 # compatible with spike, qemu, riscv-vp++ and ara
#memlen = 512*1024 # 512KiB
memlen = 3*1024*1024 # 3MiB

config = dict(
    log = True,
    build_ignore_error = True,
    stop_on_exception = False,
    skip_on_exception = True,
    # reserve 10KiB in xmem for dumpfile (TODO: automate calculation)
    #dumpfile_reserve = 10*1024,
    # reserve 20KiB in xmem for dumpfile (TODO: automate calculation) NEEDED FOR VLEN=4096 ((0x00300000/2)-0x0017f180 = 3712KiB reserve)
    dumpfile_reserve = 20*1024,

    # EXPERIMENTAL: ENABLING THIS MAKES NOT MUCH SENSE YET!
    CovGuidedFuzzerGen_allow_exceptions = False,

    # only show differences in machine state diff
    CompareRunner_mstate_diff_full = False,

    # keep memory dumps (consumes significant amount of harddrive space)
    DumpFile_keep_dumpfile = False,

    # ARA may hang on test case execution (running clock, but no instructions retired)
    # with this we can control, whether we count such cases as TIMEOUT or ERROR (with lastPC-1)
    # (handling it as error makes it possible to minimize the case with CodeErrMinRunner, but
    # may hide the hang cases)
    AraRunner_count_hang_as_error = True,

    # vcsr is not writable with other values than 0 on ARA (register is always 0)
    # With this we enable a quirk in ISG which prevents generation of
    # code that sets vcsr to other values than 0
    quirk_ara_csrs = False,

    # <32 bit loads between [0x10:0x17] fail on sail-riscv with exception
    # Seems also to affect stores, but rvvts does not generate stores do not write in xmem (would overwrite program)
    # TODO: adresses match the tohost and fromhost symbols (see objdump)
    # TODO: most cases could not be state minimized -> but manually possible -> WHY?!
    # QUIRK: set this value to 0x20 if sail is used as reference or dut
    quirk_sail_load_offset = 0x20,

    archive_on_timeout = True,
    archive_on_ignore = True,
    archive_on_error = True,
    archive_on_complete = False,

    # Default Reference Runner -> NOTE: has to be set!
    RefCovRunner_ref = None,

    # Ignore sequences (test-cases) that cause an exception in the reference (i.e. invalid sequences)
    # Enabling this allows pure positive testing.
    RefCovRunner_ignore_invalid_sequences = False,

    RefCovRunner_coverage = None,
    RISCVOVPSIMCover_extensions = "V",

    rv_extensions = "mfdv",
    vector_elen = 64,

    memstart = memstart,
    memlen = memlen,
    xmemstart = memstart,
    xmemlen = memlen // 2,
    dmemstart = memstart + memlen // 2,
    dmemlen = memlen // 2,
)
