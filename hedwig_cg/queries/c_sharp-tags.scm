; C# tags.scm — from tree-sitter/tree-sitter-c-sharp official repo

(class_declaration name: (identifier) @name) @definition.class

(class_declaration (base_list (_) @name)) @reference.class

(interface_declaration name: (identifier) @name) @definition.interface

(interface_declaration (base_list (_) @name)) @reference.interface

(method_declaration name: (identifier) @name) @definition.method

(object_creation_expression type: (identifier) @name) @reference.class

(invocation_expression function: (member_access_expression name: (identifier) @name)) @reference.call

(namespace_declaration name: (identifier) @name) @definition.module
