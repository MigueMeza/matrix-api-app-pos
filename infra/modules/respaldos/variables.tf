variable "nombre" {
  description = "Prefijo de los nombres de los recursos"
  type        = string
}

variable "rol_servidor" {
  description = "Nombre del rol del servidor, que recibe permiso para subir respaldos"
  type        = string
}

variable "dias_respaldo" {
  description = "Días que se conservan los mysqldump en S3"
  type        = number
  default     = 30
}

variable "snapshots_conservados" {
  description = "Snapshots diarios que se conservan de cada disco"
  type        = number
  default     = 7
}

variable "hora_snapshot_utc" {
  description = "Hora del snapshot diario en UTC (HH:MM). Conviene con el servidor apagado: el snapshot queda consistente."
  type        = string
  default     = "01:30"
}
