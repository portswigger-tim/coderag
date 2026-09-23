; Definitions -------------------------------------------------------------
(method_declaration
  name: (identifier) @def.name
  body: (block) @def.body) @def.function

(constructor_declaration
  name: (identifier) @def.name
  body: (constructor_body) @def.body) @def.function

(class_declaration
  name: (identifier) @def.name
  body: (class_body) @def.body) @def.class

(interface_declaration
  name: (identifier) @def.name
  body: (interface_body) @def.body) @def.interface

(enum_declaration
  name: (identifier) @def.name
  body: (enum_body) @def.body) @def.enum

; Inheritance -------------------------------------------------------------
(superclass (type_identifier) @ref.base)
(super_interfaces (type_list (type_identifier) @ref.base))

; Calls -------------------------------------------------------------------
(method_invocation name: (identifier) @ref.call)
(object_creation_expression type: (type_identifier) @ref.instantiates)

; Types -------------------------------------------------------------------
(formal_parameter type: (type_identifier) @ref.param)
(formal_parameter type: (generic_type (type_identifier) @ref.param))
(method_declaration type: (type_identifier) @ref.return)

; Imports -----------------------------------------------------------------
(import_declaration (scoped_identifier) @import.module)
