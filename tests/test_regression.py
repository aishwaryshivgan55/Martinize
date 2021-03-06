#!/usr/bin/env python
# MARTINIZE
# A simple, versatile tool for coarse-graining molecular systems
# Copyright (C) 2017  Tsjerk A. Wassenaar and contributors
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.

"""
Regression tests for martinize.

This test suite runs the insane command line with various set of arguments, and
assess that the results correspond to the result obtained with previous
versions.

Notice that these tests do not assess that the results are correct. Instead,
they assess that changes do not affect the behaviour of the program.

If ran as a script, this generate the reference files expected by the tests. If
ran usinf pytest or nosetest, this executes insane with a series of arguments
and compares the output to the reference.
"""

from __future__ import print_function

import contextlib
import functools
import glob
import mock
import os
import random
import shutil
import shlex
import subprocess
import sys
import tempfile
import textwrap
import importlib

from nose.tools import assert_equal, assert_raises

import utils

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

try:
    from itertools import izip_longest as zip_longest
except ImportError:
    from itertools import zip_longest


PROGRAM = 'martinize'

CLI = importlib.import_module(".".join([PROGRAM, "cli"]))

HERE = os.path.abspath(os.path.dirname(__file__))
EXECUTABLE = utils.which(PROGRAM)
DATA_DIR = os.path.join(HERE, 'data')
INPUT_DIR = os.path.join(HERE, 'data', 'inputs')
RANDSEED = '42'
SEED_ENV = 'INSANE_SEED'

# The arguments to test insane with are listed here. The tuple is used both to
# generate the references, and to run the tests.
# To add a test case, add the arguments to test in the tuple.
SIMPLE_TEST_CASES = [
    ('-f {}.pdb'.format(pdb), pdb) for pdb in ('1ubq', '3csy', '2qwo')
]



def _arguments_as_list(arguments):
    """
    Return the arguments as a list as expected by subprocess.Popen.

    The arguments can be provided as a string that will be spitted to a list.
    They can also be provided as a list, then the list will be returned
    untouched.
    """
    try:
        arguments_list = shlex.split(arguments)
    except ValueError:
        arguments_list = arguments
    return arguments_list


def _output_from_arguments(arguments, option='-o'):
    """
    Find the file name of the GRO output provided as argument to program.

    The file name is passed to program via the '-o' argument. If the argument is
    provided several times, then only the last one is considered.

    This function reads the arguments provided as a list of arguments.
    """
    if not option:
        return None

    for i, argument in reversed(list(enumerate(arguments))):
        if argument == option:
            break
    else:
        raise ValueError('Output name is not provided to {} '
                         'using the {} argument.'.format(PROGRAM, option))

    return arguments[i + 1]


def _split_case(case):
    """
    Get the arguments and the input directory from a test case.
    """
    if len(case) == 3:
        case_args, input_dir, alias = case
        if input_dir is not None:
            input_dir = os.path.join(INPUT_DIR, input_dir)
    elif len(case) == 2:
        case_args, input_dir = case
        input_dir = os.path.join(INPUT_DIR, input_dir)
        alias = case_args
    else:
        case_args = case
        input_dir = None
        alias = case_args
    return case_args, input_dir, alias


def _reference_path(arguments, alias=None):
    """
    Get the path to the reference files for the simple test cases.
    """
    arg_list = _arguments_as_list(arguments)
    simple_case_ref_data = os.path.join(DATA_DIR, 'simple_case')
    base_name = arguments if alias is None else alias
    out_struct = _output_from_arguments(arg_list, option='')
    if out_struct:
        out_format = os.path.splitext(out_struct)[-1]
        ref_gro = os.path.join(simple_case_ref_data, base_name + out_format)
    else:
        ref_gro = None
    try:
        out_top = _output_from_arguments(arg_list, option='-o')
    except ValueError:
        ref_top = None
    else:
        ref_top = os.path.join(simple_case_ref_data, base_name + '.top')
    ref_stdout = os.path.join(simple_case_ref_data, base_name + '.out')
    ref_stderr = os.path.join(simple_case_ref_data, base_name + '.err')
    return ref_gro, ref_top, ref_stdout, ref_stderr


def _run_external(arguments):
    command = [EXECUTABLE] + arguments
    env = {SEED_ENV: INSANE_SEED} if SEED_ENV else {}
    process = subprocess.Popen(command,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               env=env)
    out, err = process.communicate()
    return out, err, process.returncode


def _run_internal(arguments):
    if SEED_ENV:
        os.environ[SEED_ENV] = RANDSEED
    random.seed(RANDSEED)
    command = [EXECUTABLE] + arguments
    out = StringIO()
    err = StringIO()
    with mock.patch('random.random', return_value=0.1):
        with utils._redirect_out_and_err(out, err):
            returncode = CLI.main(command)
    out = out.getvalue()
    err = err.getvalue()
    return out, err, returncode


def run_program(arguments, input_directory=None, runner=_run_internal):
    """
    Run program with the given arguments

    Insane is run in a copy of `input_directory`.
    """
    # Copy the content of the input directory in the current directory if an
    # input directory is provided.
    if input_directory is not None:
        for path in glob.glob(os.path.join(input_directory, '*')):
            if os.path.isdir(path):
                shutil.copytree(path, '.')
            else:
                shutil.copy2(path, '.')
    out, err, returncode = runner(arguments)
    print("** {} exited with return code {}.".format(PROGRAM.capitalize(), returncode))
    if returncode:
        print(err)
    return out, err, returncode


def compare(output, reference):
    """
    Assert that two files are identical.
    """
    out_file = utils._open_if_needed(output)
    ref_file = utils._open_if_needed(reference)
    with out_file, ref_file:
        lines_zip = zip_longest(out_file, ref_file, fillvalue=None)
        for out_line, ref_line in lines_zip:
            assert_equal(out_line, ref_line)
        extra_out = list(out_file)
        extra_ref = list(ref_file)
        assert_equal(extra_out, [])
        assert_equal(extra_ref, [])


def run_and_compare(arguments, input_dir,
                    ref_gro, ref_top,
                    ref_stdout, ref_stderr, runner=_run_external):
    """
    Run program and compare its output against a reference
    """
    # Create the command as a list for subprocess.Popen.
    # The arguments can be pass to the current function as a string or as a
    # list of arguments. If they are passed as a string, they need to be
    # converted to a list.
    arguments = _arguments_as_list(arguments)

    # The name of the output file must be provided to program for program to
    # work. Since we also need that file name, let's get it from program's
    # arguments.
    ## Magic here -- Expect DRAGONS
    gro_output = _output_from_arguments(arguments, option='-o')
    if ref_top is not None:
        top_output = _output_from_arguments(arguments, option='-p')

    # We want program to run in a temporary directory. This allows to keep the
    # file system clean, and it avoids mixing output of different tests.
    with utils.tempdir():
        out, err, returncode = run_program(arguments, input_dir, runner=runner)
        assert not returncode
        assert os.path.exists(gro_output)
        if os.path.splitext(gro_output)[-1] == '.gro':
            utils.assert_gro_equal(gro_output, ref_gro)
        else:
            compare(gro_output, ref_gro)
        compare(utils.ContextStringIO(out), ref_stdout)
        compare(utils.ContextStringIO(err), ref_stderr)
        if ref_top is not None:
            compare(top_output, ref_top)


def _test_simple_cases():
    """
    This function generates test functions for nosetests. These test functions
    execute insane with the argument listed in SIMPLE_TEST_CASES.
    """
    for case in SIMPLE_TEST_CASES:
        case_args, input_dir, alias = _split_case(case)
        ref_gro, ref_top, ref_stdout, ref_stderr = _reference_path(case_args, alias)
        # The test generator could yield run and compare directly. Bt, then,
        # the verbose display of nosetests gets crowded with the very long
        # names of the reference file, that are very redundant. Using a partial
        # function allows to have only the arguments for insane displayed.
        _test_case = functools.partial(
            run_and_compare,
            ref_gro=ref_gro,
            ref_top=ref_top,
            ref_stdout=ref_stdout,
            ref_stderr=ref_stderr,
            runner=_run_external)
        _test_case.__doc__ = ' '.join([EXECUTABLE, case_args])
        yield (_test_case, case_args, input_dir)


def test_simple_cases_internal():
    """
    This function generates test functions for nosetests. These test functions
    calls insane's main function with the argument listed in SIMPLE_TEST_CASES.
    """
    for case in SIMPLE_TEST_CASES:
        case_args, input_dir, alias = _split_case(case)
        ref_gro, ref_top, ref_stdout, ref_stderr = _reference_path(case_args, alias)
        # The test generator could yield run and compare directly. Bt, then,
        # the verbose display of nosetests gets crowded with the very long
        # names of the reference file, that are very redundant. Using a partial
        # function allows to have only the arguments for insane displayed.
        _test_case = functools.partial(
            run_and_compare,
            ref_gro=ref_gro,
            ref_top=ref_top,
            ref_stdout=ref_stdout,
            ref_stderr=ref_stderr,
            runner=_run_internal)
        _test_case.__doc__ = ' '.join([EXECUTABLE, case_args])
        yield (_test_case, case_args, input_dir)


class TestGroTester(object):
    """
    Test if the comparison of GRO file catches the differences.
    """
    ref_gro_content = """\
    INSANE! Membrane UpperLeaflet>POPC=1 LowerLeaflet>POPC=1
    4
        1POPC   NC3    1   2.111  14.647  11.951
        1POPC   PO4    2   2.177  14.644  11.651
        1POPC   GL1    3   2.128  14.642  11.351
        1POPC   GL2    4   1.961  14.651  11.351
    10 10 10"""

    def test_equal(self):
        """
        Make sure that identical files do not fail.
        """
        with utils.tempdir():
            with open('ref.gro', 'w') as outfile:
                print(textwrap.dedent(self.ref_gro_content),
                      file=outfile, end='')
            utils.assert_gro_equal('ref.gro', 'ref.gro')

    def test_diff_x(self):
        """
        Make sure that error in coordinates is caught.
        """
        gro_content = """\
        INSANE! Membrane UpperLeaflet>POPC=1 LowerLeaflet>POPC=1
        4
            1POPC   NC3    1   2.111  14.647  11.951
            1POPC   PO4    2   2.177  14.644  11.651
            1POPC   GL1    3   2.128  14.642  11.353  # Is not within tolerance
            1POPC   GL2    4   1.961  14.651  11.351
        10 10 10"""

        with utils.tempdir():
            with open('ref.gro', 'w') as outfile:
                print(textwrap.dedent(self.ref_gro_content),
                      file=outfile, end='')
            with open('content.gro', 'w') as outfile:
                print(textwrap.dedent(gro_content), file=outfile, end='')
            assert_raises(AssertionError, utils.assert_gro_equal,
                          'content.gro', 'ref.gro')

    def test_diff_in_tolerance(self):
        """
        Make sure that small errors in coordinates are not caught.
        """
        gro_content = """\
        INSANE! Membrane UpperLeaflet>POPC=1 LowerLeaflet>POPC=1
        4
            1POPC   NC3    1   2.111  14.647  11.951
            1POPC   PO4    2   2.177  14.644  11.651
            1POPC   GL1    3   2.128  14.642  11.352  # Is within tolerance
            1POPC   GL2    4   1.961  14.651  11.351
        10 10 10"""

        with utils.tempdir():
            with open('ref.gro', 'w') as outfile:
                print(textwrap.dedent(self.ref_gro_content),
                      file=outfile, end='')
            with open('content.gro', 'w') as outfile:
                print(textwrap.dedent(gro_content), file=outfile, end='')
            utils.assert_gro_equal('content.gro', 'ref.gro')

    def test_diff_natoms(self):
        """
        Make sure that differences in number of atom is caught.
        """
        gro_content = """\
        INSANE! Membrane UpperLeaflet>POPC=1 LowerLeaflet>POPC=1
        6
            1POPC   NC3    1   2.111  14.647  11.951
            1POPC   PO4    2   2.177  14.644  11.651
            1POPC   GL1    3   2.128  14.642  11.351
            1POPC   GL2    4   1.961  14.651  11.351
            1POPC   C1A    5   2.125  14.651  11.051
            1POPC   D2A    6   2.134  14.602  10.751
        10 10 10"""

        with utils.tempdir():
            with open('ref.gro', 'w') as outfile:
                print(textwrap.dedent(self.ref_gro_content),
                      file=outfile, end='')
            with open('content.gro', 'w') as outfile:
                print(textwrap.dedent(gro_content), file=outfile, end='')
            assert_raises(AssertionError, utils.assert_gro_equal,
                          'content.gro', 'ref.gro')

    def test_diff_title(self):
        """
        Make sure that a different title is caught.
        """
        gro_content = """\
        A different title
        4
            1POPC   NC3    1   2.111  14.647  11.951
            1POPC   PO4    2   2.177  14.644  11.651
            1POPC   GL1    3   2.128  14.642  11.351
            1POPC   GL2    4   1.961  14.651  11.351
        10 10 10"""

        with utils.tempdir():
            with open('ref.gro', 'w') as outfile:
                print(textwrap.dedent(self.ref_gro_content),
                      file=outfile, end='')
            with open('content.gro', 'w') as outfile:
                print(textwrap.dedent(gro_content), file=outfile, end='')
            assert_raises(AssertionError, utils.assert_gro_equal,
                          'content.gro', 'ref.gro')

    def test_diff_box(self):
        """
        Make sure that a different box is caught.
        """
        gro_content = """\
        INSANE! Membrane UpperLeaflet>POPC=1 LowerLeaflet>POPC=1
        4
            1POPC   NC3    1   2.111  14.647  11.951
            1POPC   PO4    2   2.177  14.644  11.651
            1POPC   GL1    3   2.128  14.642  11.351
            1POPC   GL2    4   1.961  14.651  11.351
        10 9.9 10 9.08 4 54"""

        with utils.tempdir():
            with open('ref.gro', 'w') as outfile:
                print(textwrap.dedent(self.ref_gro_content),
                      file=outfile, end='')
            with open('content.gro', 'w') as outfile:
                print(textwrap.dedent(gro_content), file=outfile, end='')
            assert_raises(AssertionError, utils.assert_gro_equal,
                          'content.gro', 'ref.gro')

    def test_diff_field(self):
        """
        Make sure that a difference in a field is caught.
        """
        gro_content = """\
        INSANE! Membrane UpperLeaflet>POPC=1 LowerLeaflet>POPC=1
        4
            1POPC   NC3    1   2.111  14.647  11.951
            1DIFF   PO4    2   2.177  14.644  11.651
            1POPC   GL1    3   2.128  14.642  11.351
            1POPC   GL2    4   1.961  14.651  11.351
        10 10 10"""

        with utils.tempdir():
            with open('ref.gro', 'w') as outfile:
                print(textwrap.dedent(self.ref_gro_content),
                      file=outfile, end='')
            with open('content.gro', 'w') as outfile:
                print(textwrap.dedent(gro_content), file=outfile, end='')
            assert_raises(AssertionError, utils.assert_gro_equal,
                          'content.gro', 'ref.gro')


def generate_simple_case_references():
    """
    Run program to generate reference files for the simple regression tests.

    Run insane with the arguments listed in SIMPLE_TEST_CASES. The output GRO
    file, the standard output, and the standard error are stored in the
    DATA_DIR/simple_case directory.
    """
    for case in SIMPLE_TEST_CASES:
        case_args, input_dir, alias = _split_case(case)
        arguments = _arguments_as_list(case_args)
        out_gro = _output_from_arguments(arguments, option='')
        try:
            out_top = _output_from_arguments(arguments, option='-o')
        except ValueError:
            out_top = None
        ref_gro, ref_top, ref_stdout, ref_stderr = _reference_path(case_args, alias)
        with utils.tempdir():
            print(PROGRAM + ' ' + ' '.join(arguments))
            out, err, _ = run_program(arguments, input_dir)
            with open(ref_stdout, 'w') as outfile:
                for line in out:
                    print(line, file=outfile, end='')
            with open(ref_stderr, 'w') as outfile:
                for line in err:
                    print(line, file=outfile, end='')
            if out_gro is not None:
                shutil.copy2(out_gro, ref_gro)
            if out_top is not None:
                shutil.copy2(out_top, ref_top)


def clean_simple_case_references():
    """
    Delete reference files for the simple tests if they are not in use anymore.
    """
    simple_test_cases = [_split_case(case)[2] for case in SIMPLE_TEST_CASES]
    simple_case_ref_data = os.path.join(DATA_DIR, 'simple_case')
    for path in glob.glob(os.path.join(simple_case_ref_data, '*')):
        base_name = os.path.basename(os.path.splitext(path)[0])
        if base_name not in simple_test_cases:
            print(path)
            os.remove(path)


def main():
    """
    Command line entry point.
    """
    help_ = """
Generate or clean the reference files for program's regression tests.

{0} gen: generate the files
{0} clean: clean the unused files

nosetests -v: run the tests
""".format(sys.argv[0])
    commands = {'gen': generate_simple_case_references,
                'clean': clean_simple_case_references}
    if len(sys.argv) != 2:
        print(help_, file=sys.stderr)
        sys.exit(1)
    try:
        commands[sys.argv[1]]()
    except KeyError:
        print("Unrecognized keyword '{}'.".format(sys.argv[1]))
        print(help_, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
