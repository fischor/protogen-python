# protoc-gen-empty sample

This is a basic example of a protoc plugin.

## Run

Ensure a folder called `output_root` exists:

```
mkdir output_root
rm -r output_root/acme
```

Generate code for the `samples/protos` protobuf definitions with the protoc-gen-empty plugin:

```sh
protoc \
    --plugin=protoc-gen-empty=samples/protoc-gen-empty/plugin.py \
    --empty_out=output_root \
    --proto_path samples/protos \
    samples/protos/acme/**/*.proto
`` 
