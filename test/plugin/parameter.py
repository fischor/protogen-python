#!/usr/bin/env python
"""A test plugin.

Plugin to test that parameters are read in correctly.
It simply prints the parameters it received in a out.txt file.
"""

import protogen


def generate(gen: protogen.Plugin):
    g = gen.new_generated_file("out.txt", protogen.PyImportPath(""))
    # Write sorted by key.
    for k, v in [(k, gen.parameter[k]) for k in sorted(gen.parameter.keys())]:
        g.P(k, "->", v)


opts = protogen.Options()
opts.run(generate)
