# coding: utf-8

# (C) 2023-26 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License

# Global host specific configuration for RVVTS

config = dict(
    # GCC binary
    # Mandatory for RISC-V builds
    gcc_bin = "/opt/riscv-gnu-toolchain-multi-2024.09.03/bin/riscv32-unknown-elf-gcc",

    # GNU Debugger binary
    # Mandatory for state extraction for RISC-V VP++ and QEMU
    gdb_bin = "/opt/riscv-gnu-toolchain-multi-2024.09.03/bin/riscv32-unknown-elf-gdb",

    # RISCVOVPSim binary
    # Optional (Coverage measurement)
    riscvovpsim_bin = "/opt/imperas-riscv-tests/riscv-ovpsim/bin/Linux64/riscvOVPsim.exe",

    # sail-riscv binary
    # Mandatory when used as reference or DuT
    sail_riscv_bin = "/srv/ext/TOOLS/sail-riscv-rvvtsdut_20260216/build/c_emulator/sail_riscv_sim",

    # Spike simulator binary
    # Mandatory when used as reference or DuT
    spike_bin = "/srv/ext/TOOLS/riscv-isa-sim_20250806/spike",

    # Path to RISC-V VP++ binaries
    # Mandatory when used as reference or DuT
    vp_path = "/srv/ext/GUI-VP_KITS/GUI-VP_Kit/riscv-vp-plusplus/vp/build/bin",

    # Path to verilated ARA testbench binary
    # Mandatory when used as reference or DuT
    ara_tb_bin = "/srv/ext/RVVTS/202508_PULP_ARA/ara_20250805_patched_built/hardware/build/verilator/Vara_tb_verilator",

    # Path to QEMU binaries
    # Mandatory when used as reference or DuT
    qemu_path = "/opt/qemu",
)
