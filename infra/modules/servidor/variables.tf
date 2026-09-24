variable "nombre" {
  description = "Prefijo de los nombres de los recursos"
  type        = string
}

variable "tipo_instancia" {
  description = "Tipo de EC2. t4g = ARM (más barato); si usas x86 (ej. t3.small), cambia también arquitectura."
  type        = string
}

variable "arquitectura" {
  description = "Debe coincidir con tipo_instancia: arm64 para t4g, x86_64 para t3"
  type        = string

  validation {
    condition     = contains(["arm64", "x86_64"], var.arquitectura)
    error_message = "arquitectura debe ser arm64 o x86_64."
  }
}

variable "disco_sistema_gb" {
  description = "Disco del sistema operativo (se puede recrear sin perder datos). 8 GB es el mínimo de Amazon Linux 2023."
  type        = number
  default     = 8
}

variable "disco_datos_gb" {
  description = "Disco de datos: /var/lib/docker (contenedores y la base de MySQL)"
  type        = number
  default     = 20
}

variable "etiquetas_disco_datos" {
  description = "Etiquetas extra del disco de datos (ej. la que usa el módulo de respaldos para los snapshots)"
  type        = map(string)
  default     = {}
}

variable "puertos_publicos" {
  description = "Puertos abiertos a internet. Sin 22: el acceso es por SSM."
  type        = list(number)
  default     = [80, 443]
}

variable "version_docker_compose" {
  description = "Versión del plugin de Docker Compose que se instala al crear el servidor"
  type        = string
  default     = "v2.29.7"
}

variable "cidr_subred" {
  description = "Rango de IPs de la subred del servidor, dentro de la VPC por defecto (172.31.0.0/16)"
  type        = string
  default     = "172.31.0.0/20"
}
