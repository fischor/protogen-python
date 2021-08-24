import unittest
import subprocess
import os.path
import os
from typing import Tuple, List


class TestProtogen(unittest.TestCase):

    # Just e2e tests for now.
    # One could create and store some protodescriptorsets using protoc.
    # Create a CodeGeneratorRequest out of it and run the plugin using that
    # one use Options(stdin=fake_stdin, stdout=fake_stdout) to fake stdin
    # and out.
    def test_e2e(self):
        # test won't work if using relative path. protoc seems to have troubles
        # finding files then:
        #
        #   - protoc-gen-empty=./test/plugin/main.py: warning: directory does not exist.
        #   - vendor/google/api/annotations.proto: File does not reside within any path
        #     specified using --proto_path (or -I).  You must specify a --proto_path which
        #     encompasses this file.  Note that the proto_path must be an exact prefix of
        #     the .proto file names -- protoc is too dumb to figure out when two paths
        #     (e.g. absolute and relative) are equivalent (it's harder than you think).
        #
        pwd = os.getcwd()
        vendor = os.path.join(pwd, "test", "vendor")
        proto = os.path.join(
            pwd, "test", "vendor", "google", "api", "annotations.proto"
        )
        plugin = os.path.join(pwd, "test", "plugin", "main.py")

        # Create the output directory if it does not exists. protoc requires it
        # to exist before generating output to it.
        out_dir = os.path.join(pwd, "testout", "main")
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        # Run protoc.
        code, output = _run_protoc(
            [
                "protoc",
                "-I",
                vendor,
                f"--plugin=protoc-gen-empty={plugin}",
                f"--empty_out={out_dir}",
                proto,
            ]
        )
        self.assertEqual(output, "")
        self.assertEqual(code, 0)

        # Check content of directory.
        with open("test/golden/google/api/annotations.out") as f:
            golden = f.read()
        with open("testout/main/google/api/annotations.out") as f:
            generated = f.read()

        self.assertEqual(golden, generated)

    def test_parameter(self):
        pwd = os.getcwd()
        vendor = os.path.join(pwd, "test", "vendor")
        proto = os.path.join(
            pwd, "test", "vendor", "google", "api", "annotations.proto"
        )
        plugin = os.path.join(pwd, "test", "plugin", "parameter.py")

        # Create the output directory if it does not exists. protoc requires it
        # to exist before generating output to it.
        out_dir = os.path.join(pwd, "testout", "params")
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        self.maxDiff = None

        code, output = _run_protoc(
            [
                "protoc",
                "-I",
                vendor,
                f"--plugin=protoc-gen-params={plugin}",
                f"--params_opt=k1=v1,k2=v2;k3=v3,",
                f"--params_opt=k4",
                f"--params_opt=k5=v5",
                f"--params_out=abc=x,5=2:{out_dir}",
                proto,
            ]
        )
        self.assertEqual(output, "")
        self.assertEqual(code, 0)

        # Check content of directory.
        with open("test/golden/params.txt") as f:
            golden = f.read()
        with open("testout/params/out.txt") as f:
            generated = f.read()

        self.assertEqual(golden, generated)


def _run_protoc(args: List[str]) -> Tuple[int, str]:
    proc = subprocess.Popen(
        args, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE
    )
    # Executed from current directory (repo root)
    code = proc.wait()
    if code == 0:
        output = proc.stdout.read()
    else:
        output = proc.stderr.read()
    proc.terminate()  # TODO necessary?
    return code, output
