#!/usr/bin/env python
"""A test plugin."""

from typing import List, Union
import protogen


def generate(gen: protogen.Plugin):
    for f in gen.files_to_generate:
        g = gen.new_generated_file(
            f.generated_filename_prefix + ".out", f.py_import_path
        )
        g.P("# Generated code output.")
        g.P()

        g.P("dependencies:")
        for dep in f.dependencies:
            g.P("- name: ", dep.proto.name)
            g.P("  num_dependencies: ", len(dep.dependencies))
            g.P("  num_messages: ", len(collect_messages(dep)))
            g.P("  num_enums: ", len(collect_enums(dep)))
            g.P("  num_services: ", len(dep.services))
            g.P("  num_extensions: ", len(dep.extensions))
        g.P()

        g.P("messages:")
        for m in f.messages:
            generate_message(g, m, 0)
        g.P()

        g.P("enums:")
        for e in f.enums:
            generate_enum(g, e, 0)
        g.P()

        g.P("services:")
        for s in f.services:
            generate_service(g, s)
        g.P()

        g.P("extensions:")
        for e in f.extensions:
            generate_extensions(g, e)


def generate_message(g: protogen.GeneratedFile, message: protogen.Message, lvl: int):
    reset = g.set_indent(lvl)
    g.P("- name: ", message.full_name)

    g.P("  fields:")
    for f in message.fields:
        g.P("  - name: ", f.full_name)
        g.P("    message: ", "None" if not f.message else f.message.full_name)
        g.P("    enum: ", "None" if not f.enum else f.enum.full_name)

    g.P("  messages:")
    for m in message.messages:
        generate_message(g, m, lvl + 2)

    g.P("  enums:")
    for e in message.enums:
        generate_enum(g, e, lvl + 2)

    g.set_indent(reset)


def generate_enum(g: protogen.GeneratedFile, e: protogen.Enum, lvl: int):
    reset = g.set_indent(lvl)
    g.P("- name: ", e.full_name)
    g.P("  values:")
    for v in e.values:
        g.P("  - name: ", v.full_name)

    g.set_indent(reset)


def generate_service(g: protogen.Service, s: protogen.Service):
    g.P("- name: ", s.full_name)
    g.P("  methods:")
    for m in s.methods:
        g.P("  - name: ", m.full_name)
        g.P("    input: ", m.input.full_name)
        g.P("    output: ", m.output.full_name)
        g.P("    client_streaming: ", m.proto.client_streaming)
        g.P("    server_streaming: ", m.proto.server_streaming)
        g.P("    path: ", m.grpc_path)


def generate_extensions(g: protogen.GeneratedFile, e: protogen.Extension):
    g.P("- name: ", e.full_name)
    g.P("  extendee: ", e.extendee.full_name)
    g.P("  message: ", "None" if not e.message else e.message.full_name)
    g.P("  enum: ", "None" if not e.enum else e.enum.full_name)


def collect_messages(
    fm: Union[protogen.File, protogen.Message]
) -> List[protogen.Message]:
    messages = []
    for m in fm.messages:
        messages.append(m)
        messages.extend(collect_messages(m))
    return messages


def collect_enums(fm: Union[protogen.File, protogen.Message]) -> List[protogen.Enum]:
    enums = []
    enums.extend(fm.enums)
    for m in fm.messages:
        enums.extend(collect_enums(m))
    return enums


opts = protogen.Options()
opts.run(generate)
