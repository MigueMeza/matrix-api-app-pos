# Lo que se puede ajustar de producción. Los valores propios van en terraform.tfvars.

# ---------------------------------------------------------------- servidor

variable "tipo_instancia" {
  description = "t4g = ARM (más barato). 1 tienda / ~8 ventas al día: micro (1 GB) alcanza. Si crece: t4g.small (2 GB)."
  type        = string
  default     = "t4g.micro"
}

variable "arquitectura" {
  description = "arm64 para t4g, x86_64 para t3"
  type        = string
  default     = "arm64"
}

variable "disco_datos_gb" {
  description = "Tamaño del disco donde vive la base de MySQL. Se puede agrandar después sin apagar, pero no achicar."
  type        = number
  default     = 10
}

variable "puertos_publicos" {
  description = "Puertos abiertos a internet"
  type        = list(number)
  default     = [80, 443]
}

variable "ssh_permitido_desde" {
  description = "IPs que pueden entrar por SSH (ej. [\"201.141.31.69/32\"]). Va en terraform.tfvars, no en git. Vacío = cerrado."
  type        = list(string)
  default     = []
}

variable "llave_ssh_archivo" {
  description = "Ruta de la llave PÚBLICA para SSH (ej. ~/.ssh/matrix-pos.pub). Vacío = sin llave. Cambiarla recrea el servidor."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------- horario (hora de CDMX)

variable "horario_encender" {
  description = "9:00, de lunes a viernes (la API tarda 1-2 minutos en responder después de encender)"
  type        = string
  default     = "cron(0 9 ? * MON-FRI *)"
}

variable "horario_apagar" {
  description = "17:00. Todos los días: también apaga lo que se haya encendido a mano en fin de semana."
  type        = string
  default     = "cron(0 17 ? * * *)"
}

variable "horario_activo" {
  description = "false = el servidor queda encendido siempre"
  type        = bool
  default     = true
}

# ---------------------------------------------------------------- GitHub Actions

variable "crear_proveedor_oidc_github" {
  description = "false si la cuenta ya tiene el proveedor OIDC de GitHub (de otro proyecto)"
  type        = bool
  default     = true
}

# ---------------------------------------------------------------- costos

variable "presupuesto_mensual_usd" {
  description = "Alerta cuando el gasto de la cuenta se acerque a este monto"
  type        = number
  default     = 20
}

variable "correo_alertas" {
  description = "Correo para las alertas de presupuesto. Vacío = sin alertas."
  type        = string
  default     = ""
}
