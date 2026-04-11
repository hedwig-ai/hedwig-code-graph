; Kotlin tags.scm — based on community patterns, adapted for tree_sitter_kotlin AST

(class_declaration
  name: (identifier) @name) @definition.class

(object_declaration
  name: (identifier) @name) @definition.class

(function_declaration
  name: (identifier) @name) @definition.function

(call_expression
  (identifier) @name) @reference.call

(call_expression
  (navigation_expression
    (identifier) @name)) @reference.call
