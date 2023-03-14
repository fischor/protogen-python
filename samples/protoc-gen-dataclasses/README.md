# protoc-gen-dataclasses sample plugin

This sample demonstrates the use of `py_import_func` and shows how to signal support for and handle proto3 optionals.

## Run

Ensure a folder called `output_root` exists:

```
mkdir output_root
rm -r output_root/acme
```

generate

```sh
protoc \
    --plugin=protoc-gen-dataclasses=samples/protoc-gen-dataclasses/plugin.py \
    --dataclasses_out=output_root \
    --proto_path samples/protos \
    samples/protos/acme/**/*.proto
`` 
