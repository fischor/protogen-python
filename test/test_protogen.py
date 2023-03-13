from protogen.test import run_plugin


def test_protogen():
    resp = run_plugin(
        proto_paths=["test/vendor"],
        files_to_generate=["google/api/annotations.proto"],
        plugin="test.plugin.main",
    )

    assert resp.proto.error == ""

    generated, ok = resp.file_content("google/api/annotations.out")
    assert ok

    with open("test/golden/google/api/annotations.out") as f:
        golden = f.read()

    assert golden == generated


def test_parameter():
    resp = run_plugin(
        proto_paths=["test/vendor"],
        files_to_generate=["google/api/annotations.proto"],
        plugin="test.plugin.parameter",
        parameter={
            "k1": "v1",
            "k2": "v2;k3=v3",
            "k4": "",
            "k5": "v5",
            "abc": "x",
            "5": "2",
        },
    )

    assert resp.proto.error == ""

    generated, ok = resp.file_content("out.txt")
    assert ok

    with open("test/golden/params.txt") as f:
        golden = f.read()

    assert golden == generated
