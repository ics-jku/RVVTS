# coding: utf-8

# (C) 2023-25 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
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

    archive_on_timeout = True,
    archive_on_ignore = True,
    archive_on_error = True,
    archive_on_complete = False,

    RefCovRunner_coverage = None,
    RISCVOVPSIMCover_extensions = "V",

    rv_extensions = "fdv",
    vector_elen = 64,

    memstart = memstart,
    memlen = memlen,
    xmemstart = memstart,
    xmemlen = memlen // 2,
    dmemstart = memstart + memlen // 2,
    dmemlen = memlen // 2,
)
