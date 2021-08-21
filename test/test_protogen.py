import unittest
import subprocess
import os.path
import os

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
        proto = os.path.join(pwd, "test", "vendor", "google", "api", "annotations.proto")
        plugin = os.path.join(pwd, "test", "plugin", "main.py")
        
        # Create the output directory if it does not exists. protoc requires it
        # to exist before generating output to it.
        out_dir = os.path.join(pwd, "testout")
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        # Run protoc.
        proc = subprocess.Popen(
            ["protoc", "-I", vendor, f"--plugin=protoc-gen-empty={plugin}", f"--empty_out={out_dir}", proto], 
            text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        # Executed from current directory (repo root)
        code = proc.wait()
        if code == 0:
            output = proc.stdout.read()
        else:
            output = proc.stderr.read()
        proc.terminate()
        self.assertEqual(output, "")
        self.assertEqual(code, 0)

        # Check content of directory.
        with open("test/golden/google/api/annotations.out") as f:
            golden = f.read()
        with open("testout/google/api/annotations.out") as f:
            generated = f.read()
        
        self.assertEqual(golden, generated)


