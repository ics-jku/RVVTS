# RVVTS - The RISC-V Vector Test Framework (V2)

The **RVVTS Framework** is a modular, open-source framework designed for comprehensive testing of **RISC-V Vector (RVV)** implementations.
It addresses the complexity of RVV's 600+ configurable instructions by supporting both positive and negative testing scenarios.
The framework introduces the **Single Instruction Isolation with Code Minimization** and **Automated Failure Categorization (AFC)** techniques, which drastically reduce manual effort required to analyze failing test cases.

**RVVTS** automates the entire verification process, from test generation and execution to coverage measurement and failure analysis.
By isolating failing instructions and minimizing the associated code, it streamlines debugging and helps detect bugs more efficiently.
The framwork uncovered bugs in RVV implementations of [PULP Ara](https://github.com/pulp-platform/ara/) ([reports](https://github.com/ics-jku/RVVTS_RTL_AFC_Ara)), [Sail-RISC-V](https://github.com/riscv/sail-riscv) ([reports](https://github.com/ics-jku/RVVTS_SailRV_Spike)), [RISC-V VP++](https://github.com/ics-jku/riscv-vp-plusplus), [QEMU](https://www.qemu.org/)

The framework is implemented in Python and is highly flexible.
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
├── CovGuidedTestsetGenerator.ipynb                          ... Jupyter notebook demonstrating parallelized test-set generation
                                                                 (e.g. directory "Testsets")
├── TestsetCodeErrMinRunnerTests.ipynb                       ... Jupyter notebook demonstrating execution of pre-generated
                                                                 test sets
├── LICENSE                                                  ... BSD 3-clause "New" or "Revised" License
├── DUTS                                                     ... Additional material for specific DUTs (patches, ...)
└── rvvts                                                    ... The core rvvts Python framework
```



## Installation/Setup

### Host System (Debian/Ubuntu)

It is recommended to install the following packages.
However, you can also follow the individual installation instructions of Spike, RISC-V VP++, QEMU, and PULP Ara.

On Debian/Ubuntu:
```bash
sudo apt install cmake autoconf automake autotools-dev clang-format-19 curl libmpc-dev libmpfr-dev libgmp-dev gawk build-essential bison flex texinfo libgoogle-perftools-dev libtool patchutils bc zlib1g-dev libexpat-dev libboost-iostreams-dev libboost-program-options-dev libboost-log-dev qtbase5-dev qt5-qmake libvncserver-dev device-tree-compiler nlohmann-json3-dev help2man libfl-dev perl
```


### Python

RVVTS needs at least Python version 3.11.

Example setup for a new Python 3.11 Conda environment:

 1. Install Miniconda
    * See https://engineeringfordatascience.com/posts/install_miniconda_from_the_command_line/
    * Restart the terminal after installation
 2. Set up the environment
    ```
    conda create --name python_rvvts python=3.11
    ```
 3. Activate the environment
    ```
    conda activate python_rvvts
    ```


The Python packages required by RVVTS can be installed with:
```
pip install numpy jsonpickle jupyter
```



### RISC-V GNU Cross-compilation Toolchain (Mandatory)

The [riscv-gnu-toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain) is used by RVVTS (i) to translate generated or loaded code fragments into executable RISC-V programs (GCC), and (ii) to control execution and extract machine states (GDB).

 1. Clone the RISC-V GNU Toolchain and enter the directory
    ```
    git clone https://github.com/riscv-collab/riscv-gnu-toolchain.git
    cd riscv-gnu-toolchain
    ```
 2. Select a specific toolchain version (e.g., 2026.06.06)
    ```
    git checkout 2026.06.06
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
Binaries are distributed via GitHub: https://github.com/riscv-ovpsim/imperas-riscv-tests.

***Note: At the time of writing, there are no working versions of riscvOVPsim available!*** \
The distributed binaries are locked via a date check and the repository has not been updated with new versions for some time now.

 1. Clone riscvOVPsim
    ```
    git clone https://github.com/riscv-ovpsim/imperas-riscv-tests.git
    cd imperas-riscv-tests
    ```
    You should now have the executable file ```riscvOVPsim.exe``` in directory ```riscv-ovpsim/bin/Linux64```.
 2. Update ```riscvovpsim_bin``` in ```config_host.py```. Use the absolute path to the ```riscvOVPsim.exe``` executable



### Spike Simulator (Mandatory)

The [Spike simulator](https://github.com/riscv-software-src/riscv-isa-sim) is used as a golden model for execution comparison by RVVTS and is therefore mandatory.

 1. Clone the Spike repository and enter the directory
    ```
    git clone https://github.com/riscv-software-src/riscv-isa-sim.git
    cd riscv-isa-sim
    ```
 2. Optional: Select a specific Spike version
    ```
    git checkout ...
    ```
 3. Build
    ```
    ./configure
    make -j$(nproc)
    ```
    You should now have an executable file ```spike``` in this directory.
 4. Update ```spike_bin``` in ```config_host.py```. Use the absolute path to the created ```spike``` executable


More detailed build instructions can be found in the documentation of the Spike simulator.



### SAIL-RISC-V (Optional)

[SAIL-RISC-V](https://github.com/riscv/sail-riscv) is an open-source executable formal model of the RISC-V ISA. RVVTS can use its C emulator as a reference model or as one of the DUTs currently supported by RVVTS.

 1. Clone SAIL-RISC-V and enter the directory
    ```
    git clone https://github.com/riscv/sail-riscv.git
    cd sail-riscv
    ```
 2. Select the tested SAIL-RISC-V version
    Tested with a33475aeb80090127433b5a8b30e717edaa19e71 (tag 2026-02-16-a33475a / 0.10)
    ```
    git checkout a33475aeb80090127433b5a8b30e717edaa19e71
    ```
 3. Apply the RVVTS DUT Patch located in ```DUTS/SAIL-RISC-V/sailrv_rvvts_dut_v1.patch```
    (v1 compatible with a33475aeb80090127433b5a8b30e717edaa19e71)
    ```
    git am <rvvts>/DUTS/SAIL-RISC-V/sailrv_rvvts_dut_v1.patch
    ```
 4. Build the C emulator
    ```
    ./build_simulator.sh
    ```
    You should now have the executable file ```sail_riscv_sim``` in directory ```build/c_emulator```.
 5. Update ```sail_riscv_bin``` in ```config_host.py```. Use the absolute path to ```build/c_emulator/sail_riscv_sim```



### RISC-V VP++ (Optional)

[RISC-V VP++](https://github.com/ics-jku/riscv-vp-plusplus) is an open-source, SystemC-based RISC-V virtual prototype with support for RISC-V Vector, and is one of the DUTs currently supported by RVVTS.

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
 4. Update ```vp_path``` in ```config_host.py```. Use the absolute path to ```vp/build/bin```


More detailed build instructions can be found in the documentation of RISC-V VP++.



### QEMU (Optional)

[QEMU](https://www.qemu.org) is an open-source emulator with support for RISC-V and RISC-V Vector, and is one of the DUTs currently supported by RVVTS.

 1. Clone QEMU and enter the directory
    ```
    git clone https://github.com/qemu/qemu.git
    cd qemu
    ```
 2. Optional: Select a specific QEMU version
    ```
    git checkout ...
    ```
 3. Build (in local directory)
    ```
    ./configure --target-list=riscv32-softmmu,riscv64-softmmu
    make -j$(nproc)
    ```
    You should now have the executable files ```qemu-system-riscv32``` and ```qemu-system-riscv64``` in directory ```build```.
 4. Update ```qemu_path``` in ```config_host.py```. Use the absolute path to ```build```



### PULP Ara (Optional)
[PULP Ara](https://github.com/pulp-platform/ara) is an open-source, 64-bit RTL implementation of a RISC-V vector unit. Developed as part of the PULP platform, it operates as a coprocessor for the CVA6 scalar core and supports version 1.0 of the RISC-V Vector Extension.

 1. Clone Ara and enter the directory
    ```
    git clone https://github.com/pulp-platform/ara.git
    cd ara
    ```
 2. Optional: Select a specific Ara version
    Tested with a6436df6ad and ab4158aeeb
    ```
    git checkout ab4158aeeb
    ```
 3. Apply the RVVTS DUT Patch located in ```DUTS/PULP_ARA/ara_rvvts_dut_v1.patch```
    (v1 compatible with a6436df6ad and ab4158aeeb)
    ```
    git am <rvvts>/DUTS/PULP_ARA/ara_rvvts_dut_v1.patch
    ```
 4. Build the verilated Ara model following the original build instructions (README.md)
    Result: ```<ara>/hardware/build/verilator/Vara_tb_verilator```
 5. Update ```ara_tb_bin``` in ```config_host.py``` accordingly.



## First Steps

After installation/setup:
 1. Switch to the RVVTS top-level directory
 2. If necessary, activate your virtual Python environment \
    e.g. conda
    ```
    conda activate python_rvvts
    ```
 3. Start Jupyter Lab
    ```
    jupyter lab
    ```
Your browser should now be open and display Jupyter Lab and the project structure as presented in the [Project Structure](#project-structure) section.

A good starting point for experiments is ```FuzzCodeErrMinRunnerTests.ipynb```:
 1. Select your preferred ```dut``` and ```xlen``` in the config cell
 2. Run the notebook cell-by-cell
    * "First Test": Generates a single random program, executes it on the reference simulator and DUT and shows a machine state difference report.
      * If a deviation in the machine state is detected (potential failure) you can examine the minimized program causing the deviation by uncommenting the lines in the following cell.
    * "Manual Experiments": Enter your own program to be executed and compared.
    * "Automated Experiments": Automated runs of "First Test". Detailed statistics and failing instructions are shown live while the execution is running.

You can now investigate the other Jupyter notebooks as presented in the [Project Structure](#project-structure) section.



## Publications

The initial paper on RVVTS was presented at ICCAD 2024 and is available as a [.pdf](https://ics.jku.at/files/2024ICCAD_Single-Instruction-Isolation-for-RISC-V-Vector-Test-Failures.pdf).

The state of RVVTS from the initial paper (RVVTS version 1), including the pre-generated test sets, is available under the tag [RVVTSv1_ICCAD_2024](https://github.com/ics-jku/RVVTS/tree/RVVTSv1_ICCAD_2024).

If you use RVVTS or find it useful, you can cite our paper as follows:

```
@inproceedings{SG:2024b,
  author =        {Manfred Schl{\"{a}}gl and Daniel Gro{\ss}e},
  booktitle =     {International Conference on Computer-Aided Design},
  title =         {Single Instruction Isolation for {RISC-V} Vector Test Failures},
  year =          {2024},
}
```

### All RVVTS related publications

* **GLSVLSI 2026**

  Manfred Schlägl, Jonas Reichhardt, and Daniel Große. From generation to failure categorization: An open-source automated RTL verification framework for RVV. In ACM Great Lakes Symposium on VLSI (GLSVLSI), 2026.

  Extends RVVTS with RTL support and an Automated Failure Categorization stage. Applied to the RTL implementation of Ara, the framework achieves more than 96% functional coverage, minimizes about 97% of the detected deviations, and groups failures into 16 categories.

  [[bib](https://ics.jku.at/bibliography/manfred_schlaegl/#SRG:2026b) | [DOI](https://doi.org/10.1145/3787109.3815255) | [material](https://github.com/ics-jku/RVVTS_RTL_AFC_Ara) | [.pdf](https://ics.jku.at/files/2026GLSVLSI_From_Generation_to_Failure_Categorization_An_Open-Source_automated_RTL_Verification_Framework_for_RVV.pdf)]

* **RISC-V Summit Europe 2026**

  Manfred Schlägl, Katharina Ruep, and Daniel Große. Sail-RISC-V and Spike for RISC-V vector: Toward consistent golden reference behavior. In RISC-V Summit Europe, 2026.

  Uses RVVTS to compare the RVV behavior of Sail-RISC-V and Spike. Positive tests show only 0.23% deviations, whereas negative tests reveal 3.73%, highlighting issues in Sail-RISC-V instruction-validity checks under dynamic configurations.

  [[bib](https://ics.jku.at/bibliography/manfred_schlaegl/#SRG:2026) | [material](https://github.com/ics-jku/RVVTS_SailRV_Spike) | [.pdf](https://ics.jku.at/files/2026RISC-V_Summit_Europe_RVVTS_SailRV_Spike.pdf)]

* **DATE 2026**

  Katharina Ruep, Manfred Schlägl, and Daniel Große. Late breaking results: Float fight – verifying floating-point behavior in RISC-V simulators. In Design, Automation and Test in Europe Conference (DATE), pages 1–3, 2026.

  Introduces FP-RVVTS, an RVVTS extension for floating-point verification. It adds support for the RISC-V F, D, and Zfh extensions, improves failure isolation, achieves more than 95% functional coverage, and exposes bugs in several simulators and floating-point libraries.

  [[bib](https://ics.jku.at/bibliography/manfred_schlaegl/#RSG:2026) | [DOI](https://doi.org/10.23919/DATE69613.2026.11539613) | [base RVVTS material](https://github.com/ics-jku/RVVTS) | [.pdf](https://ics.jku.at/files/2026DATE_LBR_Float_Fight-Verifying_Floating-Point_Behavior_in_RISC-V_Simulators.pdf)]

* **MBMV 2025**

  Manfred Schlägl and Daniel Große. RVVTS: A modular, open-source framework for positive and negative testing of the RISC-V “V” vector extension (RVV). In ITG/GI/GMM-Workshop “Methoden und Beschreibungssprachen zur Modellierung und Verifikation von Schaltungen und Systemen” (MBMV), 2025.

  Summarizes the RVVTS framework: grammar-based and coverage-guided test generation, positive and negative testing, automated execution, and Single Instruction Isolation with Code Minimization. The case studies confirm bugs in RISC-V VP++ and QEMU.

  [[bib](https://ics.jku.at/bibliography/manfred_schlaegl/#SG:2025b) | [material](https://github.com/ics-jku/RVVTS) | [.pdf](https://ics.jku.at/files/2025MBMV_RVVTS.pdf)]

* **ICCAD 2024**

  Manfred Schlägl and Daniel Große. Single instruction isolation for RISC-V vector test failures. In IEEE/ACM International Conference on Computer-Aided Design (ICCAD), pages 156:1–156:9, 2024.

  Introduces RVVTS as a modular open-source framework for positive and negative RVV testing. Its Single Instruction Isolation with Code Minimization technique reduces large sets of detected deviations to compact debugging cases while achieving more than 94% functional coverage.

  [[bib](https://ics.jku.at/bibliography/manfred_schlaegl/#SG:2024b) | [DOI](https://doi.org/10.1145/3676536.3676755) | [material](https://github.com/ics-jku/RVVTS) | [.pdf](https://ics.jku.at/files/2024ICCAD_Single-Instruction-Isolation-for-RISC-V-Vector-Test-Failures.pdf)]

* **RISC-V Summit Europe 2024**

  Manfred Schlägl and Daniel Große. Bounded load/stores in grammar-based code generation for testing the RISC-V vector extension. In RISC-V Summit Europe, 2024.

  Presents a precursor to RVVTS: a grammar-based fuzzing approach for RVV testing. The paper focuses on generating valid vector load/store sequences by extending a context-free grammar with functions that add context-sensitive behavior.

  [[bib](https://ics.jku.at/bibliography/manfred_schlaegl/#SG:2024) | [material](https://github.com/ics-jku/RVVTS) | [.pdf](https://ics.jku.at/files/2024RISCVSummit_BoundedLoadStoreGrammarTestRVV.pdf)]
