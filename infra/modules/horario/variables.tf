variable "nombre" {
  description = "Prefijo de los nombres de los recursos"
  type        = string
}

variable "instancia_id" {
  description = "Instancia que se enciende y apaga"
  type        = string
}

variable "instancia_arn" {
  description = "ARN de la instancia (para limitar el permiso a solo ella)"
  type        = string
}

variable "encender" {
  description = "Expresión cron de encendido, ej. cron(30 7 ? * MON-FRI *)"
  type        = string
}

variable "apagar" {
  description = "Expresión cron de apagado, ej. cron(0 19 ? * * *)"
  type        = string
}

variable "zona_horaria" {
  description = "Zona horaria de las expresiones cron"
  type        = string
  default     = "America/Mexico_City"
}

variable "activo" {
  description = "false = los horarios quedan pausados y el servidor no se enciende ni se apaga solo"
  type        = bool
  default     = true
}
