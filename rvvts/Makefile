# (C) 2023-24 Manfred Schlaegl <manfred.schlaegl@jku.at>, Institute for Complex Systems, JKU Linz
#
# SPDX-License-Identifier: BSD 3-clause "New" or "Revised" License
#

FLAKE8_ARGS=\
	--show-source --count --statistics	\
	--max-complexity=20					\
	--max-line-length=127				\
	--exclude .git,__pycache__,__init__.py,.ipynb_checkpoints

.PHONY: all lint check

all: package

lint:
	flake8 . ${FLAKE8_ARGS}
check: lint

style:
	black .
