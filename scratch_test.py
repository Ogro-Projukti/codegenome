from codegenome.parser import SourceParser
import tree_sitter_python
from tree_sitter import Language, Parser

parser = SourceParser()
p_internal = parser._parsers['python']
print("Internal parser:", p_internal, getattr(p_internal, 'language', None))

lang = Language(tree_sitter_python.language())
p_manual = Parser(lang)
print("Manual parser:", p_manual, getattr(p_manual, 'language', None))

source = b'''"""Module doc."""
import os
from pathlib import Path

class Greeter:
    """Says hello."""

    def greet(self, name):
        if name:
            helper(name)
        return name

def helper(value):
    return value
'''
print("Internal parse:", p_internal.parse(source))
