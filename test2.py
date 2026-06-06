import tree_sitter
import tree_sitter_python
lang = tree_sitter.Language(tree_sitter_python.language(), 'python')

try:
    p = tree_sitter.Parser()
    p.set_language(lang)
    print("set_language successful")
except AttributeError:
    print("falling back to Parser(lang)")
    p = tree_sitter.Parser(lang)

print(p.parse(b'def foo(): pass'))
