variable "nombre" {
  description = "Prefijo del nombre del presupuesto"
  type        = string
}

variable "limite_usd" {
  description = "Presupuesto mensual en dólares"
  type        = number
}

variable "correo" {
  description = "Correo que recibe las alertas"
  type        = string
}
