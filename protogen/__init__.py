"""Package protogen makes writing protoc plugins easy.

A protoc plugin essentialy turns a CodeGeneratorRequest from protoc into
CodeGeneratorResponse. The CodeGeneratorRequest contains the raw proto
descriptors of the proto definitions contained in the files code generation is
requested for (and the descriptors of every file thats imported). The
CodeGeneratorResponse is returned by to plugin to protoc. It contains a list of
files (name and content) the plugin wants protoc to write to disk.

``protogen`` provides a bunch of classes to ease writing protoc plugins. Most of
them are simply replacements of their corresponding descriptors. E.g.
:class:`File` represents a proto FileDescriptor, :class:`Message` a proto
Descriptor, :class:`Service` a proto ServiceDescriptor etc. They should be self
explanatory. You can read their docstrings for more information about them.

The classes :class:`Options`, :class:`Plugin` and :class:`GeneratedFile` make up
a framework to generate (Python) files from a CodeGeneratorRequest.  You can see
these in action in the following example plugin:

.. code-block:: python

    #!/usr/bin/env python
    '''An example plugin.'''

    import protogen

    def generate(gen: protogen.Plugin):
        for f in gen.files_to_generate:
            g = gen.new_generated_file(
                f.proto.name.replace(".proto", ".py"), 
                f.py_import_path,
            )
            g.P("# Generated code ahead.")
            g.P()
            g.print_imports()
            g.P()
            for m in f.message:
                g.P("class ", m.py_ident, ":")
                g.P("  pass")
                for ff in m.fields:
                    # ...
            for s in f.services:
                g.P("class ", s.py_ident, ":")
                g.P("  pass")
                for m in f.methods:
                    g.P("  def ", m.py_name, "(request):")
                    g.P("    pass")

    if __name__ == "__main__":
        opts = protogen.Options()
        opts.run(generate)

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


class Registry:
    """A registry for protogen types.

    A registry holds referneces to :class:`File`, :class:`Service`,
    :class:`Enum`  and :class:`Message` objects that have been resolved within
    a resolution process (see :meth:`Options.run`).
    """

    def __init__(self):
        """Create a new, empty registry."""
        self._services_by_name: Dict[str, "Service"] = {}
        self._messages_by_name: Dict[str, "Message"] = {}
        self._enums_by_name: Dict[str, "Enum"] = {}
        self._files_by_name: Dict[str, "File"] = {}

    def _register_file(self, file: "File"):
        self._files_by_name[file.proto.name] = file

    def _register_service(self, service: "Service"):
        self._services_by_name[service.full_name] = service

    def _register_message(self, message: "Message"):
        self._messages_by_name[message.full_name] = message

    def _register_enum(self, enum: "Enum"):
        self._enums_by_name[enum.full_name] = enum

    def file_by_name(self, name: str) -> Optional["File"]:
        """Get a file by its full name.

        Arguments
        ---------
        name : str
            The full (proto) name of the file to retrieve.

        Returns
        -------
        file: File or None
            The file or `None` if no file with that name has been registered.
        """
        if name not in self._files_by_name:
            return None
        return self._files_by_name[name]

    def service_by_name(self, name: str) -> Optional["Service"]:
        """Get a service by its full name.

        Arguments
        ---------
        name : str
            The full (proto) name of the service to retrieve.

        Returns
        -------
        service: Service or None
            The service or `None` if no service with that name has been registered.
        """
        if name not in self._services_by_name:
            return None
        return self._services_by_name[name]

    def message_by_name(self, name: str) -> Optional["Message"]:
        """Get a message by its full name.

        Arguments
        ---------
        name : str
            The full (proto) name of the message to retrieve.

        Returns
        -------
        message: Message or None
            The message or `None` if no message with that name has been registered.
        """
        if name not in self._messages_by_name:
            return None
        return self._messages_by_name[name]

    def enum_by_name(self, name: str) -> Optional["Enum"]:
        """Get an enum by its full name.

        Arguments
        ---------
        name : str
            The full (proto) name of the enum to retrieve.

        Returns
        -------
        enum: Enum or None
            The enum or `None` if no enum with that name has been registered.
        """
        if name not in self._enums_by_name:
            return None
        return self._enums_by_name[name]

    def all_files(self) -> List["File"]:
        """Get all registered files."""
        return list(self._files_by_name.values())

    def all_services(self) -> List["Service"]:
        """Get all registered services."""
        return list(self._services_by_name.values())

    def all_messages(self) -> List["Message"]:
        """Get all registered messages."""
        return list(self._messages_by_name.values())

    def all_enums(self) -> List["Enum"]:
        """Get all registered enums."""
        return list(self._enums_by_name.values())

    def files_by_package(self, package: str) -> List["File"]:
        """Get files by proto package.

        Arguments
        ---------
        package : str
            The proto package to get files for.

        Returns
        -------
        List[File]
            The files.
        """
        files = []
        for file in self._files_by_name.values():
            if file.proto.package == package:
                files.append(file)
        return files

    def services_by_package(self, package: str) -> List["Service"]:
        """Get services by proto package.

        Arguments
        ---------
        package : str
            The proto package to get services for.

        Returns
        -------
        List[Service]
            The services.
        """
        services = []
        for service in self._services_by_name.values():
            if service.parent_file.proto.package == package:
                services.append(service)
        return services

    def messages_by_package(
        self, package: str, top_level_only: bool = False
    ) -> List["Message"]:
        """Get messages by proto package.

        Arguments
        ---------
        package : str
            The proto package to get messages for.
        top_level_only : bool, optional, default=False
            If True, only top level message are returned. Otherwise nested
            messages are included.

        Returns
        -------
        List[Message]
            The messages.
        """
        messages = []
        for message in self._messages_by_name.values():
            include = message.parent is None or not top_level_only
            if message.parent_file.proto.package == package and include:
                messages.append(message)
        return messages

    def enums_by_package(
        self, package: str, top_level_only: bool = False
    ) -> List["Enum"]:
        """Get enums by proto package.

        Arguments
        ---------
        package : str
            The proto package to get enums for.
        top_level_only : bool, optional, default=False
            If True, only top level enums are returned. Otherwise nested enums
            are included.

        Returns
        -------
        List[Enum]
            The enums.
        """
        enums = []
        for enum in self._enums_by_name.values():
            include = enum.parent is None or not top_level_only
            if enum.parent_file.proto.package == package and include:
                enums.append(enum)
        return enums


def _resolve_enum_type_name(
    registry: Registry, ref: str, type_name: str
) -> Optional["Enum"]:
    """Find a enum in the registry.

    Intended to be used to resolve `FieldDescriptorProto.type_name`.
    """
    if type_name.startswith("."):
        return registry.enum_by_name(type_name[1:])
    return Exception("resolve without dot notation not implemented yet")


def _resolve_message_type_name(
    registry: Registry, ref: str, type_name: str
) -> Optional["Message"]:
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


class Location:
    """A proto location.

    A Location identifies a piece of source code in a .proto file which
    corresponds to a particular definition.  This information is particular
    useful as it contains the comments that are associated with a certain part
    (e.g. a message or field) of the ``.proto`` file.

    Attributes
    ----------
    source_file : str
        Name of the file the location is from.
    path : List[int]
        Identifies which part of the FileDescriptor was defined at the location.
    leading_comments : str
        Comments directly attached (leading) to the location. Not separated with
        a blank.
    trailing_comments : str
        Comments directly attached (trailing) to the location. Not separated
        with a blank.
    leading_detached_comments : List[str]
        Comments that are leading to the current location and detached from it
        by at least one blank line.

    Examples
    --------
    The following example explains the different kind of comments.

    .. code-block:: proto

        optional int32 foo = 1;  // Comment attached to foo.
        // Comment attached to bar.
        optional int32 bar = 2;

        optional string baz = 3;
        // Comment attached to baz.
        // Another line attached to baz.

        // Comment attached to qux.
        //
        // Another line attached to qux.
        optional double qux = 4;

        // Detached comment for corge. This is not leading or trailing comments
        // to qux or corge because there are blank lines separating it from
        // both.

        // Detached comment for corge paragraph 2.

        optional string corge = 5;
        /* Block comment attached
        * to corge.  Leading asterisks
        * will be removed. */
        /* Block comment attached to
        * grault. */
        optional int32 grault = 6;

        // ignored detached comments.

    """

    def __init__(
        self,
        source_file: str,
        path: List[int],
        leading_detached_comments: List[str],
        leading_comments: str,
        trailing_comments: str,
    ):
        self.source_file = source_file
        self.path = path
        self.leading_detached_comments = [
            _clean_comment(c) for c in leading_detached_comments
        ]
        self.leading_comments = _clean_comment(leading_comments)
        self.trailing_comments = _clean_comment(trailing_comments)


def _resolve_location(
    file: google.protobuf.descriptor_pb2.FileDescriptorProto, path: List[int]
) -> Location:
    """Resolve location information for a path.

    Arguments
    ---------
    file : google.protobuf.descriptor_pb2.FileDescriptorProto
        The file descriptor that contains the location information.
    path : List[number]:
        Path to resolve the location information for.

    Returns
    -------
    Location
        Location information for the path in file, or an empty Location
        information if the path is not present in the file.
    """
    for location_pb in file.source_code_info.location:
        # location_pb.path is a RepeatedScalarFieldContainer, that implements __eq__
        # and compares again its inner _values (list(int)) to the other argument.
        if location_pb.path == path:
            return Location(
                file.name,
                path,
                location_pb.leading_detached_comments,
                location_pb.leading_comments,
                location_pb.trailing_comments,
            )
    return Location(file.name, path, [], "", "")


class PyImportPath:
    """A Python import path.

    Represents a Python import path as used in a Python import statement. In
    Python, the import path is used to identify the module to import. An import
    path "google.protobuf.timestamp_pb2" refers to the
    "google/protobuf/timestamp_pb2.py" module and might be imported as follows:

    >>> import google.protobuf.timestamp_pb2

    or

    >>> from google.protobuf.timestamp_pb2 import Timestamp

    This is just a simple wrapper class around the import string. It is used in
    the `GeneratedFile` to keep track of which import statements need to be
    included in the output of the generated file as well as how a `PyIdent`
    needs to be referred to in the output the generated file.

    Example
    -------
    Use the `PyImportPath` class to take advantage of the import resolution
    mechanism provided by the `GeneratedFile`:

    >>> import protogen
    >>> grpc_pkg = protogen.PyImportPath("grpc")
    >>> # g is of type protogen.GeneratedFile
    >>> g.P("def my_method(request):")
    >>> g.P("  ", grpc_pkg.ident("unary_unary"), "(request)")

    That way `grpc_pkg` will be added automatically to the import list of `g`.
    """

    def __init__(self, path: str):
        """Create a new Python import path wrapping `path`."""
        self._path = path

    def ident(self, name: str) -> "PyIdent":
        """Create a `PyIdent` with `self` as import path and name as `py_name`.

        Arguments
        ---------
        name : str
            Python name of the identifier.

        Returns
        -------
        PyIdent
            The python identifier.
        """
        return PyIdent(self, name)

    def __eq__(self, o: object) -> bool:
        """Compare the import path.

        Returns
        -------
        True, if the interal paths match. False, otherwise.
        """
        if type(o) != PyImportPath:
            return NotImplemented
        return self._path == o._path

    def __hash__(self) -> int:
        """Hash the import path."""
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
    """An identifier for a Python class, function or variable.

    A Python class, function or variable is uniquely identified by its import
    path (e.g. ``google.protobuf.timestamp_pb2``), that references the module its
    defined in, and name (eg `Timestamp`).

    Attributes
    ----------
    py_import_path : PyImportPath
        The Python import path of the identifier.
    py_name : str
        Name of the class, function or variable.
    """

    def __init__(self, py_import_path: PyImportPath, py_name: str):
        """Create a new Python identifier.

        The recommended way to initialize a new `PyIdent` is using
        `PyImportPath.indent()` instead.

        >>> grpc_pkg = protogen.PyImportPath("grpc")
        >>> grpc_pkg.ident("unary_unary")
        """
        self.py_import_path = py_import_path
        self.py_name = _sanitize_name(py_name)


class Kind(enum.Enum):
    """Kind is an enumeration of the different value types of a field."""

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
    """Cardinality specifies whether a field is optional, required or repeated."""

    OPTIONAL = 1
    REQUIRED = 2
    REPEATED = 3


class EnumValue:
    """A proto enum value.

    This is the ``protogen`` equivalent to a protobuf EnumValueDescriptor. The
    enum values attributes are obtained from the EnumValueDescriptor it is
    derived from and references to other ``protogen`` classes that have been
    resolved in the resolution process. It represents a Protobuf enum value
    declared within an Protobuf enum definition.

    Attributes
    ----------
    proto : google.protobuf.descriptor_pb2.EnumValueDescriptorProto
        The raw EnumValueDescriptor of the enum value.
    py_ident : PyIdent
        Python identifier for the Python attribute of the enum value.
    full_name : str
        Full proto name of the enum value. Note that full names of enum values
        are different: All other proto declarations are in the namespace of
        their parent. Enum values however are within the namespace of ther
        parent file.  An enum value named ``FOO_VALUE`` declared within an enum
        ``proto.package.MyEnum`` has a full name of ``proto.package.FOO:VALUE``.
    number : int
        The enum number.
    parent : Enum
        The enum the enum value is declared in.
    location : Location
        Comments associated with the enum value.
    """

    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.EnumValueDescriptorProto,
        parent: "Enum",
        path: List[int],
    ):
        self.proto = proto
        # The Python identifier for a enum value is TODO
        self.py_ident = parent.py_ident.py_import_path.ident(
            parent.py_ident.py_name + "." + proto.name
        )
        self.number = self.proto.number
        self.parent = parent
        self.location = _resolve_location(parent.parent_file.proto, path)


class Enum:
    """A proto enum.

    This is the ``protogen`` equivalent to a protobuf EnumDescriptor. The enums
    attributes are obtained from the EnumDescriptor it is derived from and
    references to other ``protogen`` classes that have been resolved in the
    resolution process. It represents a Protobuf enum defined within an `.proto`
    file.

    Attributes
    ----------
    proto : google.protobuf.descriptor_pb2.EnumDescriptorProto
        The raw EnumDescriptor of the enum.
    py_ident : PyIdent
        Python identifier for the Python class of the enum.
    full_name : str
        Full proto name of the enum.
    parent_file : File
        The File the enum is declared in.
    parent : Message or None
        For nested enums, the message the enum is declared in. ``None`` otherwise.
    values : List[EnumValue]
        Values of the enum.
    location : Location
        Comments associated with the enum.
    """

    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.EnumDescriptorProto,
        parent_file: "File",
        parent: Optional["Message"],
        path: List[int],
    ):
        self.proto = proto
        if parent is None:
            self.full_name = parent_file.proto.package + "." + proto.name
            self.py_ident = parent_file.py_import_path.ident(proto.name)
        else:
            self.full_name = parent.full_name + "." + proto.name
            self.py_ident = parent.py_ident.py_import_path.ident(
                parent.py_ident.py_name + "." + proto.name
            )
        self.parent_file = parent_file
        self.parent = parent
        self.location = _resolve_location(parent_file.proto, path)
        # Add enum values.
        self.values: List[EnumValue] = []
        for i in range(len(proto.value)):
            value_path = path + [
                2,
                i,
            ]  # 2 is the field number for `value` in `EnumDescriptorProto`.
            self.values.append(EnumValue(proto.value[i], self, value_path))


def _is_map(message: "Message") -> bool:
    return (
        message.proto.HasField("options")
        and message.proto.options.HasField("map_entry")
        and getattr(message.proto.options, "map_entry")
    )


class Field:
    """A proto field.

    This is the ``protogen`` equivalent to a protobuf FieldDescriptor. The
    fields attributes are obtained from the FieldDescriptor it is derived from
    and references to other ``protogen`` classes that have been resolved in the
    resolution process. It represents a Protobuf field declared within a
    Protobuf message definition. It is also used to describe protobuf extensions.

    Attributes
    ----------
    proto : google.protobuf.descriptor_pb2.FieldDescriptorProto
        The raw FieldDescriptor of the field.
    py_name : str
        Python name of the field. This is a sanatized version of the original
        proto field name.
    full_name : str
        Full proto name of the field.
    parent : Message or None
        The message the field is declared in. Or ``None`` for top-level
        extensions.
    parent_file : File
        The file the field is declared in.
    oneof : OneOf or None
        The oneof in case the field is contained in a oneof. ``None`` otherwise.
    kind : Kind
        The field kind.
    cardinality : Cardinality
        Cardinality of the field.
    enum : Enum or None
        The enum type of the field in case the fields :attr:`kind` is
        :attr:`Kind.Enum`. ``None`` otherwise.
    message : Message or None
        The message type of the field in case the fields :attr:`kind` is
        :attr:`Kind.Message`. ``None`` otherwise.
    extendee : Message or None
        The extendee in case this is a top-level extension. ``None`` otherwise.
    location : Location
        Comments associated with the field.
    """

    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.FieldDescriptorProto,
        parent: Optional["Message"],
        parent_file: "File",
        oneof: Optional["OneOf"],
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
        self.message: Optional["Message"] = None
        self.enum: Optional["Enum"] = None

    def is_map(self) -> bool:
        """Whether the field is a map field.

        Returns
        -------
        bool
            ``True`` if the field is a map field. ``False`` otherwise.
        """
        if self.message is None:
            return False
        return _is_map(self.message)

    def is_list(self) -> bool:
        """Whether the field is a list field.

        A list fields has a :attr:`cardinality` of ``Cardinality.REPEATED`` and
        is not a map field.

        Returns
        -------
        bool
            ``True`` if the field is a list field. ``False`` otherwise.
        """
        return self.cardinality == Cardinality.REPEATED and not self.is_map()

    def map_key(self) -> Optional["Field"]:
        """Return the map key if the field is a map field.

        Returns
        -------
        Field or None
            The field of the map key if :meth:`is_map` is ``True``. ``None``
            otherwise.
        """
        if not self.is_map():
            return None
        return self.message.fields[0]

    def map_value(self) -> Optional["Field"]:
        """Return the map value if the field is a map field.

        Returns
        -------
        Field or None
            The field of the map value if :meth:`is_map` is ``True``. ``None``
            otherwise.
        """
        if not self.is_map():
            return None
        return self.message.fields[1]

    def _resolve(self, registry: Registry):
        # resolve extendee is present
        if self.proto.HasField("extendee"):
            self.extendee = _resolve_message_type_name(
                registry, self.full_name, self.proto.extendee
            )
            if self.extendee is None:
                raise ResolutionError(
                    file=self.parent_file.proto.name,
                    desc=self.full_name,
                    ref=self.proto.extendee,
                )

        # resolve the enum
        if self.kind == Kind.ENUM:
            if not self.proto.HasField("type_name"):
                raise InvalidDescriptorError(
                    full_name=self.full_name,
                    msg="is of kind ENUM but has no `type_name` set",
                )
            self.enum = _resolve_enum_type_name(
                registry, self.full_name, self.proto.type_name
            )
            if not self.enum:
                raise ResolutionError(
                    file=self.parent_file.proto.name,
                    desc=self.full_name,
                    ref=self.proto.type_name,
                )

        # resolve the message
        if self.kind == Kind.MESSAGE:
            if not self.proto.HasField("type_name"):
                raise InvalidDescriptorError(
                    full_name=self.full_name,
                    msg="is of kind MESSAGE but has no `type_name` set",
                )
            self.message = _resolve_message_type_name(
                registry, self.full_name, self.proto.type_name
            )
            if self.message is None:
                raise ResolutionError(
                    file=self.parent_file.proto.name,
                    ref=self.full_name,
                    type_name=self.proto.type_name,
                )


class OneOf:
    """A proto Oneof.

    This is the ``protogen`` equivalent to a protobuf OneofDescriptor. The
    oneofs attributes are obtained from the OneofDescriptor it is derived from
    and references to other ``protogen`` classes that have been resolved in the
    resolution process. It represents a Protobuf oneof declared within a
    Protobuf message definition.

    Attributes
    ----------
    proto : google.protobuf.descriptor_pb2.OneofDescriptorProto
        The raw OneofDescritor of the oneof.
    full_name : str
        Full proto name of the oneof.
    parent : Message
        The message the oneof is declared in.
    fields : List[Field]
        Fields that are part of the oneof.
    location : Location
        Comments associated with the oneof.
    """

    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.OneofDescriptorProto,
        parent: "Message",
        path: List[int],
    ):
        self.proto = proto
        self.full_name = parent.full_name + "." + proto.name
        self.parent = parent
        self.location = _resolve_location(parent.parent_file.proto, path)
        self.fields: List[Field] = []


Extension = Field
"""A protobuf extension.

Protobuf extensions are described using FieldDescriptors. See :class:`Field`.
"""


class Message:
    """A proto message.

    This is the ``protogen`` equivalent to a protobuf Descriptor. The messages
    attributes are obtained from the Descriptor it is derived from and
    references to other ``protogen`` classes that have been resolved in the
    resolution process. It represents a Protobuf message defined within an
    `.proto` file.

    Attributes
    ----------
    proto : google.protobuf.descriptor_pb2.DescriptorProto
        The raw Descriptor of the message.
    py_ident : PyIdent
        Python identifier for the Python class of the message.
    full_name : str
        Full proto name of the message.
    parent_file : File
        The file the message is defined in.
    parent : Message or None
        The parent message in case this is a nested message. ``None``, for
        top-level messages.
    fields : List[Field]
        Message field declarations. This includes fields defined within oneofs.
    oneofs : List[OneOf]
        Oneof declarations.
    enums : List[Enum]
        Nested enum declarations.
    messages List[Message]:
        Nested message declarations.
    extensions : List[Extension]
        Nested extension declations.
    location : Location
        Comments associated with the message.
    """

    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.DescriptorProto,
        parent_file: "File",
        parent: Optional["Message"],
        path: List[int],
    ):
        self.proto = proto
        self.py_ident = parent_file.py_import_path.ident(
            self.proto.name
        )  # TODO how to handle nested messages?
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
            # 8 is the number of oneof_decl in MessageDescriptorProto.
            oneof_path = path + [8, i]
            oneof = OneOf(proto.oneof_decl[i], self, oneof_path)
            self.oneofs.append(oneof)

        # Initialize Fields.
        self.fields: List[Field] = []
        for i in range(len(proto.field)):
            # 2 is the number of field in MessageDescriptorProto.
            field_path = path + [2, i]
            # In case that field belongs to a oneof, initialize it with that oneof.
            # The `oneof_index` indicates to which oneof the field belongs.
            if proto.field[i].HasField("oneof_index"):
                field = Field(
                    proto.field[i],
                    self,
                    parent_file,
                    self.oneofs[proto.field[i].oneof_index],
                    field_path,
                )
                self.oneofs[proto.field[i].oneof_index].fields.append(field)
                self.fields.append(field)
            else:
                field = Field(proto.field[i], self, parent_file, None, field_path)
                self.fields.append(field)

        # Initialize nested Messages.
        self.messages: List[Message] = []
        for i in range(len(proto.nested_type)):
            # 3 is the number of nested_type in MessageDescriptorProto.
            message_path = path + [3, i]
            message = Message(proto.nested_type[i], parent_file, self, message_path)
            self.messages.append(message)

        # Initialize nested Enums.
        self.enums: List[Enum] = []
        for i in range(len(proto.enum_type)):
            # 4 is the number of enum_type in MessageDescriptorProto.
            enum_path = path + [4, i]
            enum = Enum(proto.enum_type[i], parent_file, self, enum_path)
            self.enums.append(enum)

        # Initialize message Extensions.
        self.extension: List[Extension] = []
        for i in range(len(proto.extension)):
            # 6 is the number of extension in MessageDescriptorProto.
            extension_path = path + [6, i]
            extension = Field(
                proto.extension[i], self, parent_file, None, extension_path
            )
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

        # Remove autogenerated messages from the list of nested message.
        # Typically, no code should be generated for these.
        # TODO maybe make this configurable
        cleaned_messages = []
        for message in self.messages:
            if (
                message.proto.options.HasField("map_entry")
                and message.proto.options.map_entry
            ):
                continue
            cleaned_messages.append(message)
        self.messages = cleaned_messages


class ResolutionError(Exception):
    """Error raised when type or enum name can not be resolved.

    This error is raised if a reference to a message or enum could not be
    resolved.  References to messages and enum might be declared in
    MethodDescriptors or FieldDescriptors.

    Attributes
    ----------
    file : str
        The proto file that contains the descriptor that referes to a type that could not be resolved.
    desc : str
        The full name of the descriptor that holds the reference
    ref : str
        The type or enum reference that can not be resolved.
    """

    def __init__(self, file: str, desc: str, ref: str):
        msg = f'({file}: Failed to resolve "{ref}" from "{desc}".'
        super().__init__(msg)
        self.file = file
        self.desc = desc
        self.ref = ref


class InvalidDescriptorError(Exception):
    """Error raised when a descriptor is invalid.

    This error is raied if a descriptor is considered invalid. A descriptor
    might be considered invalid for various reasons. For example:
    * a FieldDescriptor may be of TYPE_ENUM but not declare a type_name
    * a FieldDescriptor may be of TYPE_MESSAGE but not declare a type_name
    """

    def __init__(self, full_name: str, msg: str):
        super().__init__(f"invalid descriptor error ({full_name}): {msg}")


class Method:
    """A proto service method.

    This is the ``protogen`` equivalent to a protobuf MethodDescriptor. The
    methods attributes are obtained from the MethodDescriptor it is derived from
    and references to other ``protogen`` classes that have been resolved in the
    resolution process. It represents a Protobuf method declared within a
    Protobuf service definition.

    Attributes
    ----------
    proto : google.protobuf.descriptor_pb2.MethodDescriptorProto
        The raw MethodDescriptor of the method.
    py_name : str
        Python name of the method. A snake cased version of the proto name.
    full_name : str
        Full proto name of the method.
    grpc_path :str
        The grpc path of the method. Derived from the service and method name:
        ``"/{service name}/{method name}"``
    parent : Service
        The service the method is declared in.
    input : Message
        The input message of the method.
    output : Message
        The output message of the method.
    location : Location
        Comments associated with the method.
    """

    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.MethodDescriptorProto,
        parent: "Service",
        path: List[int],
    ):
        self.proto = proto
        self.py_name = protogen._case.snake_case(proto.name)
        self.full_name = parent.full_name + "." + proto.name
        self.grpc_path = "/" + parent.full_name + "/" + proto.name
        self.parent = parent
        # input (needs to be resolved)
        # output (needs to be resolved)
        self.location = _resolve_location(parent.parent_file.proto, path)

    def _resolve(self, registry: Registry):
        self.input = _resolve_message_type_name(
            registry, self.full_name, self.proto.input_type
        )
        if self.input is None:
            raise ResolutionError(
                file=self.parent.parent_file.proto.name,
                desc=self.full_name,
                ref=self.proto.input_type,
            )
        self.output = _resolve_message_type_name(
            registry, self.full_name, self.proto.output_type
        )
        if self.output is None:
            raise ResolutionError(
                file=self.parent.parent_file.proto.name,
                desc=self.full_name,
                ref=self.proto.output_type,
            )


class Service:
    """A proto service.

    This is the ``protogen`` equivalent to a protobuf ServiceDescriptor. The
    services attributes are obtained from the ServiceDescriptor it is derived
    from and references to other ``protogen`` classes that have been resolved in
    the resolution process. It represents a Protobuf service defined within an
    `.proto` file.

    Attributes
    ----------
    proto : google.protobuf.descriptor_pb2.ServiceDescriptorProto
        The raw ServiceDescriptor of the service.
    py_ident : PyIdent
        Python identifier for the Python class of the service.
    full_name : str
        Full proto name of the service.
    parent_file : File
        The file the Service is defined in.
    methods : List[Method]
        Service method declarations.
    location : Location
        Comments associated with the service.
    """

    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.ServiceDescriptorProto,
        parent: "File",
        path: List[int],
    ):
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
    """A proto file.

    This is the ``protogen`` equivalent to a protobuf FileDescriptor. The files
    attributes are obtained from the FileDescriptor it is derived from and
    references to other ``protogen`` classes that have been resolved in the
    resolution process. It represents a Protobuf file (`.proto` file).

    Attributes
    ----------
    proto : google.protobuf.descriptor_pb2.FileDescriptorProto
        The raw FileDescriptor of the file.
    generated_filename_prefix : str
        Name of the original proto file (without ``.proto`` extension).
    py_package_name : str
        Name of the proto package the file belongs to. This is the result of the
        proto package name of the proto file applied to the ``py_import_function``
        of the ``Plugin`` that is used to read the file.
    py_import_path : PyImportPath
        Import path for the file.
    generate : bool
        Whether Python code should be generated for the file.
    dependencies : List[File]
        Files imported by the file.
    enums : List[Enum]
        Top-level enum declarations.
    messages : List[Message]
        Top-level message declarations.
    services : List[Service]
        Service declarations.
    extensions List[Extension]
        Top-level extension declarations.
    """

    def __init__(
        self,
        proto: google.protobuf.descriptor_pb2.FileDescriptorProto,
        generate: bool,
        py_import_func: Callable[[str, str], str],
    ):
        self.proto = proto
        self.generated_filename_prefix = proto.name[: -len(".proto")]
        # The actual pyton path is determined using the py_import_func.
        # TODO maybe require the rewrite func to return a Python file and
        # then generate the import path from that python filename
        self.py_import_path = PyImportPath(py_import_func(proto.name, proto.package))
        self.py_package_name = str(proto.package)
        self.generate = generate
        self.dependencies: List[File] = []

        self.messages: List[Message] = []
        for i in range(len(proto.message_type)):
            # 4 is the number of the message_type in the FileDescriptorProto.
            path = [4, i]
            message = Message(proto.message_type[i], self, None, path)
            self.messages.append(message)

        self.enums: List[Enum] = []
        for i in range(len(proto.enum_type)):
            # 5 is the number of the enum_type in the FileDescriptorProto.
            path = [5, i]
            enum = Enum(proto.enum_type[i], self, None, path)
            self.enums.append(enum)

        self.services: List[Service] = []
        for i in range(len(proto.service)):
            # 6 is the number of the service in the FileDescriptorProto.
            path = [6, i]
            service = Service(proto.service[i], self, path)
            self.services.append(service)

        self.extensions: List[Extension] = []
        for i in range(len(proto.extension)):
            # 7 is the number of the extension in the FileDescriptorProto.
            path = [7, i]
            extension = Extension(proto.extension[i], None, self, None, path)
            self.extensions.append(extension)

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
    """An output buffer to write generated code to.

    A generated file is a buffer. New lines can be added to the output buffer by
    calling :func:`P`.

    Additionally, the generated file provides mechanism for handling Python
    imports.  Internally it maintains a list of :class:`PyImportPath` s that are
    requested to be imported.  Use :meth:`print_imports` to mark the position in
    the output buffer the imports will be printed at.

    To create a new instance of a generated file use
    :meth:`Plugin.new_generated_file`. :meth:`Plugin.new_generated_file`
    requires a ``filename`` and a ``py_import_path`` as parameter.  The
    ``filename`` is obviously the name of the file to be created.  The
    ``py_import_path`` is used for *import resolution*. It specifies the Python
    module the generated file is representing.

    When calling :meth:`qualified_py_ident` the generated files import path is
    compared to the import path of the Python identifier that is passed as an
    argument.  If they refer to different Python modules, the
    :class:`PyImportPath` of the argument is added to the list of imports of the
    generated file.  Note that also :meth:`P` calls :meth:`qualified_py_ident`,
    so the above also applies to :class:`PyIdent` arguments passed to :meth:`P`.

    Attributes
    ----------
    name : str
        Name of the generated file.
    """

    def __init__(
        self,
        name: str,
        py_import_path: PyImportPath,
    ):
        self.name = name
        self._py_import_path = py_import_path
        self._buf: List[str] = []
        self._import_mark = -1
        # Set of imports. Will be rewritten using the py_import_func before
        # added to the set.
        self._imports: Set[PyImportPath] = set()
        self._indent = 0

    def set_indent(self, level: int) -> int:
        """Set the indentation level.

        Set the indentation level such that consecutive calls to :func:`P` are
        indented automatically to that level.

        Arguments
        ---------
        level : int
            The new indentation level.

        Returns
        -------
        int
            The old indentation level.

        Raises
        ------
        ValueError
            If level is less than zero.

        Example
        -------
        >>> g.P("class MyClass:")
        >>> reset = g.set_indent(4)
        >>> g.P("def __init__():")
        >>> g.P("    pass")
        >>> g.set_indent(reset)
        """
        if level < 0:
            raise ValueError("indent must be greater or equal zero")
        old = self._indent
        self._indent = level
        return old

    def P(self, *args):
        """Add a new line to the output buffer.

        Add a new line to the output buffer containing a stringified version of
        the passed arguments.  For arguments that are of class :class:`PyIdent`
        :meth:`qualified_py_ident` is called. This will add the import path to
        the generated files import list and write the fully qualified name of
        the Python identifier, if necessary.

        Arguments
        ---------
        *args
            Items that make up the content of the new line. All args are printed
            on the same line. There is no whitespace added between the
            individual args.
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

    def qualified_py_ident(self, ident: PyIdent) -> str:
        """Obtain the qualified Python identifier name with respect to the generated file.

        If ``ident.py_import_path`` and the :attr:`import_path` of the generated
        file refer to different Python modules, the ``ident.py_import_path``
        will be added to the list of imports of the generated file and the fully
        qualified name of `ident` will be returned.
        If ``ident.py_import_path`` and the :attr:`import_path` of the generated
        file refer to the same Python module, the ``ident.py_name`` will be
        returned and nothing will be added to the list of imports of the
        generated file.

        Arguments
        ---------
        ident : PyIdent
            The identifier to obtain the qualified name for.

        Returns
        -------
        str
            The qualified identifier name.
        """
        if ident.py_import_path == self._py_import_path:
            return ident.py_name
        else:
            self._imports.add(ident.py_import_path)
            return ident.py_import_path._path + "." + ident.py_name

    def print_import(self):
        """Set the mark to print the imports in the output buffer.

        The current location in the output buffer will be used to print the
        imports collected by :meth:`qualified_py_ident`. Only one location can
        be set. Consecutive calls will overwrite previous calls.

        Example
        -------
        >>> g.P("# My python file")
        >>> g.P()
        >>> g.print_imports()
        >>> g.P()
        >>> g.P("# more content following after the imports..")
        """
        self._import_mark = len(self._buf)

    def _proto(self) -> google.protobuf.compiler.plugin_pb2.CodeGeneratorResponse.File:
        if self._import_mark > -1:
            lines = (
                self._buf[: self._import_mark]
                + [f"import {p._path}" for p in self._imports]
                + self._buf[self._import_mark :]
            )
        else:
            lines = self._buf
        content = "\n".join(lines)
        # TODO can we run yapf here?
        return google.protobuf.compiler.plugin_pb2.CodeGeneratorResponse.File(
            name=self.name,
            content=content,
        )


class Plugin:
    """An invocation of a protoc plugin.

    Provides access to the resolved ``protogen`` classes as parsed from the
    CodeGeneratorRequest read from protoc and is used to create a
    CodeGeneratorResponse that is returned back to protoc.
    To add a new generated file to the response, use :meth:`new_generated_file`.

    Attributes
    ----------
    parameter : Dict[str, str]
        Parameter passed to the plugin using ``{plugin name}_opt=<key>=<value>`
        or ``<plugin>_out=<key>=<value>`` command line flags.
    files_to_generate : List[File]
        Set of files to code generation is request for. These are the files
        explictly passed to protoc as command line arguments.
    """

    def __init__(
        self,
        parameter: Dict[str, str],
        files_to_generate: List[File],
    ):
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

    def new_generated_file(
        self, name: str, py_import_path: PyImportPath
    ) -> GeneratedFile:
        """Create a new generated file.

        The generated file will be added to the output of the plugin.

        Arguments
        ---------
        name : str
            Filename of the generated file.
        py_import_path : PyImportPath
            Python import path of the new generated file. This is used to decide
            whether to print the fully qualified name or the simple name for a
            Python identifier when using `GeneratedFile.P`. See
            :class:`GeneratedFile`.

        Returns
        -------
        GeneratedFile
            The new generated file.
        """
        g = GeneratedFile(name, py_import_path)
        self._generated_files.append(g)
        return g

    def error(self, msg: str):
        """Record an error.

        The error will be reported back to protoc. No output will be produced in
        case of an error.  produce any output. Will act as a no-op for
        consecutive calls; only the first error is reported back.

        Arguments
        ---------
        msg : str
            Error message to report back to protoc. This will appear on the
            command line when the error is displayed.
        """
        if self._error is None:
            self._error = msg


def default_py_import_func(filename: str, package: str) -> str:
    """Return the Python import path for a file.

    Return the Python import path for a file following the behaviour of the
    offical Python protoc plugin that generates for each input file
    `path/to/file.proto` a corresponding `path/to/file_pb2.py` file.  This
    function is used as the default ``py_import_func`` parameter in
    :func:``Options.__init__``.

    Arguments
    ---------
    filename : str
        Filename of the proto file to request the import path for.
    package : str
        Proto package name of the file to request the import path for.

    Returns
    -------
    str
        The Python import path for the file.

    Example
    -------
    >>> default_py_import_func("google/protobuf/field_mask.proto", "google.protobuf")
    "google.protobuf.field_mask_pb2"
    """
    return filename.replace(".proto", "_pb2").replace("/", ".")


class Options:
    """Options for resolving a raw CodeGeneratorRequest to ``protogen`` classes.

    In the resolution process, the raw FileDescriptors, Descriptors,
    ServiceDescriptors etc. that are contained in the CodeGeneratorRequest
    provided by protoc are turned into their corresponding ``protogen`` classes
    (:class:`File`, :class:`Message`, :class:`Service`).

    Use :meth:`run` to run a code generation function.
    """

    def __init__(
        self,
        *,
        py_import_func: Callable[[str, str], str] = default_py_import_func,
        input: BinaryIO = sys.stdin.buffer,
        output: BinaryIO = sys.stdout.buffer,
    ):
        """Create options for the resolution process.

        Arguments
        ---------
        py_import_func : Callable[[str, str], str], optional
            Defines how to derive :class:`PyImportPath` for the :class:`File`
            objects in the resolution process. This also influences the
            :class:`PyIdent` attributes that are part of :class:`Message`,
            :class:`Enum`, and :class:`Service` classes as their import paths
            are inherited from the :class:`File` they are defined in.  Defaults
            to use :func:`default_py_import_func`.
        input : BinaryIO, optional
            The input stream to read the CodeGeneratorRequest from. Defaults
            to :attr:`sys.stdin.buffer`.
        output : BinaryIO, optional
            The output stream to write the CodeGeneratorResponse to.
            Defaults to :attr:`sys.stdout.buffer`.
        """
        self._input = input
        self._output = output
        self._py_import_func = py_import_func

    def run(self, f: Callable[[Plugin], None]):
        """Start resolution process and run ``f`` with the :class:`Plugin` containing the resolved classes.

        run waits for protoc to write the CodeGeneratorRequest to
        :attr:`input`, resolves the raw FileDescriptors, Descriptors,
        ServiceDescriptors etc. contained in it to their corresponding
        ``protogen`` classes and creates a new :class:`Plugin` with the resolved
        classes.
        ``f`` is then called with the :class:`Plugin` as argument. Once ``f``
        returns, :class:`Options` will collect the CodeGeneratorResponse from
        the :class:`Plugin` that contains information of all
        :class:`GeneratedFile` s that have been created on the plugin. The
        response is written to :attr:`output` for protoc to pick it up. protoc
        writes the generated files to disk.

        Arguments
        ---------
        f : Callable[[Plugin], None]
            Function to run with the Plugin containing the resolved classes.
        """
        req = google.protobuf.compiler.plugin_pb2.CodeGeneratorRequest.FromString(
            self._input.read()
        )

        # Parse parameters. These are given as flags to protoc:
        #
        #   --plugin_opt=key1=value1
        #   --plugin_opt=key2=value2,key3=value3
        #   --plugin_opt=key4,,,
        #   --plugin_opt=key5:novalue5
        #   --plugin_out=key6:./path
        #
        # Multiple in one protoc call are possible. All `plugin_opt`s are joined
        # with a "," in the CodeGeneratorRequest. The equal sign actually has no
        # special meaning, its just a convention.
        #
        # The above would result in a parameter string of
        #
        #   "key1=value1,key2=value2,key3=value3,key4,,,,key5:novalue5,key6"
        #
        # (ignoring the order).
        #
        # Follow the convention of parameters pairs separated by commans in the
        # form {k}={v}. If {k} (without value), write an empty string to the
        # parameter dict. For {k}={v}={v2} write {k} as key and {v}={v2} as
        # value.
        parameter: Dict[str, str] = {}
        for param in req.parameter.split(","):
            if param == "":
                # Ignore empty parameters.
                continue
            splits = param.split("=", 1)  # maximum one split
            if len(splits) == 1:
                k, v = splits[0], ""
            else:
                k, v = splits
            parameter[k] = v

        # Resolve raw proto descriptors to their corresponding protogen classes.
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
