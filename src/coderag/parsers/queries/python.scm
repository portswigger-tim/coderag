; Definitions -------------------------------------------------------------
(function_definition
  name: (identifier) @def.name
  body: (block) @def.body) @def.function

(class_definition
  name: (identifier) @def.name
  body: (block) @def.body) @def.class

; Module-level constants: NAME = ... at top level, screaming snake case is
; filtered in Python since tree-sitter cannot express the casing rule.
(module
  (expression_statement
    (assignment
      left: (identifier) @def.name) @def.body) @def.const)

; Inheritance -------------------------------------------------------------
(class_definition
  superclasses: (argument_list (identifier) @ref.base))

; Calls -------------------------------------------------------------------
(call function: (identifier) @ref.call)
(call function: (attribute attribute: (identifier) @ref.call))

; Type annotations --------------------------------------------------------
(typed_parameter type: (type (identifier) @ref.param))
(typed_parameter type: (type (string) @ref.param.str))
(typed_parameter type: (type (subscript value: (identifier) @ref.param)))
(function_definition
  return_type: (type (identifier) @ref.return))
(function_definition
  return_type: (type (subscript value: (identifier) @ref.return)))

; Imports -----------------------------------------------------------------
(import_statement
  name: (dotted_name) @import.module)
(import_statement
  name: (aliased_import
          name: (dotted_name) @import.module
          alias: (identifier) @import.alias))
(import_from_statement
  module_name: (dotted_name) @import.module
  name: (dotted_name) @import.name)
(import_from_statement
  module_name: (relative_import) @import.module
  name: (dotted_name) @import.name)
