; Definitions -------------------------------------------------------------
(function_declaration
  name: (identifier) @def.name
  body: (block) @def.body) @def.function

(method_declaration
  name: (field_identifier) @def.name
  body: (block) @def.body) @def.function

(type_declaration
  (type_spec
    name: (type_identifier) @def.name
    type: (struct_type) @def.body)) @def.struct

(type_declaration
  (type_spec
    name: (type_identifier) @def.name
    type: (interface_type) @def.body)) @def.interface

(const_declaration
  (const_spec name: (identifier) @def.name) @def.body) @def.const

; Package-level var tables (lookup maps, rate tables) are answers in
; their own right, not incidental state.
(var_declaration
  (var_spec name: (identifier) @def.name value: (_) @def.body)) @def.const

; Calls -------------------------------------------------------------------
(call_expression function: (identifier) @ref.call)
(call_expression function: (selector_expression field: (field_identifier) @ref.call))

; Types -------------------------------------------------------------------
(parameter_declaration type: (type_identifier) @ref.param)
(parameter_declaration type: (pointer_type (type_identifier) @ref.param))
(parameter_declaration type: (qualified_type name: (type_identifier) @ref.param))
(method_declaration result: (type_identifier) @ref.return)
(function_declaration result: (type_identifier) @ref.return)
(composite_literal type: (type_identifier) @ref.instantiates)

; Imports -----------------------------------------------------------------
(import_spec path: (interpreted_string_literal) @import.module)
