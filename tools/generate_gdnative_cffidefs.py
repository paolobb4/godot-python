#! /usr/bin/env python3

import argparse
import re
from os import path
from pycparser import parse_file, c_ast, c_generator
from pycparser.c_ast import Constant


BASEDIR = path.dirname(path.abspath(__file__))


# CFFI cannot parse enum value that are not just number (e.g.
# `GODOT_BUTTON_MASK_LEFT = 1 << (GODOT_BUTTON_LEFT - 1)`), so we have
# to do the computation here.
class CookComplexEnumsVisitor(c_ast.NodeVisitor):

    def visit_Enum(self, node):
        if not node.values:
            return
        generator = c_generator.CGenerator()
        for i, elem in enumerate(node.values.enumerators):
            if not elem.value:
                continue
            try:
                raw_val = generator.visit(elem.value)
                for item in node.values.enumerators:
                    try:
                        if item.value and item.value.type == 'int':
                            raw_val = raw_val.replace(item.name, item.value.value)
                    except:
                        pass
                cooked_value = eval(raw_val)
                elem.value = Constant(type='int', value=str(cooked_value))
            except:
                pass


def _generate_cdef(gdnative_include, bits, cpp):
    header = '%s/gdnative_api_struct.gen.h' % gdnative_include
    cpp_path, *cpp_args = cpp.split()
    cpp_args += [
        '-D__attribute__(x)=',
        '-I' + gdnative_include,
        '-I%s/fake_libc_include' % BASEDIR
    ]
    ast = parse_file(header, use_cpp=True, cpp_path=cpp_path, cpp_args=cpp_args)
    v = CookComplexEnumsVisitor()
    v.visit(ast)
    generator = c_generator.CGenerator()
    splitted_src = generator.visit(ast).split('\n')
    # First lines are typedefs not related with godot creating compile time errors
    first_line = next(i for i, line in enumerate(splitted_src) if 'godot' in line.lower())
    src = splitted_src[first_line:]
    # CFFI cannot parse sizeof, so we have to processe it here
    wordsize = str(8 if bits == '64' else 4)
    src = [re.sub(r'sizeof *\(void *\*\)', wordsize, l) for l in src]
    return '\n'.join(
        [
            '/********************************************************/',
            '/* AUTOGENERATED by tools/generate_gdnative_cffidefs.py */',
            '/********************************************************/',
        ] + src
    )


def generate_cdef(output, gdnativedir, bits, cpp):
    with open(output, 'w') as fd:
        fd.write(_generate_cdef(gdnativedir, bits, cpp))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate cdef.gen.h file (needed to generate'
                                                 ' CFFI bindings) from the GDnative headers.')
    parser.add_argument('gdnative', help='Path to Godot GDnative folder')
    parser.add_argument('--output', '-o', default='cdef.gen.h')
    parser.add_argument('--bits', '-b', choices=['32', '64'], default='64')
    parser.add_argument('--cpp', help='Preprocessor command', default='cpp')
    args = parser.parse_args()
    generate_cdef(args.output, args.gdnative, args.bits, args.cpp)
