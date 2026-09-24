variable "nombre" {
  description = "Prefijo de los nombres de los recursos"
  type        = string
}

variable "repositorio" {
  description = "Repositorio que puede usar el rol (dueño/repo)"
  type        = string
}

variable "instancia_arn" {
  description = "Servidor que el rol puede encender, apagar y administrar por SSM"
  type        = string
}

variable "crear_proveedor" {
  description = "false si la cuenta ya tiene el proveedor OIDC de token.actions.githubusercontent.com"
  type        = bool
  default     = true
}
