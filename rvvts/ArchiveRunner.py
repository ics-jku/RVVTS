#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import Runner, RunnerOutcome, RunnerFile

import shutil


class ArchiveRunner(Runner):
    def setup(self, config):

        super().setup(config)

        subconfig = config.copy()
        subconfig["dir"] = self.get_dir()

        if self.log:
            self.statfile = RunnerFile(dir=self.get_dir(), name="stats.log")
        self.ArchiveRunner_dut = config["ArchiveRunner_dut"](subconfig)
        self.archive_on_timeout = config["archive_on_timeout"]
        self.archive_on_ignore = config["archive_on_ignore"]
        self.archive_on_error = config["archive_on_error"]
        self.archive_on_complete = config["archive_on_complete"]
        self.iteration = 0
        self.timeouts = 0
        self.ignores = 0
        self.errors = 0
        self.completes = 0
        self.runkwargs = None

    def task(self):
        return self.ArchiveRunner_dut.run(blocking=True, **self.runkwargs)

    def task_post(self, ret):
        archivedir = None

        if ret[0] == RunnerOutcome.TIMEOUT:
            self.timeouts += 1
            if self.archive_on_timeout:
                archivedir = (
                    self.get_dir() + "/TIMEOUT_iteration_" + f"{self.iteration :010d}"
                )
        elif ret[0] == RunnerOutcome.IGNORE:
            self.ignores += 1
            if self.archive_on_ignore:
                archivedir = (
                    self.get_dir() + "/IGNORE_iteration_" + f"{self.iteration :010d}"
                )
        elif ret[0] == RunnerOutcome.ERROR:
            self.errors += 1
            if self.archive_on_error:
                archivedir = (
                    self.get_dir()
                    + "/ERROR_"
                    + self.ArchiveRunner_dut.get_error_cause()
                    + "_iteration_"
                    + f"{self.iteration :010d}"
                )
        elif ret[0] == RunnerOutcome.COMPLETE:
            self.completes += 1
            if self.archive_on_complete:
                archivedir = (
                    self.get_dir() + "/COMPLETE_iteration_" + f"{self.iteration :010d}"
                )

        if archivedir is not None:
            shutil.copytree(self.ArchiveRunner_dut.get_dir(), archivedir)

        self.iteration += 1

        if self.log:
            stats = ""
            stats += "iterations: " + str(self.iteration)
            stats += "\nignores: " + str(self.ignores)
            stats += "\nerrors: " + str(self.errors)
            stats += "\ncompletes: " + str(self.completes)
            stats += "\n"
            self.statfile.set_content(stats)

        return ret

    def run_handler(self, blocking, **kwargs):
        self.runkwargs = kwargs
        return super().run_handler(blocking=blocking, **kwargs)
