import protogen
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


def test_with_indent():
    g = protogen.GeneratedFile("test_with_indent", "")
    g.P("top-level")
    with g.indent(2):
        g.P("indented-by-two")
        with g.indent(4):
            g.P("indented-by-six")
        g.P("return-by-two")
    g.P("return-top-level")

    expected = [
        "top-level",
        "  indented-by-two",
        "      indented-by-six",
        "  return-by-two",
        "return-top-level",
    ]
    assert g._buf == expected
