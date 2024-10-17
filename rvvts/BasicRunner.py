#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from enum import Enum

import os
import time
import signal
import subprocess
import threading


class RunnerFile:
    def __init__(self, dir=os.getcwd(), name="file", content=""):

        self.dir = dir
        if not os.path.exists(dir):
            os.makedirs(dir)

        self.file = open(dir + "/" + name, "wt")
        self.set_content(content)

    def set_content(self, content=""):
        self.file.seek(0)
        self.file.truncate(0)
        self.file.flush()
        self.file.write(content)
        self.file.flush()

    def get_name(self):
        return self.file.name


# ## Runner


class RunnerOutcome(Enum):
    INVALID = 0
    BUSY = 1
    TIMEOUT = 2
    IGNORE = 3
    ERROR = 4
    COMPLETE = 5


class Runner:

    # logging constructor -> DO NOT OVERRIDE -> use setup instead!
    def __init__(self, config=None):
        self.setup(config=config)
        self._log_config(name="init_config.log", config=config)

    def _log_write(self, name="unknown.log", content=""):
        if not self.log:
            return
        RunnerFile(dir=self.get_dir(), name=name, content=content)
        return

    def _log_config(self, name="unknown_config.log", config=None):
        self._log_write(name=name, content=str(config) + "\n")

    def _log_kwargs(self, name="unknown_args.log", **kwargs):
        self._log_write(name=name, content=str(kwargs) + "\n")

    def _log_result(self, name="result.log", result=(RunnerOutcome.INVALID, None)):
        content = "OUTCOME: " + str(result[0]) + "\n"
        content += "RESULTS:\n" + str(result[1]) + "\n"
        self._log_write(name=name, content=content)

    def _log_results(
        self,
        task_result=(RunnerOutcome.INVALID, None),
        task_post_result=(RunnerOutcome.INVALID, None),
    ):
        self._log_result(name="task_pre_result.log", result=task_result)
        self._log_result(name="task_result.log", result=task_post_result)

    # override instead of constructor
    def setup(self, config=None):

        dir = config["dir"]
        self.log = config["log"]
        self.result = (RunnerOutcome.INVALID, None)

        # create runner dir
        if config.get("RunnerDirNotIndexed", False):
            # directory without index -> e.g. for working in existing directory
            self.dir = dir + "/" + type(self).__name__
        else:
            # new directory with index
            i = 0
            self.dir = dir + "/" + type(self).__name__ + "_" + str(i)
            while os.path.exists(self.dir):
                i += 1
                self.dir = dir + "/" + type(self).__name__ + "_" + str(i)
        if not os.path.exists(self.dir):
            os.makedirs(self.dir)

    def _task_exec(self):
        self.task_pre()
        task_result = self.task()
        task_post_result = self.task_post(task_result)
        self.result = task_post_result
        self._log_results(task_result=task_result, task_post_result=task_post_result)

    # override
    def task_pre(self):
        pass

    # override
    def task(self):
        return (RunnerOutcome.COMPLETE, None)

    # override
    def task_post(self, result):
        return result

    def is_busy(self):
        return False

    def wait(self):
        return

    def get_dir(self):
        return self.dir

    def get_result(self):
        return self.result

    # override
    def get_error_cause(self):
        return "unknown"

    # run method for calling
    # DO NOT OVERRIDE -> use only for call
    def run(self, **kwargs):
        self._log_kwargs(name="run_args.log", **kwargs)
        return self.run_handler(**kwargs)

    # run method for execution
    # OVERRIDE -> use for implementation
    def run_handler(self, **kwargs):
        self._task_exec()
        return self.get_result()


# iter 0 -> infinite
def runner_bench(
    runner,
    custom_stat_f=None,
    iter=1000,
    stop_on_ignore=False,
    stop_on_error=False,
    **kwargs,
):

    completes = 0
    errors = 0
    ignores = 0
    timeouts = 0

    def print_stats(i):
        if iter < 0:
            iter_str = "inf"
        else:
            iter_str = str(iter)
        output = (
            str(i + 1)
            + "/"
            + iter_str
            + " [ completes: "
            + str(completes)
            + ", ignores: "
            + str(ignores)
            + ", errors: "
            + str(errors)
            + ", timeouts: "
            + str(timeouts)
        )
        if custom_stat_f:
            output += custom_stat_f(runner)
        print("\r" + output + " ]", end="")

    kwargs["blocking"] = True

    start = time.clock_gettime(time.CLOCK_MONOTONIC)
    i = 0
    while iter < 0 or i < iter:
        print_stats(i)
        ret = runner.run(**kwargs)
        i += 1

        if ret[0] == RunnerOutcome.COMPLETE:
            completes += 1
        if ret[0] == RunnerOutcome.TIMEOUT:
            timeouts += 1
        elif ret[0] == RunnerOutcome.IGNORE:
            ignores += 1
            if stop_on_ignore:
                break
        elif ret[0] != RunnerOutcome.COMPLETE:
            errors += 1
            if stop_on_error:
                break

    print_stats(i - 1)
    print()
    end = time.clock_gettime(time.CLOCK_MONOTONIC)
    diff = end - start
    print(i, " iterations in ", diff, "seconds")
    print(diff / i, " seconds per iteration")
    print(i / diff, " iterations per second")


class ThreadingRunner(Runner):
    def setup(self, config=None):
        super().setup(config=config)
        self.thread = threading.Thread(target=self.__threadf)
        self.run_event = threading.Event()
        self.ready_event = threading.Event()
        self.running = False
        self.busy = False

    def __threadf(self):
        while True:

            # wait for action
            self.run_event.wait()
            self.run_event.clear()

            # quit thread if requested
            if not self.running:
                break

            # exec
            self._task_exec()

            # cleanup
            self.busy = False
            # notify
            self.ready_event.set()

    # override
    def task(self):
        return (RunnerOutcome.COMPLETE, None)

    def is_busy(self):
        return self.busy

    def wait(self):
        self.ready_event.wait()
        self.ready_event.clear()

    def run_handler(self, blocking=False, **kwargs):

        if self.is_busy():
            return (RunnerOutcome.BUSY, None)

        # lazy startup
        if not self.running:
            self.running = True
            self.thread.start()

        # init
        self.ready_event.clear()
        self.result = (RunnerOutcome.BUSY, None)
        self.busy = True
        # start
        self.run_event.set()

        # wait if blocking
        if blocking:
            self.wait()

        # return results
        return self.get_result()


class ProcessTimeoutRunner(ThreadingRunner):
    def setup(self, config=None, program=[]):

        super().setup(config=config)

        self.timeout = 1.0
        self.proc_pid = -1
        self.set_program(program)

    def _log_command(self, name="command.log", command=[]):
        self._log_write(name=name, content=" ".join(command) + "\n")

    def _log_input(self, name="input.log", input=""):
        self._log_write(name=name, content=input)

    def _log_output(self, stdout="", stderr=""):
        self._log_write(name="stdout.log", content=stdout)
        self._log_write(name="stderr.log", content=stderr)

    def set_program(self, program):
        self.program = program

    def task(self):
        command = self.program + self.parameters

        self._log_command(command=command)
        self._log_input(input=self.input)

        timedout = False
        proc = subprocess.Popen(
            command,
            cwd=self.get_dir(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.proc_pid = proc.pid
        try:
            stdout, stderr = proc.communicate(input=self.input, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            timedout = True
        self.proc_pid = -1

        self._log_output(stdout=stdout, stderr=stderr)

        if timedout:
            outcome = RunnerOutcome.TIMEOUT
            ret = None
        else:
            # create ret struct
            ret = subprocess.CompletedProcess(
                args=command, returncode=proc.returncode, stdout=stdout, stderr=stderr
            )
            # TODO only negative ???
            if ret.returncode != 0:
                outcome = RunnerOutcome.ERROR
            else:
                outcome = RunnerOutcome.COMPLETE

        return (outcome, ret)

    # request stop
    def stop(self):
        if self.proc_pid > 0:
            try:
                os.kill(self.proc_pid, signal.SIGTERM)
            except Exception:
                pass

    def run_handler(self, timeout=1.0, parameters=[], input="", **kwargs):

        # parameter parsing
        self.timeout = timeout
        self.parameters = parameters
        self.input = input

        return super().run_handler(parameters=parameters, input=input, **kwargs)
