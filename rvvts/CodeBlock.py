#!/usr/bin/env python
# coding: utf-8
#
# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

import re
import jsonpickle


class CodeStats:
    def __init__(self):
        self.fragments = 0
        self.lines = 0
        self.ins = 0
        self.vins = 0

    def add(self, b):
        self.fragments += b.fragments
        self.lines += b.lines
        self.ins += b.ins
        self.vins += b.vins

    def __str__(self):
        ret = ""
        ret += "#fragments:   " + str(self.fragments) + "\n"
        ret += "#lines:       " + str(self.lines) + "\n"
        ret += "#ins:         " + str(self.ins) + "\n"
        ret += "#vins:        " + str(self.vins) + "\n"
        return ret

    def __repr__(self):
        return self.__str__()


class CodeElement:
    def __init__(self):
        pass

    def replace(self, oldvalue, newvalue):
        pass

    def as_code(self):
        return ""

    def __str__(self):
        return self.as_code()

    def __repr__(self):
        return self.__str__()

    def get_stats(self):
        return CodeStats()


class CodeFragment(CodeElement):
    def __init__(self, code: str):
        super().__init__()
        self.code = code

    def replace(self, oldvalue, newvalue):
        self.code = self.code.replace(oldvalue, newvalue)

    def as_code(self):
        return self.code

    def get_stats(self):
        s = CodeStats()
        s.fragments = 1
        lines = self.code.split("\n")
        s.lines = len(lines)
        for line in lines:
            if re.match(r"^\s*\S.*", line):
                s.ins += 1
            if re.match(r"^\s*v.*", line):
                s.vins += 1
        return s


class CodeFragmentList(CodeElement):
    def __init__(self, fragment=None):
        self.elements = []
        if fragment is not None:
            self.add(fragment)

    def replace(self, oldvalue, newvalue):
        for e in self.elements:
            e.replace(oldvalue, newvalue)

    def add(self, elem: CodeFragment):
        self.elements.append(elem)

    def add_list(self, list):
        self.elements += list.elements

    def as_list(self):
        return self.elements

    def as_code(self):
        return "\n".join(element.as_code() for element in self.as_list())

    def len(self):
        return len(self.elements)

    def get_part(self, begin, end):
        list = CodeFragmentList()
        list.elements = self.elements[begin:end]
        return list

    def get_stats(self):
        s = CodeStats()
        for e in self.elements:
            s.add(e.get_stats())
        return s


class CodeBlock(CodeElement):

    @classmethod
    def load(cls, filename):
        with open(filename, "r") as file:
            json_data = file.read()
            return jsonpickle.decode(json_data)
        return None

    def __init__(self, init_fragments=None, main_fragments=None, deinit_fragments=None):

        super().__init__()
        self.init_fragments = CodeFragmentList()
        self.deinit_fragments = CodeFragmentList()
        self.main_fragments = CodeFragmentList()
        if init_fragments is not None:
            self.init_fragments = init_fragments
        if main_fragments is not None:
            self.main_fragments = main_fragments
        if deinit_fragments is not None:
            self.deinit_fragments = deinit_fragments

    def replace(self, oldvalue, newvalue):
        self.init_fragments.replace(oldvalue, newvalue)
        self.deinit_fragments.replace(oldvalue, newvalue)
        self.main_fragments.replace(oldvalue, newvalue)

    def save(self, filename):
        json_data = jsonpickle.encode(self)
        with open(filename, "w") as file:
            file.write(json_data)

    def set_init_fragments(self, fragments: CodeFragmentList):
        self.init_fragments = fragments

    def set_deinit_fragments(self, fragments: CodeFragmentList):
        self.deinit_fragments = fragments

    def add_init_fragment(self, fragment: CodeFragment):
        self.init_fragments.add(fragment)

    def add_deinit_fragment(self, fragment: CodeFragment):
        self.deinit_fragments.add(fragment)

    def add(self, fragment: CodeFragment):
        self.main_fragments.add(fragment)

    def as_list(self):
        ret = []
        ret += [self.init_fragments.as_list()]
        ret += [self.main_fragments.as_list()]
        ret += [self.deinit_fragments.as_list()]
        return ret

    def as_code(self):
        ret = ""
        ret += self.init_fragments.as_code() + "\n"
        ret += self.main_fragments.as_code() + "\n"
        ret += self.deinit_fragments.as_code()
        return ret

    def main_len(self):
        return self.main_fragments.len()

    def get_part(self, begin, end):
        part = self.main_fragments.get_part(begin, end)
        return CodeBlock(
            init_fragments=self.init_fragments,
            deinit_fragments=self.deinit_fragments,
            main_fragments=part,
        )

    def get_stats_main(self):
        return self.main_fragments.get_stats()

    def get_stats_all(self):
        s = self.get_stats_main()
        s.add(self.init_fragments.get_stats())
        s.add(self.deinit_fragments.get_stats())
        return s

    def get_stats(self):
        return self.get_stats_all()
