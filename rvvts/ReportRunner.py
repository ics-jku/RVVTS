#!/usr/bin/env python
# coding: utf-8
#
# (C) 2026 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

from .BasicRunner import Runner, RunnerOutcome, RunnerFile

import os
import re
import shutil


class ReportRunner(Runner):
    def setup(self, config):

        super().setup(config)

        subconfig = config.copy()
        subconfig["dir"] = self.get_dir()

        if self.log:
            self.statfile = RunnerFile(dir=self.get_dir(), name="stats.log")

        dut_class = config["ReportRunner_dut"]
        self.ReportRunner_dut = dut_class(subconfig)

        self.report_config = config.copy()
        self.archive_on_timeout = config["archive_on_timeout"]
        self.archive_on_ignore = config["archive_on_ignore"]
        self.archive_on_error = config["archive_on_error"]
        self.archive_on_complete = config["archive_on_complete"]
        self.iteration = 0
        self.failid = 0
        self.timeouts = 0
        self.ignores = 0
        self.errors = 0
        self.completes = 0
        self.runkwargs = None

    def task(self):
        return self.ReportRunner_dut.run(blocking=True, **self.runkwargs)

    def task_post(self, ret):
        archivedir = None
        reportdir = None
        failid = None
        outcome_name = self.outcome_name(ret)

        if ret[0] == RunnerOutcome.TIMEOUT:
            self.timeouts += 1
            if self.archive_on_timeout:
                failid = self.failid
                name = self.case_dirname("TIMEOUT", "", "", failid)
                archivedir = os.path.join(self.artifacts_root(), name)
                reportdir = os.path.join(self.reports_root(), name)
        elif ret[0] == RunnerOutcome.IGNORE:
            self.ignores += 1
            if self.archive_on_ignore:
                failid = self.failid
                name = self.case_dirname("IGNORE", "", "", failid)
                archivedir = os.path.join(self.artifacts_root(), name)
                reportdir = os.path.join(self.reports_root(), name)
        elif ret[0] == RunnerOutcome.ERROR:
            self.errors += 1
            if self.archive_on_error:
                failid = self.failid
                category, instruction = self.error_case()
                name = self.case_dirname("ERROR", category, instruction, failid)
                archivedir = os.path.join(self.artifacts_root(), name)
                reportdir = os.path.join(self.reports_root(), name)
        elif ret[0] == RunnerOutcome.COMPLETE:
            self.completes += 1
            if self.archive_on_complete:
                name = "COMPLETE-iteration_" + f"{self.iteration :010d}"
                archivedir = os.path.join(self.artifacts_root(), name)
                reportdir = os.path.join(self.reports_root(), name)

        if archivedir is not None:
            os.makedirs(os.path.dirname(archivedir), exist_ok=True)
            shutil.copytree(self.ReportRunner_dut.get_dir(), archivedir)
            if reportdir is not None:
                self.write_report(archivedir, reportdir, ret, failid, outcome_name)

        if ret[0] != RunnerOutcome.COMPLETE:
            self.failid += 1
        self.iteration += 1

        if self.log:
            stats = ""
            stats += "iterations: " + str(self.iteration)
            stats += "\nfailids: " + str(self.failid)
            stats += "\nignores: " + str(self.ignores)
            stats += "\nerrors: " + str(self.errors)
            stats += "\ncompletes: " + str(self.completes)
            stats += "\n"
            self.statfile.set_content(stats)

        return ret

    def run_handler(self, blocking, **kwargs):
        self.runkwargs = kwargs
        return super().run_handler(blocking=blocking, **kwargs)

    def artifacts_root(self):
        return os.path.join(self.get_dir(), "ARTIFACTS")

    def reports_root(self):
        return os.path.join(self.get_dir(), "REPORTS")

    def outcome_name(self, ret):
        return ret[0].name if isinstance(ret[0], RunnerOutcome) else str(ret[0])

    def error_case(self):
        cause = self.get_error_cause()
        category, sep, instruction = cause.partition("-")
        return category, instruction if sep else ""

    def get_error_cause(self):
        if hasattr(self.ReportRunner_dut, "get_error_cause"):
            return self.ReportRunner_dut.get_error_cause()
        return "UNKNOWN-unknown"

    def case_dirname(self, kind, category, instruction, failid):
        parts = [kind]
        if category:
            parts.append(category)
        if instruction:
            parts.append(instruction)
        parts.append("FailID_" + f"{failid:06d}")
        return "-".join(parts)

    def write_report(self, archivedir, reportdir, ret, failid, outcome_name):
        os.makedirs(reportdir, exist_ok=True)

        artifacts = self.copy_report_artifacts(
            archivedir, reportdir, self.collect_artifacts()
        )
        self.add_mstate_diff_artifact(reportdir, artifacts)
        report = self.build_report(
            archivedir, reportdir, ret, artifacts, failid, outcome_name
        )
        with open(os.path.join(reportdir, "README.md"), "w") as f:
            f.write(self.render_markdown_report(report))

    def build_report(self, archivedir, reportdir, ret, artifacts, failid, outcome_name):
        case = self.parse_case_dir(os.path.basename(archivedir), failid)
        target = self.report_target()
        sections = self.build_report_sections(archivedir, reportdir, artifacts)
        return {
            "title": self.report_title(case),
            "case": case,
            "target": target,
            "runner": {
                "runner": type(self).__name__,
                "dut_runner": type(self.ReportRunner_dut).__name__,
            },
            "result": {
                "outcome": outcome_name,
                "detail": str(ret[1]),
            },
            "artifacts": artifacts,
            "sections": sections,
        }

    def parse_case_dir(self, dirname, failid):
        match = re.match(
            r"^(?P<kind>[^-]+)(?:-(?P<body>.*))?-FailID_(?P<failid>\d+)$",
            dirname,
        )
        case = {
            "artifact_dir": dirname,
            "kind": dirname.split("-", 1)[0],
            "category": "",
            "instruction": "",
            "failid": failid,
        }
        if not match:
            return case

        case["kind"] = match.group("kind")
        case["failid"] = int(match.group("failid"))
        body = match.group("body")
        if body:
            category, sep, instruction = body.partition("-")
            case["category"] = category
            case["instruction"] = instruction if sep else ""
        return case

    def report_title(self, case):
        parts = []
        if case["failid"] is not None:
            parts.append("FailID_" + f"{case['failid']:06d}")
        parts.append(case["kind"])
        if case["category"]:
            parts.append(case["category"])
        if case["instruction"]:
            parts.append(case["instruction"])
        return " ".join(parts)

    def report_target(self):
        rvisacfg = self.report_config.get("rvisacfg")
        target = {
            "ref": self.runner_label(self.report_config.get("RefCovRunner_ref")),
            "dut": self.dut_label(),
            "xlen": None,
            "vlen": None,
            "isa": "",
        }
        if rvisacfg is None:
            return target

        for key, getter in [
            ("xlen", "get_xlen"),
            ("vlen", "get_vlen"),
            ("isa", "to_isa_str"),
        ]:
            if hasattr(rvisacfg, getter):
                try:
                    target[key] = getattr(rvisacfg, getter)()
                except Exception:
                    pass
        return target

    def dut_label(self):
        dut = self.report_config.get("CompareRunner_dut")
        if self.runner_label(dut) == "DuTGDB":
            dut = self.report_config.get("DuTGDBRunner_dut", dut)
        return self.runner_label(dut)

    def runner_label(self, runner):
        if runner is None:
            return "unknown"
        name = getattr(runner, "__name__", type(runner).__name__)
        for suffix in ["Runner", "_Runner"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        if name == "RISCVOVPSIMCoverage":
            return "RISCVOVPSIM"
        return name

    def safe_name(self, name):
        name = re.sub(r"[^A-Za-z0-9_.-]+", "", str(name))
        return name or "unknown"

    def collect_artifacts(self):
        artifacts = {}

        codeerrminrunner = self.report_codeerrminrunner()
        if codeerrminrunner is not None:
            self.add_artifact(
                artifacts,
                "code_block",
                self.runner_path(codeerrminrunner, "99_res_code_block.json"),
            )
            self.add_artifact(
                artifacts,
                "ref_mstate",
                self.runner_path(codeerrminrunner, "99_res_end_ref_mstate.json"),
            )
            self.add_artifact(
                artifacts,
                "dut_mstate",
                self.runner_path(codeerrminrunner, "99_res_end_dut_mstate.json"),
            )
            self.add_artifact(
                artifacts,
                "afc_fp_report",
                self.runner_path(codeerrminrunner, "AFC_FP_report.log"),
                copy=False,
            )

        self.add_artifact(
            artifacts,
            "dut_stderr",
            self.runner_path(self.report_dut_runner(), "stderr.log"),
            copy=False,
        )
        return artifacts

    def report_codeerrminrunner(self):
        if hasattr(self.ReportRunner_dut, "codeerrminrunner"):
            return self.ReportRunner_dut.codeerrminrunner
        if hasattr(self.ReportRunner_dut, "res_code_block"):
            return self.ReportRunner_dut
        return None

    def report_dut_runner(self):
        codeerrminrunner = self.report_codeerrminrunner()
        if codeerrminrunner is None:
            return None

        codecomparerunner = getattr(codeerrminrunner, "codecomparerunner", None)
        compare_runner = getattr(codecomparerunner, "compare_runner", None)
        return getattr(compare_runner, "CompareRunner_dut", None)

    def runner_path(self, runner, filename):
        if runner is None:
            return None
        return os.path.join(runner.get_dir(), filename)

    def add_artifact(self, artifacts, name, source, copy=True):
        source_path = self.artifact_source_path(source)
        if source_path is None:
            return
        artifacts[name] = {
            "source_path": source_path,
            "report_path": self.report_artifact_name(name) if copy else None,
        }

    def artifact_source_path(self, source):
        if source is None:
            return None
        root = os.path.abspath(self.ReportRunner_dut.get_dir())
        source = os.path.abspath(source)
        try:
            common = os.path.commonpath([root, source])
        except ValueError:
            return None
        if common != root or not os.path.isfile(source):
            return None
        return os.path.relpath(source, root)

    def report_artifact_name(self, name):
        canonical_names = {
            "code_block": self.code_block_artifact_name(),
            "ref_mstate": self.mstate_artifact_name("Ref", self.report_target()["ref"]),
            "dut_mstate": self.mstate_artifact_name("DUT", self.report_target()["dut"]),
            "mstate_diff": "mstate_diff.txt",
        }
        return canonical_names.get(name, name + ".txt")

    def code_block_artifact_name(self):
        return "cblock_test_case.json"

    def code_block_title(self):
        return "Test Case (" + self.code_block_status_label() + ")"

    def code_block_status_label(self):
        labels = {
            "non_reduced": "non-reduced",
            "reduced": "reduced",
            "minimized": "minimized",
            "minimized_state": "minimized state",
            "resulting": "resulting",
        }
        return labels.get(self.code_block_status_key(), "resulting")

    def code_block_status_key(self):
        codeerrminrunner = self.report_codeerrminrunner()
        code_status = getattr(codeerrminrunner, "code_status", "")
        if code_status is None:
            return "resulting"
        code_status = str(code_status).strip().split(":", 1)[-1].strip()
        if code_status == "executed":
            return "non_reduced"
        if code_status in ["reduced", "minimized", "minimized_state"]:
            return code_status
        return "resulting"

    def mstate_artifact_name(self, prefix, runner_name):
        runner_name = self.safe_name(runner_name)
        if runner_name == "unknown":
            return "mstate_" + prefix + ".json"
        return "mstate_" + prefix + runner_name + ".json"

    def copy_report_artifacts(self, archivedir, reportdir, artifacts):
        copied_artifacts = {}
        for name, artifact in artifacts.items():
            if artifact["report_path"] is None:
                copied_artifacts[name] = {
                    "source_path": artifact["source_path"],
                    "report_path": None,
                }
                continue
            source = os.path.join(archivedir, artifact["source_path"])
            destination = os.path.join(reportdir, artifact["report_path"])
            if not os.path.isfile(source):
                continue
            try:
                shutil.copy2(source, destination)
            except OSError as e:
                copied_artifacts[name] = {
                    "source_path": artifact["source_path"],
                    "report_path": artifact["report_path"],
                    "copy_error": str(e),
                }
                continue
            copied_artifacts[name] = {
                "source_path": artifact["source_path"],
                "report_path": artifact["report_path"],
            }
        return copied_artifacts

    def add_mstate_diff_artifact(self, reportdir, artifacts):
        ref_mstate = artifacts.get("ref_mstate")
        dut_mstate = artifacts.get("dut_mstate")
        if ref_mstate is None or dut_mstate is None:
            return
        ref_path = os.path.join(reportdir, ref_mstate["report_path"])
        dut_path = os.path.join(reportdir, dut_mstate["report_path"])
        path = self.report_artifact_name("mstate_diff")
        with open(os.path.join(reportdir, path), "w") as f:
            f.write(self.diff_machine_states(ref_path, dut_path, full=True))
        artifacts["mstate_diff"] = {
            "source_path": None,
            "report_path": path,
        }

    def build_report_sections(self, archivedir, reportdir, artifacts):
        sections = []

        code_block = artifacts.get("code_block")
        if code_block is not None:
            sections.append(
                {
                    "title": self.code_block_title(),
                    "type": "code",
                    "path": code_block["report_path"],
                    "content": self.format_code_block(
                        os.path.join(reportdir, code_block["report_path"])
                    ),
                }
            )

        ref_mstate = artifacts.get("ref_mstate")
        dut_mstate = artifacts.get("dut_mstate")
        if ref_mstate is not None and dut_mstate is not None:
            ref_path = os.path.join(reportdir, ref_mstate["report_path"])
            dut_path = os.path.join(reportdir, dut_mstate["report_path"])
            sections.append(
                {
                    "title": "Resulting Machine State Diff",
                    "type": "diff",
                    "content": self.diff_machine_states(ref_path, dut_path, full=False),
                }
            )

        for artifact_key, title in [
            ("dut_stderr", "DUT stderr Output"),
            ("afc_fp_report", "FP Characterization"),
        ]:
            artifact = artifacts.get(artifact_key)
            if artifact is None:
                continue
            sections.append(
                {
                    "title": title,
                    "type": "artifact",
                    "path": artifact["report_path"],
                    "content": self.read_source_artifact(archivedir, artifact),
                }
            )

        return sections

    def format_code_block(self, path):
        try:
            from .CodeBlock import CodeBlock

            return str(CodeBlock.load(path)) + "\n"
        except Exception:
            return self.read_file(path)

    def diff_machine_states(self, ref_path, dut_path, full):
        try:
            from .MachineState import MachineState

            ref_mstate = MachineState.load(ref_path)
            dut_mstate = MachineState.load(dut_path)
            states_equal, diff_text = ref_mstate.compare(dut_mstate, diff_full=full)
            return diff_text + "STATES DIFFER: " + str(not states_equal) + "\n"
        except Exception as e:
            label = "full " if full else ""
            return (
                "Could not generate " + label + "machine-state diff: " + str(e) + "\n"
            )

    def read_source_artifact(self, archivedir, artifact):
        return self.read_file(os.path.join(archivedir, artifact["source_path"]))

    def read_file(self, path):
        try:
            with open(path, "r", errors="replace") as f:
                return f.read()
        except Exception as e:
            return "Could not read artifact: " + str(e)

    def render_markdown_report(self, report):
        lines = [
            "# " + report["title"],
            "",
        ]
        case = report["case"]
        target = report["target"]
        if target["ref"] != "unknown":
            lines.append(f"* Reference model (REF): {target['ref']}")
        if target["dut"] != "unknown":
            lines.append(f"* DUT: {target['dut']}")
        if target["xlen"] is not None:
            target_line = f"* Target: RV{target['xlen']}"
            if target["vlen"] is not None:
                target_line += f" with `VLEN = {target['vlen']}` bit"
            if target["isa"]:
                target_line += f" (`{target['isa']}`)"
            lines.append(target_line + ".")
        if case.get("failid") is not None:
            lines.append("* FailID: " + str(case["failid"]))
        for key in ["kind", "category", "instruction"]:
            value = case.get(key)
            if value not in [None, ""]:
                title_key = key.replace("_", " ").capitalize()
                lines.append(f"* {title_key}: `{value}`")
        lines.append(f"* Runner: `{report['runner']['dut_runner']}`")

        visible_artifacts = [
            "code_block",
            "ref_mstate",
            "dut_mstate",
            "mstate_diff",
        ]
        for name in visible_artifacts:
            artifact = report["artifacts"].get(name)
            if artifact is not None:
                report_path = artifact["report_path"]
                label = self.artifact_label(name)
                lines.append(f"* {label}: [{report_path}]({report_path})")
        lines.append("")
        lines += ["## Report", ""]

        for section in report["sections"]:
            lines += ["### " + section["title"], ""]
            if section["type"] == "artifact" and section["path"] is not None:
                lines.append(
                    "Source: [" + section["path"] + "](" + section["path"] + ")"
                )
                lines.append("")
            lines += ["```", section.get("content", "").rstrip(), "```", ""]

        return "\n".join(lines)

    def artifact_label(self, name):
        labels = {
            "code_block": self.code_block_title(),
            "ref_mstate": "Resulting REF machine state",
            "dut_mstate": "Resulting DUT machine state",
            "mstate_diff": "Resulting full machine state diff",
            "afc_fp_report": "Automated failure characterization report",
            "dut_stderr": "DUT stderr output",
        }
        return labels.get(name, name)
