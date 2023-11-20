# protoc-gen-extensions sample

This sample shows how to use proto3 extensions (`MethodOptions` more specifically) and the `protogen.Registry` to resolve messages.

## How to access extensionn values

This example works with the following `MethodOption` extension that can be found in [../protos/acme/longrunning/operations.proto](../protos/acme/longrunning/operations.proto):

```proto
extend google.protobuf.MethodOptions { OperationInfo operation_info = 1049; }

message Operation {
  string name = 1;
  acme.protobuf.Any metadata = 2;
  bool done = 3;
  oneof result {
    string error = 4;
    acme.protobuf.Any response = 5;
  }
}

message OperationInfo {
  string response_type = 1;
  string metadata_type = 2;
}
```

Note that the extension is a `MethodOption` extension and that field number `1049` was assigned to it.
The extension is used on methods like this, see [../protos/acme/library/v1/library.proto](../protos/acme/library/v1/library.proto):

```proto
service Library {
  rpc WriteBook(WriteBookRequest) returns (acme.longrunning.Operation) {
    option (acme.longrunning.operation_info) = {
      response_type : "WriteBookResponse"
      metadata_type : "acme.protobuf.Empty"
    };
  }
}
````

For a plugin that should recognize this extensions the extension proto file and its dependencies need to be generated first using the official protoc python compiler.
Generate python code for at least the file where the extension resides in and all its dependencies with the official Python protoc plugin:

```sh
protoc --proto_path=samples/protos --python_out=. samples/protos/acme/longrunning/operations.proto samples/protos/acme/protobuf/any.proto
```

This will generate several files, including `acme/longrunning/operations_pb2.py` that holds the definition of the `OperationInfo` extension.

```
OPERATION_INFO_FIELD_NUMBER = 1049
operation_info = _descriptor.FieldDescriptor(
  name='operation_info', full_name='trainai.longrunning.operation_info', index=0,
  number=1049, type=11, cpp_type=10, label=1,
  has_default_value=False, default_value=None,
  message_type=None, enum_type=None, containing_type=None,
  is_extension=True, extension_scope=None,
  serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key)
```

In the plugin, import the Python module that defines the extension. 
This should happen before the request from protoc is read (place it somewhere in the beginning of your plugin to be on the safe side).

```
import acme.longrunning.operations_pb2

# Somewhere after run your plugin.
protogen.Options(...).run(_generate)
```

The import will cause the registration of the extension in the oroto type registry of the offical `protobuf` lib. 
With that the extension values can be accessed by the plugin.
Each options added to a proto Method will be present as a field its `Method.proto.options`.
Each `Method.proto.option` has a `number` field that corresponds to the field number that was assigned to the extension.
This way one can identify to which extension a `Method.proto.option` belongs.
See (Line 24 and 25)[./samples/protoc-gen-extensions/plugin.py#L24-L25] in the example plugin.

The mechanism to access options for proto Messages, Fields etc. is similar.

## Run the plugin

Ensure a folder called `output_root` exists:

```
mkdir output_root
rm -r output_root/acme
```

Then run plugin.

```sh
protoc --plugin=protoc-gen-extensions=samples/protoc-gen-extensions/plugin.py --extensions_out=output_root -I samples/protos samples/protos/acme/**/*.proto
```

## Documentation



