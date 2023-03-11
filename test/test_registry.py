import unittest

import protogen
import google.protobuf.descriptor_pb2


class TestRegistry(unittest.TestCase):
    def test_resolve_enum_type_name(self):
        pass

    def test_resolve_message_type_name(self):
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
                name="acme/cloud/library/v1/library.proto",
                package="acme.cloud.library.v1",
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

        registry._register_message(acme_hello_message)
        registry._register_message(acme_hello_world_message)
        registry._register_message(acme_cloud_library_v1_hello_message)
        registry._register_message(acme_cloud_library_v1_hello_world_message)

        got = registry.resolve_message("acme.cloud.library.v1.Hello", "World")
        self.assertIsNotNone(got)
        self.assertEqual(got.full_name, "acme.cloud.library.v1.Hello.World")

        got = registry.resolve_message("acme.Hello", "World")
        self.assertIsNotNone(got)
        self.assertEqual(got.full_name, "acme.Hello.World")

        got = registry.resolve_message_type("acme.Hello", "World")
        self.assertIsNotNone(got)
        self.assertEqual(got.full_name, "acme.Hello.World")

        # Test self references.
        got = registry.resolve_message("acme.cloud.library.v1.Hello", "Hello")
        self.assertIsNotNone(got)
        self.assertEqual(got.full_name, "acme.cloud.library.v1.Hello")

        # Test self references.
        got = registry.resolve_message("acme.cloud.library.Something", "Hello")
        self.assertIsNotNone(got)
        self.assertEqual(got.full_name, "acme.Hello")
