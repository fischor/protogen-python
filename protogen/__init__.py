"""A one line summary of the module or program, terminated by a period.

Leave one blank line.  The rest of this docstring should contain an
overall description of the module or program.  Optionally, it may also
contain a brief description of exported classes and functions and/or usage
examples.

  Typical usage example:

  foo = ClassFoo()
  bar = foo.FunctionBar()

Examples:
    This is how you would create a plugin::

        #!/usr/bin/env python
        import protogen
        
        def generate(gen: protogen.Plugin):
            for f in gen.files_to_generate:
                g = gen.new_generated_file(f.generated_filename_prefix + "_pb.py", f.py_import_path)
                
                g.P("// This is my generated output file")
                
                for message in f.messages:
                    g.P("class ", message.py_ident.name, "():")
                    for field in message.fields:
                        # do something useful
        
                for service in f.services:
                    g.P("class ", service.py_ident.name, "():")
                    for method in service.methods:
                        g.P("    def ", method.py_name, "(input: ", method.input.ident, ") -> ", method.output.ident, ":")
                        g.P("         # do something useful")
        
        # Read input that is passed from protoc to create a protogen.Plugin instance. 
        # And runs the `generate` function with that plugin instance.
        protogen.Options().run(generate)


    Then run it like this::

        $ protoc -I <root-of-proto-files> --plugin=protoc-gen-my_plugin=./path/to/main.py --my_plugin_out=./out <files-to-generate>
    
    It is important to have the ``protoc-gen-<plugin_name>`` prefix for the ``--plugin`` option, otherwise ``protoc``
    will return with an error, saying it can not find that plugin.

Notes:
    * describe why the standard proto library is not enough
    * is already resolves field message/enum types and method input/output
      types, but no locations and also does no python idents
    * brings py idents and a GeneratedFile to automatically resolve imports
    * brings: message in context: to get the python name for a message within
      the context it is generated in (useful for nested messages and enums).

Notes:
    * how to go from google.protobuf.compiler.plugin_pb2.CodeGeneratorRequest
      to a CodeGeneratorRequest with resolve message types?
    * would need to call google.protobuf.descriptor.FileDescriptor.ParseFromString
      for all provided files etc.,
    * instead of the raw proto, all protogen types would then have the
      desc parameter (similiar to what golang is doing).
"""

import enum
import keyword
import sys
from typing import BinaryIO, Callable, Dict, List, Optional, Set
import google.protobuf.descriptor_pool
import google.protobuf.descriptor_pb2
import google.protobuf.message_factory
import google.protobuf.compiler.plugin_pb2

import protogen._case


class Registry():
    """Registry for protogen types.

    """
    def __init__(self):
        self._services_by_name: Dict[str, 'Service'] = {}
        self._messages_by_name: Dict[str, 'Message'] = {}
        self._enums_by_name: Dict[str, 'Enum'] = {}
        self._files_by_name: Dict[str, 'File'] = {}

    def _register_file(self, file: 'File'):
        self._files_by_name[file.proto.name] = file

    def _register_service(self, service: 'Service'):
        """Register a service.

        Args:
            service (Service): Service to register.
        """
        self._services_by_name[service.full_name] = service

    def _register_message(self, message: 'Message'):
        """Register a message.

        Args:
            message (Message): Message to register.
        """
        self._messages_by_name[message.full_name] = message

    def _register_enum(self, enum: 'Enum'):
        """Register an Enum.

        Args:
            enum (Enum): Enum to register.
        """
        self._enums_by_name[enum.full_name] = enum

    def file_by_name(self, name: str) -> Optional['File']:
        if name not in self._files_by_name:
            return None
        return self._files_by_name[name]

    def service_by_name(self, name: str) -> Optional['Service']:
        if name not in self._services_by_name:
            return None
        return self._services_by_name[name]

    def message_by_name(self, name: str) -> Optional['Message']:
        """Resolve a message. C++ scoping rules apply if name doesnt start with a \".\".
        """
        if name not in self._messages_by_name:
            return None
        return self._messages_by_name[name]

    def enum_by_name(self, name: str) -> Optional['Enum']:
        if name not in self._enums_by_name:
            return None
        return self._enums_by_name[name]

    def all_files(self) -> List['File']:
        """Get all files provided in the protoc request."""
        return list(self._files_by_name.values())

    def all_services(self) -> List['Service']:
        """Get all services provided in the protoc request."""
        return list(self._services_by_name.values())

    def all_messages(self) -> List['Message']:
        """Get all messages provided in the protoc request."""
        return list(self._messages_by_name.values())

    def all_enums(self) -> List['Enum']:
        """Get all enums provided in the protoc request."""
        return list(self._enums_by_name.values())

    def files_by_package(self, package: str) -> List['File']:
        """Get files by proto package"""
        files = []
        for file in self._files_by_name.values():
            if file.proto.package == package:
                files.append(file)
        return files

    def services_by_package(self, package: str) -> List['Service']:
        """Get services by proto package"""
        services = []
        for service in self._services_by_name.values():
            if service.parent_file.proto.package == package:
                services.append(service)
        return services

    def messages_by_package(self, package: str, top_level_only=False) -> List['Message']:
        """Get messages by proto package."""
        messages = []
        for message in self._messages_by_name.values():
            include = message.parent is None or not top_level_only
            if message.parent_file.proto.package == package and include:
                messages.append(message)
        return messages

    def enums_by_package(self, package: str, top_level_only=False) -> List['Enum']:
        """Get enums by proto package."""
        enums = []
        for enum in self._enums_by_name.values():
            include = enum.parent is None or not top_level_only
            if enum.parent_file.proto.package == package and include:
                enums.append(enum)
        return enums


def _resolve_enum_type_name(registry: Registry, ref: str,
                            type_name: str) -> Optional['Enum']:
    """Find a enum in the registry.

    Intended to be used to resolve `FieldDescriptorProto.type_name`.
    """
    if type_name.startswith("."):
        return registry.enum_by_name(type_name[1:])
    return Exception("resolve without dot notation not implemented yet")


def _resolve_message_type_name(registry: Registry, ref: str,
                               type_name: str) -> Optional['Message']:
    """Resolve a type_name.

    Intended to be used to resolve `FieldDescriptorProto.type_name`.
    `MethodDescriptorProto.input_type` and `MethodDescriptorProto-output_type`.
    To resolve this, several 
    """
    if type_name.startswith("."):
        return registry.message_by_name(type_name[1:])
    return None


def _clean_comment(cmmt: str) -> str:
    """Remove the first whitespace from every line, if any."""
    lines = cmmt.splitlines()
    clean_lines = []
    for line in lines:
        if len(line) > 0 and line[0] == " ":
            clean_lines.append(line[1:])
        else:
            clean_lines.append(line)
    return "\n".join(clean_lines)


# TODO maybe dataclass
class Location:
    def __init__(self, source_file: str, path: List[int],
                 leading_detached_comments: List[str], leading_comments: str,
                 trailing_comments: str):
        self.source_file = source_file
        self.path = path
        self.leading_detached_comments = [
            _clean_comment(c) for c in leading_detached_comments
        ]
        self.leading_comments = _clean_comment(leading_comments)
        self.trailing_comments = _clean_comment(trailing_comments)


def _resolve_location(file: google.protobuf.descriptor_pb2.FileDescriptorProto,
                      path: List[int]) -> Location:
    """Resolve location information for a path.

    Args:
        file (google.protobuf.descriptor_pb2.FileDescriptorProto): 
            The file descriptor.
        path (List[number]):
            Path to resolve the location information for.

    Returns:
        Location: Location information for the path in file, or an empty Location
        information if the path is not present in the file.
    """
    for location_pb in file.source_code_info.location:
        # location_pb.path is a RepeatedScalarFieldContainer, that implements __eq__
        # and compares again its inner _values (list(int)) to the other argument.
        if location_pb.path == path:
            return Location(file.name, path,
                            location_pb.leading_detached_comments,
                            location_pb.leading_comments,
                            location_pb.trailing_comments)
    return Location(file.name, path, [], "", "")


# Note: The ImportPath class only makes sense if one follows the one proto file = one
# python file schema.
class PyImportPath:

    def __init__(self, path: str):
        self._path = path

    def ident(self, name: str) -> 'PyIdent':
        """Create `PyIdent` with `self` as import path and name as `py_name`."""
        return PyIdent(self, name)

    def __eq__(self, o: object) -> bool:
        if type(o) != PyImportPath:
            return NotImplemented
        return self._path == o._path

    def __hash__(self) -> int:
        return hash(self._path)

def _is_reserved_name(value: str) -> bool:
    if keyword.iskeyword(value):
        return True

    if value in ("bytes", "str"):
        return True

    return False


def _sanitize_name(value: str) -> str:
    """Necessary for field and method names."""
    # https://www.python.org/dev/peps/pep-0008/#descriptive-naming-styles
    return f"{value}_" if _is_reserved_name(value) else value


class PyIdent:
    """Identifies a python class, enum value or method.

    Note that it might be necessary to sanitize the py_name before.

    Attributes:
        py_import_path (PyImportPath): Python import path.
        py_name (str): Python identfier name. Is going to be sanitized
            automatically.
    """
    def __init__(self, py_import_path: PyImportPath, py_name: str):
        self.py_import_path = py_import_path
        self.py_name = _sanitize_name(py_name)


class Kind(enum.Enum):
    """Kind is the proto type for a field."""

    DOUBLE = 1
    FLOAT = 2
    INT64 = 3
    UINT64 = 4
    INT32 = 5
    FIXED64 = 6
    FIXED32 = 7
    BOOL = 8
    STRING = 9
    GROUP = 10
    MESSAGE = 11
    BYTES = 12
    UINT32 = 13
    ENUM = 14
    SFIXED32 = 15
    SFIXED64 = 16
    SINT32 = 17
    SINT64 = 18


class Cardinality(enum.Enum):
    OPTIONAL = 1
    REQUIRED = 2
    REPEATED = 3


class EnumValue:
    """EnumValue is a enum value.

    Attributes:
        proto (google.protobuf.descriptor_pb2.EnumValueDescriptorProto): The raw proto descriptor.
        py_ident (PyIdent): Python identifier.
        full_name (str): Full proto name of the enum value. Note that this is
            somewhat special.
        number (int): Enum number.
        parent (Enum): Enum the value is declared in.
        location (Location): Location information associated with this enum value within 
            the enum values parent file.
    """
    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.EnumValueDescriptorProto,
        parent: 'Enum',
        path: List[int],
    ):
        self.proto = proto
        # The Python identifier for a enum value is TODO
        self.py_ident = parent.py_ident.py_import_path.ident(
            parent.py_ident.py_name + "." + proto.name)
        self.number = self.proto.number
        self.parent = parent
        self.location = _resolve_location(parent.parent_file.proto, path)

class Enum:
    """Enum is a protobuf enum.

    Attributes:
        proto (google.protobuf.descriptor_pb2.EnumDescriptorProto): The raw proto descriptor.
        py_ident (PyIdent): Python indentifier of the enum.
        full_name (str): Full proto name of the enum.
        parent_file (File): File the enum is declared in.
        parent (Optional[Message]): For nested enums, the message the enum is declared in,
            None otherwise. 
            > All other proto declarations are in the namespace of the parent. 
            > However, enum values do not follow this rule and are within the 
            > namespace of the parent's parent (i.e., they are a sibling of the 
            > containing enum). Thus, a value named "FOO_VALUE" declared within an 
            > enum uniquely identified as "proto.package.MyEnum" has a full name of 
            > "proto.package.FOO_VALUE".
        values (List[EnumValue]): Values of the enum.
        location (Location): Location information associated with this enum within 
            the enums parent file.
    """
    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.EnumDescriptorProto,
        parent_file: 'File',
        parent: Optional['Message'],
        path: List[int],
    ):
        """Initializes a new Enum; do not use."""
        self.proto = proto
        if parent is None:
            self.full_name = parent_file.proto.package + "." + proto.name
            self.py_ident = parent_file.py_import_path.ident(proto.name)
        else:
            self.full_name = parent.full_name + "." + proto.name
            self.py_ident = parent.py_ident.py_import_path.ident(
                parent.py_ident.py_name + "." + proto.name)
        self.parent_file = parent_file
        self.parent = parent
        self.location = _resolve_location(parent_file.proto, path)
        # Add enum values.
        self.values: List[EnumValue] = []
        for i in range(len(proto.value)):
            value_path = path + [
                2, i
            ]  # 2 is the field number for `value` in `EnumDescriptorProto`.
            self.values.append(EnumValue(proto.value[i], self, value_path))


def _is_map(message: "Message") -> bool:
    return message.proto.HasField(
        'options') and message.proto.options.HasField('map_entry') and getattr(
            message.proto.options, 'map_entry')


class Field:
    """Field is a protobuf field.

    Attributes:
        proto (google.protobuf.descriptor_pb2.FieldDescriptorProto): The raw proto descriptor.
        py_name (str): Python name of the field. Same as proto.name typically.
        full_name (str): Full proto name of the field.
        parent (Optional[Message]): The message the field in declared in. None for 
            top-level extensions.
        parent_file (File): The File the field is declared in.
        oneof (Optional[OneOf]): Containing oneof; None if not part of a oneof
        kind (Kind): The field kind.
        cardinality (Cardinality): Cardinality of the field.
        extendee (Optional[Message]): Extendee for extension fields, None otherwise.
        enum (Optional[Enum]): If kind is enum, this is the enum type.
        message (Optiona[Message]): If kind is message, this is the message type.
        location (Location): Location information associated with this field within 
            the fields parent file.
    """
    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.FieldDescriptorProto,
        parent: Optional['Message'],
        parent_file: 'File',
        oneof: Optional['OneOf'],
        path: List[int],
    ):
        self.proto = proto
        self.py_name = proto.name
        if parent is not None:
            self.full_name = parent.full_name + "." + proto.name
        else:
            # top-level-extension
            self.full_name = parent_file.proto.package + "." + proto.name
        self.parent = parent
        self.parent_file = parent_file
        self.oneof = oneof
        self.kind = Kind(proto.type)  # type V is builtin.int
        self.cardinality = Cardinality(proto.label)  # type V is builtin.int
        self.location = _resolve_location(parent_file.proto, path)
        self.message: Optional['Message'] = None
        self.enum: Optional['Enum'] = None

    def is_map(self) -> bool:
        if self.message is None:
            return False
        return _is_map(self.message)

    def is_list(self) -> bool:
        return self.cardinality == Cardinality.REPEATED and not self.is_map()

    def map_key(self) -> Optional['Field']:
        if not self.is_map():
            return None
        return self.message.fields[0]

    def map_value(self) -> Optional['Field']:
        if not self.is_map():
            return None
        return self.message.fields[1]

    def _resolve(self, registry: Registry):
        # resolve extendee is present
        if self.proto.HasField('extendee'):
            self.extendee = _resolve_message_type_name(registry,
                                                       self.full_name,
                                                       self.proto.extendee)
            if self.extendee is None:
                raise ResolutionError(
                    file=self.parent_file.proto.name,
                    ref=self.full_name,
                    type_name=self.proto.extendee,
                )

        # resolve the enum
        if self.kind == Kind.ENUM:
            if not self.proto.HasField('type_name'):
                raise InvalidDescriptorError(
                    full_name=self.full_name,
                    msg="is of kind ENUM but has no `type_name` set")
            self.enum = _resolve_enum_type_name(registry, self.full_name,
                                                self.proto.type_name)
            if not self.enum:
                raise ResolutionError(
                    file=self.parent_file.proto.name,
                    ref=self.full_name,
                    type_name=self.proto.type_name,
                )

        # resolve the message TODO: type_name is also set for messages
        # doe maps have a Kind.GROUP set? Might also be that maps have
        # the value kind as kind set.
        if self.kind == Kind.MESSAGE:
            if not self.proto.HasField('type_name'):
                raise InvalidDescriptorError(
                    full_name=self.full_name,
                    msg="is of kind MESSAGE but has no `type_name` set")
            self.message = _resolve_message_type_name(registry, self.full_name,
                                                      self.proto.type_name)
            if self.message is None:
                raise ResolutionError(
                    file=self.parent_file.proto.name,
                    ref=self.full_name,
                    type_name=self.proto.type_name,
                )

        # elif self.proto.HasField('type_name'):
        #     self.message = _resolve_message_type_name(registry, self.full_name,
        #                                               self.proto.type_name)
        #     if self.message is None:
        #         raise ResolutionError(
        #             file=self.parent_file.proto.name,
        #             ref=self.full_name,
        #             type_name=self.proto.type_name,
        #         )


class OneOf:
    """OneOf represents a proto oneof.

    Attributes:
        proto (google.protobuf.descriptor_pb2.OneofDescriptorProto): The raw proto descriptor.
        full_name (str): Full proto name of the oneof.
        parent (Message): Message the oneof is declared in.
        fields (List[Field]): Fields that are part of this oneof.
        location (Location): Location information associated with this message within 
            the messages parent file.
    """
    def __init__(self,
                 proto: google.protobuf.descriptor_pb2.OneofDescriptorProto,
                 parent: 'Message', path: List[int]):
        self.proto = proto
        self.full_name = parent.full_name + "." + proto.name
        self.parent = parent
        self.location = _resolve_location(parent.parent_file.proto, path)
        self.fields: List[Field] = []


Extension = Field


class Message:
    """Message represents a protobuf message.

    Attributes:
        proto (google.protobuf.descriptor_pb2.DescriptorProto): The raw proto descriptor.
        py_ident (PyIdent): Python identifier (class). Note that this is just a
            combination of python package and message name taking into consideration
            the `py_import_func`.
        full_name (str): Full proto name of the message.
        parent_file (File): The File the Message is defined in.
        parent: (Optional[Message]): The parent message in case this is a nested message
            None, for top-level messages.
        fields (List[Field]): Message field declarations. This includes fields defined within `oneof`s.
        oneofs (List[OneOf]): Message oneof declarations.
        enums (List[Enum]): Nested enum declarations.
        messages (List[Message]): Nested message declarations.
        extensions (ListExtension): Nested extension declations.
        location (Location): Location information associated with this message within 
            the messages parent file.
    """
    def __init__(self, proto: google.protobuf.descriptor_pb2.DescriptorProto,
                 parent_file: 'File', parent: Optional['Message'],
                 path: List[int]):
        """Initialize a new Message.

        Args:
            proto (FileDescriptorProto): The raw proto descriptor.
            parent_file (File): Parent file the message is defined in.
            path (List[int]): Source code info location path within the parent file.
        """
        self.proto = proto
        self.py_ident = parent_file.py_import_path.ident(
            self.proto.name)  # TODO how to handle nested messages?
        if parent is not None:
            self.full_name = parent.full_name + "." + proto.name
        else:
            self.full_name = parent_file.proto.package + "." + proto.name
        self.parent_file = parent_file
        self.parent = parent
        self.location = _resolve_location(parent_file.proto, path)

        # Initialize Oneofs.
        self.oneofs: List[OneOf] = []
        for i in range(len(proto.oneof_decl)):
            oneof_path = path + [
                8, i
            ]  # 8 is the number of oneof_decl in MessageDescriptorProto.
            oneof = OneOf(proto.oneof_decl[i], self, oneof_path)
            self.oneofs.append(oneof)

        # Initialize Fields.
        self.fields: List[Field] = []
        for i in range(len(proto.field)):
            field_path = path + [
                2, i
            ]  # 2 is the number of field in MessageDescriptorProto.
            # In case that field belongs to a oneof, initialize it with that oneof.
            # The `oneof_index` indicates to which oneof the field belongs.
            if proto.field[i].HasField('oneof_index'):
                field = Field(proto.field[i], self, parent_file,
                              self.oneofs[proto.field[i].oneof_index],
                              field_path)
                self.oneofs[proto.field[i].oneof_index].fields.append(field)
                self.fields.append(field)
            else:
                field = Field(proto.field[i], self, parent_file, None,
                              field_path)
                self.fields.append(field)

        # Initialize nested Messages.
        self.messages: List[Message] = []
        for i in range(len(proto.nested_type)):
            message_path = path + [
                3, i
            ]  # 3 is the number of nested_type in MessageDescriptorProto.
            message = Message(proto.nested_type[i], parent_file, self,
                              message_path)
            self.messages.append(message)

        # Initialize nested Enums.
        self.enums: List[Enum] = []
        for i in range(len(proto.enum_type)):
            enum_path = path + [
                4, i
            ]  # 3 is the number of enum_type in MessageDescriptorProto.
            enum = Enum(proto.enum_type[i], parent_file, self, enum_path)
            self.enums.append(enum)

        # Initialize message Extensions.
        self.extension: List[Extension] = []
        for i in range(len(proto.extension)):
            extension_path = path + [
                6, i
            ]  # 6 is the number of extension in MessageDescriptorProto.
            extension = Field(proto.extension[i], self, parent_file, None,
                              extension_path)
            self.extension.append(extension)

    def _register(self, registry: Registry):
        """Register the message and its nested messages and enums onto the registry."""
        registry._register_message(self)
        for message in self.messages:
            message._register(registry)
        for enum in self.enums:
            registry._register_enum(enum)

    def _resolve(self, registry: Registry):
        """Resolve dependencies of the message."""
        for message in self.messages:
            message._resolve(registry)
        for field in self.fields:
            field._resolve(registry)
        for extension in self.extension:
            extension._resolve(registry)
        
        # Remove autogenerated messages from the list of
        # nested message. Typically, no code shpuld be generated
        # for these. 
        # TODO maybe make this configurable
        cleaned_messages = []
        for message in self.messages:
            if message.proto.options.HasField("map_entry") and message.proto.options.map_entry:
                continue
            cleaned_messages.append(message)
        self.messages = cleaned_messages



class ResolutionError(Exception):
    """Custom error raised when resolution went wrong.

    Attributes:
        file (str): current proto file
        ref (str): reference
        msg_enum_or_service (str): what looking for
    """
    def __init__(self, file: str, ref: str, type_name: str):
        msg = f"({file}: Failed to resolve \"{type_name}\" from \"{ref}\"."
        super().__init__(msg)
        self.file = file
        self.ref = ref
        self.type_name = type_name


class InvalidDescriptorError(Exception):
    """Raised when a descriptor is invalid.

    E.g. if a FieldDescriptors Kind is enum or message but no type_name is set.
    Or if a location is specified that can not be found.
    """
    def __init__(self, full_name: str, msg: str):
        super().__init__(f"invalid descriptor error ({full_name}): {msg}")


class Method:
    """Method is a service method.

    Attributes:
        proto (google.protobuf.descriptor_pb2.MethodDescriptorProto): The raw proto descriptor.
        py_name (str): snake cased version of the method name.
        proto_full_name (str): Full proto name of the method.
        grpc_path (str): grpc path
        parent (Service): The Service the method belongs to.
    """
    def __init__(self,
                 proto: google.protobuf.descriptor_pb2.MethodDescriptorProto,
                 parent: 'Service', path: List[int]):
        self.proto = proto
        self.py_name = protogen._case.snake_case(proto.name)
        self.full_name = parent.full_name + "." + proto.name
        self.grpc_path = "/" + parent.full_name + "/" + proto.name
        self.parent = parent
        # input (needs to be resolved)
        # output (needs to be resolved)
        self.location = _resolve_location(parent.parent_file.proto, path)

    def _resolve(self, registry: Registry):
        self.input = _resolve_message_type_name(registry, self.full_name,
                                                self.proto.input_type)
        if self.input is None:
            raise ResolutionError(
                file=self.parent.parent_file.proto.name,
                ref=self.full_name,
                type_name=self.proto.input_type,
            )
        self.output = _resolve_message_type_name(registry, self.full_name,
                                                 self.proto.output_type)
        if self.output is None:
            raise ResolutionError(
                file=self.parent.parent_file.proto.name,
                ref=self.full_name,
                type_name=self.proto.output_type,
            )


class Service:
    """Service is a proto service.

    Attributes:
        proto (google.protobuf.descriptor_pb2.ServiceDescriptorProto): The raw proto descriptor.
        py_ident (PyIdent): The Python identifier (class). Note that this is just a
            combination of python package and service name taking into consideration
            the `py_import_func`.
        full_name (str): Full proto name of the service.
        parent_file (File): File the Service is defined in.
        methods (List[Method]): Service method declarations.
        location (Location): Comments associated with this service.
    """
    def __init__(self,
                 proto: google.protobuf.descriptor_pb2.ServiceDescriptorProto,
                 parent: 'File', path: List[int]):
        self.proto = proto
        self.py_ident = parent.py_import_path.ident(proto.name)
        self.full_name = parent.proto.package + "." + proto.name
        self.parent_file = parent
        self.location = _resolve_location(parent.proto, path)

        self.methods: List[Method] = []
        for i in range(len(proto.method)):
            method_path = path + [2, i]
            method = Method(proto.method[i], self, method_path)
            self.methods.append(method)

    def _register(self, registry: Registry):
        registry._register_service(self)

    def _resolve(self, registry: Registry):
        for method in self.methods:
            method._resolve(registry)


class File:
    """File is a proto file (and maybe a python file).

    Attributes always depend on the plugin configuration (espacilly python_import_path
    and generate and python_package_name).

    Attributes:
        proto (google.protobuf.descriptor_pb2.FileDescriptorProto): The raw proto descriptor.
        generated_filename_prefix (str): Name of the original proto file (without `.proto` extension).
        py_package_name (str): Name of the proto package the file belongs to. This is
            the result of the proto package name of the proto file applied to the 
            `py_import_function` of the `Plugin` that is used to read this file.
        py_import_path (ImportPath): Import path for this file. Uses the `python_package_name`
            as package.
        generate (bool): Whether Python code should be generated for this in context of the
            `Plugin` that was used to read in the descriptor.
        dependencies (list(File)): imported by this file
        enums (list(Enum)): Top-level enum declarations.
        messages (list(Message)): Top-level message declarations.
        services (list(Service)): Top-level service declarations.
        extensions (list(Extension)): Top-level extension declarations.
        options (list(Field)): options defined for this file
    """
    def __init__(self,
                 proto: google.protobuf.descriptor_pb2.FileDescriptorProto,
                 generate: bool,
                 py_import_func: Callable[[str], str],
                 ):
        """Creates a new file.

        Args:
            proto: Raw proto file descriptor.
            generate: Whether code generator for the file is requested.
            message_factory (google.protobuf.message_factory.MessageFactory):
                Message factory to re-parse options.
        """
        self.proto = proto
        self.generated_filename_prefix = proto.name[:-len(".proto")]
        # The actual pyton path is determined using the py_import_func.
        # TODO maybe require the rewrite func to return a Python file and
        # then generate the import path from that python filename
        self.py_import_path = PyImportPath(py_import_func(proto.name, proto.package))
        self.py_package_name = str(proto.package)
        self.generate = generate
        self.dependencies: List[File] = []

        self.messages: List[Message] = []
        for i in range(len(proto.message_type)):
            path = [
                4, i
            ]  # 4 is the number of the message_type in the FileDescriptorProto.
            message = Message(proto.message_type[i], self, None, path)
            self.messages.append(message)

        self.enums: List[Enum] = []
        for i in range(len(proto.enum_type)):
            path = [
                5, i
            ]  # 5 is the number of the enum_type in the FileDescriptorProto.
            enum = Enum(proto.enum_type[i], self, None, path)
            self.enums.append(enum)

        self.services: List[Service] = []
        for i in range(len(proto.service)):
            path = [
                6, i
            ]  # 6 is the number of the service in the FileDescriptorProto.
            service = Service(proto.service[i], self, path)
            self.services.append(service)

        self.extensions: List[Extension] = []
        for i in range(len(proto.extension)):
            path = [
                7, i
            ]  # 7 is the number of the extension in the FileDescriptorProto.
            extension = Extension(proto.extension[i], None, self, None, path)
            self.extensions.append(extension)

        #
        # file_opts = proto.options
        # if descriptorpb_messages is not None:
        #     _file_opts = descriptorpb_messages["google.protobuf.FileOptions"]
        #     _file_opts.ParseFromString(proto.options.SerializeToString())
        #     file_opts = _file_opts
        # for opt in file_opts.ListFields():
        #     pass

    def _register(self, registry: Registry):
        """Register the file, all messages, enums and services on the registry."""
        registry._register_file(self)

        for message in self.messages:
            message._register(registry)
        for enum in self.enums:
            registry._register_enum(enum)
        for service in self.services:
            service._register(registry)

    def _resolve(self, registry: Registry):
        """Resolve dependencies."""
        for depName in self.proto.dependency:
            dep = registry.file_by_name(depName)
            if dep is None:
                raise ResolutionError(self.proto.name, self.proto.name, dep)
            self.dependencies.append(dep)

        for message in self.messages:
            message._resolve(registry)
        for service in self.services:
            service._resolve(registry)
        for extension in self.extensions:
            extension._resolve(registry)


def _indent(s: str, width: int) -> str:
    lines = s.splitlines()
    prefix = " ".join(["" for i in range(width + 1)])
    prefix_lines = [prefix + line for line in lines]
    return "\n".join(prefix_lines)


class GeneratedFile:
    """A file generated by a Plugin.

    This is a helper class that allows to print lines.
    Use the ``Plugin.new_generated_file`` to create a new generated file that belongs to that plugin.::

        # gen is a protogen.Plugin, f is a protogen.File
        g = gen.new_generated_file(f.generated_filename_prefix, f.py_import_path)
        g.P("// add a line to the generated file.")

        g.print_imports()

        for message in f.messages:
            g.P("class", message.py_ident.name, "():")
            g.P("    pass")
    
    The generated file handles imports for you when using the ``P`` and ``qualified_py_ident``
    methods. See ``qualified_py_ident`` for how this works. 
    Use `g.print_imports()` to specify where the imports should occur in the generated file.
    See TODO ``<link-to-example>`` for a more in depth example of import handling
    """

    def __init__(
        self, 
        name: str, 
        py_import_path: PyImportPath,
    ):
        """Create an empty file with a specified name. Use `Plugin.new_generated_file` instead."""
        self.name = name
        self._py_import_path = py_import_path
        self._buf: List[str] = []
        self._import_mark = -1
        # Set of imports. Will be rewritten using the py_import_func before added
        # to the set.
        self._imports: Set[PyImportPath] = set()
        self._indent = 0

    def set_indent(self, indent: int) -> int:
        if indent < 0:
            raise ValueError("indent must be greater or equal zero")
        old = self._indent
        self._indent = indent
        return old

    def P(self, *args):
        """Print a line to the generated output.

        Each item is converted to a string. PyIdents are handeled specially: it's imports are
        added automatically to the import list of the GeneratedFile.

        Args:
            *args: Items on that line.
        """
        line = ""
        for arg in args:
            if type(arg) == PyIdent:
                if arg.py_import_path == self._py_import_path:
                    # Add name only.
                    line += arg.py_name
                else:
                    # Add fully qualified name.
                    self._imports.add(arg.py_import_path)
                    line += arg.py_import_path._path + "." + arg.py_name
            else:
                line += str(arg)
        self._buf.append(_indent(line, self._indent))

    def qualified_py_ident(self, ident: protogen.PyIdent) -> str:
        if ident.py_import_path == self._py_import_path:
            return ident.py_name
        else:
            self._imports.add(ident.py_import_path)
            return ident.py_import_path._path + "." + ident.py_name

    def print_import(self):
        self._import_mark = len(self._buf)

    def _proto(
        self
    ) -> google.protobuf.compiler.plugin_pb2.CodeGeneratorResponse.File:
        if self._import_mark > -1:
            lines = self._buf[:self._import_mark] + [
                f"import {p._path}" for p in self._imports
            ] + self._buf[self._import_mark:]
        else:
            lines = self._buf
        content = "\n".join(lines)
        # TODO can we run yapf here?
        return google.protobuf.compiler.plugin_pb2.CodeGeneratorResponse.File(
            name=self.name,
            content=content,
        )

class Plugin():
    """A protoc plugin invocation.

    Attributes:
        parameter: (Dict[str, str]): Generator parameter passed to the plugin using `<plugin>_opt=<key>=<value>` or `<plugin>_out=<key>=<value>`
        files_to_generate (List[File]): List of files to generate code for.
    """
    def __init__(
            self,
            parameter: Dict[str, str],
            files_to_generate: List[File],
        ):
        """Create a new protoc plugin.

        This __init__ method is intended to only be used internally in the 
        resolution process. Do not use it in plugins directly. Instead, use 
        the `Options.run` method to run plugin.

        Args:
            req (plugin_pb2.CodeGeneratorRequest): Request read from protoc.
        """
        self.parameter = parameter
        self.files_to_generate = files_to_generate

        self._error: Optional[str] = None
        self._generated_files: List[GeneratedFile] = []

    def _response(self) -> google.protobuf.compiler.plugin_pb2.CodeGeneratorResponse:
        response = google.protobuf.compiler.plugin_pb2.CodeGeneratorResponse()
        if self._error is not None:
            response.error = self._error
            return response
        for f in self._generated_files:
            response.file.append(f._proto())
        return response

    def new_generated_file(self, name: str,
                           py_import_path: PyImportPath) -> GeneratedFile:
        """Create a new generated file.

        The generated file will be added to automatically to the plugin output.
        The name of the file is relative to...

        Args:
            name (str): Name of the generated file. Relative to.
            py_import_path (PyImportPath): Python import path of the new generated file.
                This is used to decide wheter to print the fully qualified name or the 
                simply name for a python identifier when using `GeneratedFile.P`.
        """
        g = GeneratedFile(name, py_import_path)
        self._generated_files.append(g)
        return g

    def error(self, msg: str):
        """Record an error in code generation.

        The plugin will report the error back to protoc and will not
        produce any output. Will act as a no-op for consecutive calls;
        only the first error is reported back.

        Args:
            msg (str): Error message to report back to protoc.
        """
        if self._error is None:
            self._error = msg

def default_py_import_func(filename: str, package: str) -> str:
    """The default `py_import_func`. See Options.__init__.

    This function implies, that for each proto file a corresponsing
    python package with a "_pb2" suffix is created::

        default_py_import_func("google/protobuf/field_mask.proto", "google.protobuf")

    Use that in your own py_import_funcs.
    """
    return filename.replace(".proto", "_pb2").replace("/", ".")

class Options():
    def __init__(
        self,
        *,
        py_import_func: Callable[[str, str], str] = default_py_import_func,
        input: BinaryIO = sys.stdin.buffer,
        output: BinaryIO = sys.stdout.buffer,
    ):
        """Create options for the resolution process.

        Args:
            py_import_func: Defines how to derive `PyImportPaths` in the resolution 
                process.
        """
        self._input = input
        self._output = output
        self._py_import_func = py_import_func

    def run(self, f: Callable[[Plugin], None]):
        """Run a code generation function."""
        req = google.protobuf.compiler.plugin_pb2.CodeGeneratorRequest.FromString(
            self._input.read())

        # Parse parameters. These are given as flags to protoc:
        # 
        #   --plugin_opt=key1=value1
        #   --plugin_opt=key2=value2,key3=value3
        #   --plugin_opt=key4,,,
        #   --plugin_opt=key5:novalue5
        #   --plugin_out=key6:./path
        #
        # Multiple in one protoc call are possible. All `plugin_opt`s 
        # are joined with a "," in the CodeGeneratorRequest. The equal 
        # sign actually has no special meaning, its just a convention.
        #
        # The above would result in a parameter string of
        #
        #   "key1=value1,key2=value2,key3=value3,key4,,,,key5:novalue5,key6"
        #
        # (ignoring the order).
        #
        # Follow the convention of parameters pairs separated by commans in
        # the form {k}={v}. If {k} (without value), write an empty string
        # to the parameter dict. For {k}={v}={v2} write {k} and key and 
        # {v}={v2} as value.
        parameter: Dict[str, str] = {}
        for param in req.parameter.split(","):
            if param == "":
                # Ignore empty parameters.
                continue
            splits = param.split("=", 1) # maximum one split
            if len(splits) == 1:
                k, v = splits[0], ""
            else: 
                k, v = splits
            parameter[k] = v

        # Resolve raw proto descriptors to their corresponding 
        # protogen classes.
        registry = Registry()
        files_to_generate: List[File] = []
        for proto in req.proto_file:
            generate = proto.name in req.file_to_generate
            file = File(proto, generate, self._py_import_func)
            file._register(registry)
            file._resolve(registry)
            if generate:
                files_to_generate.append(file)

        # Create plugin and run the provided code generation function.
        plugin = Plugin(parameter, files_to_generate)
        f(plugin)

        # Write response.
        resp = plugin._response()
        self._output.write(resp.SerializeToString())
