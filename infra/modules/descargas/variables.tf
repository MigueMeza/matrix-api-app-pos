variable "nombre" {
  description = "Prefijo de los nombres de los recursos"
  type        = string
}

variable "repositorio" {
  description = "Repositorio de la app de escritorio que publica las versiones (dueño/repo)"
  type        = string
}

variable "dueno_id" {
  description = "Id numérico de la cuenta dueña del repositorio en GitHub"
  type        = string
}

variable "proveedor_oidc_arn" {
  description = "Proveedor OIDC de GitHub de la cuenta (lo crea el módulo github-oidc)"
  type        = string
}
