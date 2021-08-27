# `protogen`

Package `protogen` makes writing `protoc` plugins easier.
Working with the raw protobuf descriptor messages can be cumbersome.
`protogen` resolves and links the dependencies and references between the raw Protobuf descriptors and turns them into their corresponding `protogen` classes that are easier to work with.
It also provides mechanisms that are espacially useful to generate Python code like dealing with Python imports.

## Installation

Package `protogen` is available via `pip`. To install run:

```
pip install protogen
```

## API

Most classes in `protogen` are simply replacements of their corresponding Protobuf descriptors: `protogen.File` represents a FileDescriptor, `protogen.Message` a Descriptor, `protogen.Field` a FieldDescriptor and so on. They should be self explanatory. You can read their docstrings for more information about them.

The classes `protogen.Options`, `protogen.Plugin` and `protogen.GeneratedFile` make up a framework to generate files.
You can see these in action in the following example plugin:

```python
#!/usr/bin/env python
"""An example plugin."""

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
            for ff in m.fields:
                # ...
        for s in f.services:
            g.P("class ", s.py_ident, ":")
            for m in f.methods:
                g.P("  def ", m.py_name, "(request):")
                g.P("    pass")

if __name__ == "__main__":
    opts = protogen.Options()
    opts.run(generate)
```

## class `protogen.Options`

The `protogen.Options` class can be used to specify options for the resolution process (resolution from plain proto descriptors to `protogen` classes).
`Option.run(f: func(Plugin))` waits for `protoc` to write the CodeGeneratorRequest to `stdin`, resolves the descriptors contained in it to their corresponding `protogen` classes and initializes a new `Plugin` with the resolved classes.  
`f` is then called with the `Plugin` as argument.

Once `f` returns, `Options` will collect the CodeGeneratorResponse from the `Plugin` that contains the all created `GeneratedFile`s and write it to `stdout` for `protoc` to pick it up.
`protoc` writes the generated files to disk.

## class `protogen.Plugin`

The `Plugin` class holds the files code generation is requested for in the `Plugin.files_to_generate` attribute. These are the files that were provided as command line arguments to `protoc`.
Any options/parameters passed to the plugin via the `protoc --plugin_opt=<param>` command line flag are accessible via `Plugin.parameter`.
With `Plugin.new_generated_file` a new `GeneratedFile` gets created that is automatically added to the CodeGeneratorResponse of the plugin.
Typically, but not necessarily, one file for each file in `Plugin.files_to_generate` is created.

## class `protogen.GeneratedFile`

The `GeneratedFile` is just a buffer you can add lines to using the `g.P` (print) method.
A `GeneratedFile` is created with `Plugin.new_generated_file(filename, py_import_path)`.
The `filename` is obviously the name of the file to be created.
The `py_import_path` is used for *import resolution*.

Note that the following assumes the plugin generates Python code. For other kinds of plugins, the following is not relevant:

It is often necessary to import Python identifiers that are defined in different Python modules.
For example, a Protobuf messages might reference `google.protobuf.Timestamp` in one of its fields.
The corresponding Python class `google.protobuf.timestamp_pb2.Timestamp` needs to be imported before its mentioned in the generated code.

The `protogen.PyImportPath` class represent a Python import path. Is just a wrapper around an import path (for example `"google.protobuf.timestamp_pb2"`).
The `PyIdent` class represent a Python identifier. It holds a `PyImportPath` together with a name (e.g. a class name like `"Timestamp"`).

The `protogen.GeneratedFile` provides mechanisms to handle Python imports.
Internally it maintains a list of `PyImportPath`s that it needs to import.
`PyImportPaths` might be added to this list implictly when calling `GeneratedFile.P(*args)` or rather explicitly when calling `GeneratedFile.qualified_py_ident(PyIdent)`.
When any of the arguments to `GeneratedFile.P` is a `protogen.PyIdent`, the `py_import_path` of the `GeneratedFile` gets compared to the arguments `PyIdent.py_import_path`. 

If they are from different Python modules, the arguments import path will be added to the list of imports and the fully qualified name of the `PyIdent` will be printed. 

If both files are from the same `PyImportPath`, then the import path is not added to the list of imports. In that case it is sufficient to reference the `PyIdent` by its simple name (e.g. `Timestamp`), thus only the `PyIdent.py_name` will be printed.

To place the import statements in the buffer of the `GeneratedFile` use `GeneratedFile.print_imports`. This will put a line `"import <path>"` for each `PyImportPath` that the generated file needs to import (e.g `"import google.protobuf.timestamp_pb2"`) in the buffer.

The following example shows how the `GeneratedFile.P` function behaves for different `PyImportPaths`::

```python
# g is of type protogen.GeneratedFile
# message_a and message_b are of type protogen.Message

>>> g.py_import_path
{ "mypackage.mymodule" }

>>> message_a.py_ident
{ py_import_path: "google.protobuf.timestamp_pb2", py_name: "Timestamp" }
>>> g.P("hello ", message_a.py_ident) 
# adds "hello google.protobuf.timestamp_pb2.Timestamp" to g's line buffer and "google.protobuf.timestamp_pb2" to the imports

>>> message_b.py_ident
{ py_import_path: "mypackage.mymodule", py_name: "MyMessage" }
>>> g.P("hello ", message_b.py_ident) 
# adds "hello MyMessage" to g's line buffer (and nothing to the imports)
```

Note that you can provide a custom `py_import_func` in the `Options` constructor.
This function is used in the resolution process to calculate the `PyImportPath` for `protogen.File`s.
`protogen.Message`s, `protogen.Service`s and `protogen.Enum`s inherit the `PyImportPath` (that is part of their `PyIdent`) from the file they are defined in.
By default the `protogen.default_py_import_func` is used. 
It is compatible with the style of the offical Python `protoc` plugin that generates for each input file `path/to/file.proto` a corresponding `path/to/file_pb2.py` file.

For example, assume you know that code generation for proto definitions that are part of the `mypackage.**` proto package happens with a `protoc` plugin that generates one `.py` file per proto package. 
That `plugin` also omits the `_pb2` suffix.
For the proto package `mypackage.api.a`, that might contain any number of files, it creates a `mypackage/api/a.py` file.
For the proto package `mypackage.api.b`, a `mypackage/api/b.py` file.

A `py_import_func` describing this would be:

```python
def py_import_func(
    proto_filename: str, 
    proto_package:str,
) -> protogen.PyImportPath:
    if proto_package.split(".")[0] == "mypackage":
        # Python import path is simply the package name.
        return protogen.PyImportPath(proto_package) 
    # For every other package, assume its generated with the offical Python plugin.
    return protogen.default_py_import_func(proto_filename, proto_package)
```

# Misc

## What is a protoc plugin anyway?

`protoc`, the **Proto**buf **c**ompiler, is used to generate code derived from Protobuf definitions (`.proto` files).
Under the hood, `protoc`'s job is to read and parse the definitions into their *Descriptor* types (see [google/protobuf/descriptor.proto](https://github.com/protocolbuffers/protobuf/blob/4f49062a95f18a6c7e21ba17715a2b0a4608151a/src/google/protobuf/descriptor.proto)).
When `protoc` is run (with a plugin) it creates a CodeGeneratorRequest (see [google/protobuf/compiler/plugin.proto#L68](https://github.com/protocolbuffers/protobuf/blob/4f49062a95f18a6c7e21ba17715a2b0a4608151a/src/google/protobuf/compiler/plugin.proto#L68)) that contains the descriptors for the files to generate and everything they import and passes it to the plugin via `stdin`.

A *protoc plugin* is an executable. It reads the CodeGeneratorRequest from `stdin` and returns a CodeGeneratorResponse (see [google/protobuf/compiler/plugin.proto#L99](https://github.com/protocolbuffers/protobuf/blob/4f49062a95f18a6c7e21ba17715a2b0a4608151a/src/google/protobuf/compiler/plugin.proto#L99)) via `stdout`.
The plugin can use the descriptors from the CodeGeneratorRequest to create output files (in memory).
It returns these output files (consisting of name and content as string) in the CodeGeneratorResponse to `protoc`.

`protoc` then writes these files to disk.

## Run `protoc` with your plugin

Assume you have an executable plugin under `path/to/plugin/main.py`.
You can invoke it via:

```
protoc 
    --plugin=protoc-gen-myplugin=path/to/plugin/main.py \
    --plugin_out=./output_root \
    myproto.proto myproto2.proto
```

Caveats:
- you must use the `--plugin=protoc-gen-<plugin_name>` prefix, otherwise `protoc` fails with "plugin not executable"
- your plugin must be executable (`chmod +x path/to/plugin/main.py` and put a `#!/usr/bin/env python` at the top of the file)

# See also

- if you want to write protoc plugins with JavaScript/TypeScript: [github.com/fischor/protogen-javascript](https://github.com/fischor/protogen-javascript)
- if you want to write protoc plugins with Golang: [google.golang.org/protobuf/compiler/protogen](https://google.golang.org/protobuf/compiler/protogen)

# Credits

This package is inspired by the [google.golang.org/protobuf/compiler/protogen Golang](https://pkg.go.dev/google.golang.org/protobuf@v1.27.1/compiler/protogen) package.
