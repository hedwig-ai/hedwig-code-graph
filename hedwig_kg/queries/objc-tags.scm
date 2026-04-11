; Objective-C tags.scm — custom for hedwig-kg

(class_interface
  (identifier) @name) @definition.class

(class_implementation
  (identifier) @name) @definition.class

(protocol_declaration
  (identifier) @name) @definition.interface

(method_declaration
  (identifier) @name) @definition.method

(method_definition
  (identifier) @name) @definition.method

(function_definition
  declarator: (function_declarator
    declarator: (identifier) @name)) @definition.function

(preproc_function_def
  name: (identifier) @name) @definition.function
