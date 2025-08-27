# RVVTS - The RISC-V Vector Test Framework (Version 2)

The **RVVTS Framework** is a modular, open-source framework designed for comprehensive testing of **RISC-V Vector (RVV)** implementations.
It addresses the complexity of RVV's 600+ configurable instructions by supporting both positive and negative testing scenarios.
The framework introduces a novel **Single Instruction Isolation with Code Minimization** technique, which drastically reduces manual effort required to analyze failing test cases.

**RVVTS** automates the entire verification process, from test generation and execution to coverage measurement and failure analysis.
By isolating failing instructions and minimizing the associated code, it streamlines debugging and helps detect bugs more efficiently.
The included pre-generated test sets achieve functional coverage of over 94% and have uncovered new bugs in RVV implementations of [RISC-V VP++](https://github.com/ics-jku/riscv-vp-plusplus) and [QEMU](https://www.qemu.org/).

The framework is implemented in Python and highly flexible.
It is suitable for both automated and interactive debugging workflows through its integration with Jupyter notebooks.

More information on RVVTS can be found in the publications linked in the [last section](#publications).



## Project Structure

```
├── README.md                                                ... This file
├── config_host.py                                           ... Host-related configurations (see Installation/Setup section!)
├── config_base.py                                           ... Internal configurations (modify only if you know what you are doing!)
├── FuzzCodeErrMinRunnerTests.ipynb                          ... Jupyter notebook demonstrating interactive and
                                                                 semi-automated testing -> Good starting point for experiments!
├── CovGuidedFuzzerGenRunnerTests.ipynb                      ... Jupyter notebook demonstrating test set generation
├── CovGuidedTestsetGenerator.ipynb                          ... Jupyter notebook demonstrating parallized test-set generation
                                                                 (e.g. directory "Testsets")
├── TestsetCodeErrMinRunnerTests.ipynb                       ... Jupyter notebook demonstrating execution of pre-generated
                                                                 test sets
├── LICENSE                                                  ... BSD 3-clause "New" or "Revised" License
├── DUTS                                                     ... Additional material for specific DUTs (patches, ...)
└── rvvts                                                    ... The core rvvts Python framework
```



## Installation/Setup

### Host System (Debian/Ubuntu)

It it recommended to install the following packages.
However, you can also follow the individual installation instructions of Spike, RISC-V VP++, QEMU and PULP Ara.

On Debian/Ubuntu:
```bash
sudo apt install cmake autoconf automake autotools-dev curl libmpc-dev libmpfr-dev libgmp-dev gawk build-essential bison flex texinfo libgoogle-perftools-dev libtool patchutils bc zlib1g-dev libexpat-dev libboost-iostreams-dev libboost-program-options-dev libboost-log-dev qtbase5-dev qt5-qmake libvncserver-dev device-tree-compiler
```


### Python

RVVTS needs at least Python version 3.11.

Example of setup a new Python 3.11 in conda

 1. Install Miniconda
    * see https://engineeringfordatascience.com/posts/install_miniconda_from_the_command_line/
    * Re-start terminal after installation
 2. Setup environment
    ```
    conda create --name python_rvvts python=3.11
    ```
 3. Enable environment
    ```
    conda activate python_rvvts
    ```


RVVTS dependencies on python packages can be installed with
```
pip install numpy jsonpickle jupyter
```


### Spike Simulator (Mandatory)

The [Spike simulator](https://github.com/riscv-software-src/riscv-isa-sim) is used as golden model for execution comparison by RVVTS and therefore mandatory.

***Note: The oldest spike version supported is git hash 0408e797b139dbc1aaa52cb33dea047ad8d230ad (June 20, 2024)*** \
Versions older than this use different parameters for the vector extension (vlen, elen) which are not longer supported by RVVTS.

 1. Clone the Spike repository and enter the directory
    ```
    git clone https://github.com/riscv-software-src/riscv-isa-sim.git
    cd riscv-isa-sim
    ```
 2. Optional: Select a specific Spike version (>= git hash 0408e797b139dbc1aaa52cb33dea047ad8d230ad - see above)
    ```
    git checkout 1553a2a89699ccfbbccc3dc2dfc0815151b5694a
    ```
 3. Build
    ```
    ./configure
    make -j$(nproc)
    ```
    You should now have a executable file ```spike``` in this directory.
 4. Update ```spike_bin``` in ```config_host.py```. Use the absolute path to the created ```spike``` executable


More detailed build instructions can be found in the documentation of the Spike simulator.



### RISC-V GNU Cross-compilation Toolchain (Mandatory)

The [riscv-gnu-toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain) is used by RVVTS (i) to translat generated or loaded code fragments to executable RISC-V programs (GCC), and (ii) to control execution and extract machine states (GDB).

 1. Clone the RISC-V GNU Toolchain and enter the directory
    ```
    git clone https://github.com/riscv-collab/riscv-gnu-toolchain.git
    cd riscv-gnu-toolchain
    ```
 2. Select a specific toolchain version \
    Development of RVVTS was mostly done on git tag: 2024.09.03
    Most recent tested version is git tag: 2024.09.03
    ```
    git checkout 2024.09.03
    ```
 3. Build (in local directory)
    ```
    ./configure --prefix=$(pwd)
    make newlib -j$(nproc)
    ```
    You should now have the executable files ```riscv64-unknown-elf-gcc``` and ```riscv64-unknown-elf-gdb``` in directory ```bin```.
 4. Update ```gcc_bin``` and ```gdb_bin``` in ```config_host.py```. Use the absolute paths to the created ```riscv64-unknown-elf-gcc``` and ```riscv64-unknown-elf-gdb``` executables


More detailed build instructions can be found in the documentation of the RISC-V GNU toolchain.



### RISC-V riscvOVPsim reference simulator (Optional)

The [riscvOVPsim](https://github.com/riscv-ovpsim/imperas-riscv-tests) simulator is optionally used by RVVTS to obtain functional coverage values.

riscvOVPsim is free but not open source.
Binaries are distributed via via github: https://github.com/riscv-ovpsim/imperas-riscv-tests.

***Note: At time of writing, there are no working versions of riscvOVPsim available!*** \
The distributed binaries are locked via a date check and the repo was not updated with new versions for some time now.

 1. Clone riscvOVPsim
    ```
    git clone https://github.com/riscv-ovpsim/imperas-riscv-tests.git
    cd imperas-riscv-tests
    ```
    You should now have the executable file ```riscvOVPsim.exe``` in directory ```riscv-ovpsim/bin/Linux64```.
 2. Update ```riscvovpsim_bin``` in ```config_host.py```. Use the absolute path to the ```riscvOVPsim.exe``` executable



### RISC-V VP++ (Optional)

[RISC-V VP++](https://github.com/ics-jku/riscv-vp-plusplus) is a open-source, SystemC based RISC-V Virtual Prototype with support for RISC-V Vector, and is one of the DuTs currently supported by RVVTS.

 1. Clone RISC-V VP++ and enter the directory
    ```
    git clone https://github.com/ics-jku/riscv-vp-plusplus.git
    cd riscv-vp-plusplus
    ```
 2. Optional: Select a specific version
    ```
    git checkout ...
    ```
 3. Build
    ```
    make vps -j$(nproc)
    ```
    You should now have the executable files ```tiny32-vp``` and ```tiny64-vp``` in directory ```vp/build/bin```.
 4. Update ```vp_path``` in ```config_host.py```. Use the absolute paths to ```vp/build/bin```


More detailed build instructions can be found in the documentation of the RISC-V GNU toolchain.



### QEMU (Optional)

[QEMU](https://www.qemu.org) is a open-source emulator with support for RISC-V and RISC-V Vector, and is one of the DuTs currently supported by RVVTS.

 1. Clone QEMU and enter the directory
    ```
    git clone https://github.com/qemu/qemu.git
    cd qemu
    ```
 2. Optional: Select a specific qemu version
    ```
    git checkout v9.1.0
    ```
 3. Build (in local directory)
    ```
    ./configure --target-list=riscv32-softmmu,riscv64-softmmu
    make -j$(nproc)
    ```
    You should now have the executable files ```qemu-system-riscv32``` and ```qemu-system-riscv64``` in directory ```build```.
 4. Update ```qemu_path``` in ```config_host.py```. Use the absolute paths to ```build```



### PULP Ara (Optional)
[PULP Ara](https://github.com/pulp-platform/ara) is an open-source, 64-bit RTL implementation of a RISC-V vector unit. Developed as part of the PULP platform, it operates as a coprocessor for the CVA6 scalar core and supports version 1.0 of the RISC-V Vector Extension.

 1. Clone Ara and enter the directory
    ```
    git clone https://github.com/pulp-platform/ara.git
    cd ara
    ```
 2. Optional: Select a specific qemu version
    Tested with a6436df6ad and ab4158aeeb
    ```
    git checkout ab4158aeeb
    ```
 3. Apply the RVVTS DUT Patch located in ```DUTS/PULP_ARA/ara_rvvts_dut_v1.patch```
    (v1 compatible with a6436df6ad and ab4158aeeb)
    ```
    git am <rvvts>/DUTS/PULP_ARA/ara_rvvts_dut_v1.patch
    ```
 4. Build the verilated Ara model following the original build instruction (README.md)
    Result: ```<ara>/hardware/build/verilator/Vara_tb_verilator```
 5. Update ```ara_tb_bin``` in ```config_host.py``` accordingly.



## First Steps

After Install/Setup:
 1. Switch to the RVVTS top-directory
 2. If necessary, activate your virtual Python environment \
    e.g. conda
    ```
    conda activate python_rvvts
    ```
 3. Start Jupyter Lab
    ```
    jupyter lab
    ```
Your browser should now be open and display Jupyter lab and the project structure as presented in section [Project Structure](#project-structure).

A good starting point for experiments is ```FuzzCodeErrMinRunnerTests.ipynb```:
 1. Select your prefered ```dut``` and ```xlen``` in the config cell
 2. Run the notebook cell-by-cell
    * "First Test": Generates a single random program, executes it on the reference simulator and dut and shows a machine state difference report.
      * If a deviation in the machine state is detected (potential fail) you can examine the minimized program causing the deviation by uncommenting the lines in the following cell.
    * "Manual Experiments": Enter your own program to be executed and compared.
    * "Automated Experiments": Automated runs of "First Test". Detailed statistics and failing instructions are shown live while the execution is running.

You can now investigate the other Jupyter notebooks as presented in section [Project Structure](#project-structure).



## Publications

The initial paper on RVVTS was presented at ICCAD'24 and can be downloaded here: https://ics.jku.at/files/2024ICCAD_Single-Instruction-Isolation-for-RISC-V-Vector-Test-Failures.pdf

The state of RVVTS from the initial paper (RVVTS version 1), including the pre-generated test sets, is available under the tag [RVVTSv1_ICCAD_2024](https://github.com/ics-jku/RVVTS/tree/RVVTSv1_ICCAD_2024)

If you like RVVTS or found it useful, you can cite our paper as follows:

```
@inproceedings{SG:2024b,
  author =        {Manfred Schl{\"{a}}gl and Daniel Gro{\ss}e},
  booktitle =     {International Conference on Computer-Aided Design},
  title =         {Single Instruction Isolation for {RISC-V} Vector Test Failures},
  year =          {2024},
}
```

A related publication discusses the realisation of bounded vector load/stores by extending context-free grammars with functions to generate elements in a context-sensitive way.
This publication is available here: https://ics.jku.at/files/2024RISCVSummit_BoundedLoadStoreGrammarTestRVV.pdf
