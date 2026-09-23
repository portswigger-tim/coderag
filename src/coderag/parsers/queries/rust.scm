; Definitions -------------------------------------------------------------
(function_item
  name: (identifier) @def.name
  body: (block) @def.body) @def.function

(struct_item
  name: (type_identifier) @def.name
  body: (field_declaration_list) @def.body) @def.struct

(enum_item
  name: (type_identifier) @def.name
  body: (enum_variant_list) @def.body) @def.enum

(trait_item
  name: (type_identifier) @def.name
  body: (declaration_list) @def.body) @def.interface

(const_item
  name: (identifier) @def.name
  value: (_) @def.body) @def.const

; Calls -------------------------------------------------------------------
(call_expression function: (identifier) @ref.call)
(call_expression function: (field_expression field: (field_identifier) @ref.call))
(call_expression function: (scoped_identifier name: (identifier) @ref.call))

; Types -------------------------------------------------------------------
(parameter type: (type_identifier) @ref.param)
(parameter type: (reference_type type: (type_identifier) @ref.param))
(function_item return_type: (type_identifier) @ref.return)
(struct_expression name: (type_identifier) @ref.instantiates)

; Imports -----------------------------------------------------------------
(use_declaration argument: (scoped_identifier) @import.module)
(use_declaration argument: (use_wildcard (scoped_identifier) @import.module))
