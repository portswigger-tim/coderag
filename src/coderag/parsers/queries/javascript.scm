; JavaScript: same shapes as TypeScript minus the type system, so USES lists
; here carry calls and instantiations only (types_unavailable is set).
(function_declaration
  name: (identifier) @def.name
  body: (statement_block) @def.body) @def.function

(method_definition
  name: (property_identifier) @def.name
  body: (statement_block) @def.body) @def.function

(lexical_declaration
  (variable_declarator
    name: (identifier) @def.name
    value: [(arrow_function) (function_expression)] @def.body)) @def.function

(class_declaration
  name: (identifier) @def.name
  body: (class_body) @def.body) @def.class

(class_heritage (identifier) @ref.base)

; Test cases: test("name", () => {...}), it(...), describe(...).
; Without this, every call inside a Jest/Mocha/Vitest suite has no enclosing
; definition and is discarded, silently costing TESTED_BY edges.
(call_expression
  function: (identifier) @ref.call
  arguments: (arguments
    .
    (string (string_fragment) @def.name)
    [(arrow_function) (function_expression)] @def.body)) @def.function

(call_expression function: (identifier) @ref.call)
(call_expression function: (member_expression property: (property_identifier) @ref.call))
(new_expression constructor: (identifier) @ref.instantiates)

(import_statement
  (import_clause (named_imports (import_specifier name: (identifier) @import.name)))
  source: (string (string_fragment) @import.module))
