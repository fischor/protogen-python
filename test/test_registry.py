import protogen
import google.protobuf.descriptor_pb2


def test_registry_resolve_message_type():
    registry = protogen.Registry()

    acme_hello_file = protogen.File(
        google.protobuf.descriptor_pb2.FileDescriptorProto(
            name="acme/hello.proto", package="acme"
        ),
        False,
        protogen.default_py_import_func,
    )

    acme_hello_message = protogen.Message(
        google.protobuf.descriptor_pb2.DescriptorProto(name="Hello"),
        acme_hello_file,
        None,
        None,
    )

    acme_hello_world_message = protogen.Message(
        google.protobuf.descriptor_pb2.DescriptorProto(name="World"),
        acme_hello_file,
        acme_hello_message,
        None,
    )

    acme_cloud_library_v1_library_file = protogen.File(
        google.protobuf.descriptor_pb2.FileDescriptorProto(
            name="acme/cloud/library/v1/library.proto", package="acme.cloud.library.v1"
        ),
        False,
        protogen.default_py_import_func,
    )

    acme_cloud_library_v1_hello_message = protogen.Message(
        google.protobuf.descriptor_pb2.DescriptorProto(name="Hello"),
        acme_cloud_library_v1_library_file,
        None,
        None,
    )

    acme_cloud_library_v1_hello_world_message = protogen.Message(
        google.protobuf.descriptor_pb2.DescriptorProto(name="World"),
        acme_cloud_library_v1_library_file,
        acme_cloud_library_v1_hello_message,
        None,
    )

    google_protobuf_empty_file = protogen.File(
        google.protobuf.descriptor_pb2.FileDescriptorProto(
            name="google/protobuf/empty.proto", package="google.protobuf"
        ),
        False,
        protogen.default_py_import_func,
    )

    google_protobuf_empty_message = protogen.Message(
        google.protobuf.descriptor_pb2.DescriptorProto(name="Empty"),
        google_protobuf_empty_file,
        None,
        None,
    )

    registry._register_message(acme_hello_message)
    registry._register_message(acme_hello_world_message)
    registry._register_message(acme_cloud_library_v1_hello_message)
    registry._register_message(acme_cloud_library_v1_hello_world_message)
    registry._register_message(google_protobuf_empty_message)

    got = registry.resolve_message_type("acme.cloud.library.v1.Hello", "World")
    assert got is not None
    assert got.full_name == "acme.cloud.library.v1.Hello.World"

    got = registry.resolve_message_type("acme.Hello", "World")
    assert got is not None
    assert got.full_name == "acme.Hello.World"

    got = registry.resolve_message_type("acme.Hello", "World")
    assert got is not None
    assert got.full_name == "acme.Hello.World"

    got = registry.resolve_message_type("acme.cloud.library.v1.Hello", "Hello")
    assert got is not None
    assert got.full_name == "acme.cloud.library.v1.Hello"

    got = registry.resolve_message_type("acme.cloud.library.Something", "Hello")
    assert got is not None
    assert got.full_name == "acme.Hello"

    got = registry.resolve_message_type(
        "acme.cloud.library.v1.Hello", "google.protobuf.Empty"
    )
    assert got is not None
    assert got.full_name == "google.protobuf.Empty"
