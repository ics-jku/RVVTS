# coding: utf-8

# (C) 2023-25 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License

# Global host specific configuration for RVVTS

config = dict(
    # GCC binary
    # Mandatoryifor RISC-V builds
    gcc_bin = "/opt/riscv-gnu-toolchain-multi-2024.09.03/bin/riscv32-unknown-elf-gcc",

    # GNU Debugger binary
    # Mandatory for state extraction from RISC-V VP++, QEMU, ...
    gdb_bin = "/opt/riscv-gnu-toolchain-multi-2024.09.03/bin/riscv32-unknown-elf-gdb",

    # sail-riscv binary
    sail_riscv_bin = "/srv/ext/TOOLS/sail-riscv-rvvtsdut_20260216/build/c_emulator/sail_riscv_sim",

    # Spike simulator binary
    # Mandatory for reference simulation
    #spike_bin = "/opt/spike/spike",
    #spike_bin = "/opt/spike_20250805/spike",
    spike_bin = "/srv/ext/TOOLS/riscv-isa-sim_20250806/spike",

    # RISCVOVPSim binary
    # Optional (Coverage measurement)
    riscvovpsim_bin = "/opt/imperas-riscv-tests/riscv-ovpsim/bin/Linux64/riscvOVPsim.exe",

    # Path to RISC-V VP++ binaries
    # Optional (VP tests)
    vp_path = "/srv/ext/GUI-VP_KITS/GUI-VP_Kit/riscv-vp-plusplus/vp/build/bin",

    # Path to verilated ARA testbench
    #ara_tb_bin = "/srv/ext/RVVTS/PULP_ARA/ara_jonas/hardware/build/verilator/Vara_tb_verilator",
    #ara_tb_bin = "/srv/ext/RVVTS/PULP_ARA/ara_jonas/hardware/build/verilator/Vara_tb_verilator_512KiB",
    #ara_tb_bin = "/srv/ext/RVVTS/202508_PULP_ARA/ara_20250320_patched_built/hardware/build/verilator/Vara_tb_verilator",
    ara_tb_bin = "/srv/ext/RVVTS/202508_PULP_ARA/ara_20250805_patched_built/hardware/build/verilator/Vara_tb_verilator",

    # Path to QEMU binaries
    # Optional (QEMU tests)
    qemu_path = "/opt/qemu",
)
