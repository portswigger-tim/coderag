; Definitions -------------------------------------------------------------
(function_declaration
  name: (identifier) @def.name
  body: (statement_block) @def.body) @def.function

(method_definition
  name: (property_identifier) @def.name
  body: (statement_block) @def.body) @def.function

; const foo = (...) => {...}  and  const foo = function (...) {...}
(lexical_declaration
  (variable_declarator
    name: (identifier) @def.name
    value: [(arrow_function) (function_expression)] @def.body)) @def.function

; Exported constant tables, as distinct from arrow functions above.
(lexical_declaration
  (variable_declarator
    name: (identifier) @def.name
    value: [(array) (object) (number) (string)] @def.body)) @def.const

(class_declaration
  name: (type_identifier) @def.name
  body: (class_body) @def.body) @def.class

(interface_declaration
  name: (type_identifier) @def.name
  body: (interface_body) @def.body) @def.interface

(enum_declaration
  name: (identifier) @def.name
  body: (enum_body) @def.body) @def.enum

; Inheritance -------------------------------------------------------------
(class_heritage (extends_clause value: (identifier) @ref.base))
(interface_declaration (extends_type_clause type: (type_identifier) @ref.base))

; Test cases: test("name", () => {...}), it(...), describe(...).
; These bodies are anonymous callbacks, so without this pattern every call
; inside a Jest/Mocha/Vitest suite has no enclosing definition and is
; discarded -- which silently costs TESTED_BY edges across most of the
; JS/TS ecosystem. The string argument becomes the symbol name.
(call_expression
  function: (identifier) @ref.call
  arguments: (arguments
    .
    (string (string_fragment) @def.name)
    [(arrow_function) (function_expression)] @def.body)) @def.function

; Calls -------------------------------------------------------------------
(call_expression function: (identifier) @ref.call)
(call_expression function: (member_expression property: (property_identifier) @ref.call))
(new_expression constructor: (identifier) @ref.instantiates)

; Types -------------------------------------------------------------------
(required_parameter type: (type_annotation (type_identifier) @ref.param))
(optional_parameter type: (type_annotation (type_identifier) @ref.param))
(required_parameter
  type: (type_annotation (generic_type name: (type_identifier) @ref.param)))
(required_parameter
  type: (type_annotation (array_type (type_identifier) @ref.param)))
(function_declaration
  return_type: (type_annotation (type_identifier) @ref.return))
(function_declaration
  return_type: (type_annotation (generic_type name: (type_identifier) @ref.return)))
(method_definition
  return_type: (type_annotation (type_identifier) @ref.return))

; Imports -----------------------------------------------------------------
(import_statement
  (import_clause (named_imports (import_specifier name: (identifier) @import.name)))
  source: (string (string_fragment) @import.module))
(import_statement
  (import_clause (identifier) @import.name)
  source: (string (string_fragment) @import.module))
