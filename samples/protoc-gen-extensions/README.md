# protoc-gen-extensions sample

This sample shows how to use proto3 extensions (`MethodOptions` more specifically) and the `protogen.Registry` to resolve messages.

## Run

For a plugin that uses extensions the extension needs to be generated first using the official protoc python compiler.
This is necessary for the corresponding options that use e.g. in `samples/protos/acme/library/v1/library.proto` to be present and accessible for the example plugin.
Generate python code for at least the file where the extension resides in and all its dependencies with the official Python protoc plugin.

```sh
protoc --proto_path=samples/protos --python_out=. samples/protos/acme/longrunning/operations.proto samples/protos/acme/protobuf/any.proto
`` 

Ensure a folder called `output_root` exists:

```
mkdir output_root
rm -r output_root/acme
```

Then run plugin.

```sh
protoc --plugin=protoc-gen-extensions=samples/protoc-gen-extensions/plugin.py --extensions_out=output_root -I samples/protos samples/protos/acme/**/*.proto
`` 

