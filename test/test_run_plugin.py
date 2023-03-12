from protogen.test import run_plugin


def test_run_plugin():
    x = 1
    resp = run_plugin(
        proto_paths=["test/vendor"],
        files_to_generate=["google/api/annotations.proto", "google/api/http.proto"],
        plugin="test.plugin.main",
    )

    assert len(resp.file) == 2


def test_run_plugin_with_proto3_optionals():
    resp = run_plugin(
        proto_paths=["test/optional"],
        files_to_generate=["optional.proto"],
        plugin="test.plugin.main",
    )

    assert len(resp.file) == 1
