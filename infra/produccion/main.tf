# Ambiente de producción de Matrix POS: todo lo que existe en AWS, en un vistazo.
# Los detalles de cada pieza están en ../modules/<nombre>/main.tf

locals {
  nombre = "matrix-pos"
}

# Máquina EC2 con Docker donde viven la API y MySQL, con IP fija y disco de datos aparte
module "servidor" {
  source = "../modules/servidor"

  nombre                = local.nombre
  tipo_instancia        = var.tipo_instancia
  arquitectura          = var.arquitectura
  disco_datos_gb        = var.disco_datos_gb
  puertos_publicos      = var.puertos_publicos
  ssh_permitido_desde   = var.ssh_permitido_desde
  llave_ssh_publica     = var.llave_ssh_archivo == "" ? null : trimspace(file(pathexpand(var.llave_ssh_archivo)))
  etiquetas_disco_datos = module.respaldos.etiqueta_snapshot
}

# Enciende 9:00 (L-V) y apaga 17:00 (todos los días), hora de CDMX
module "horario" {
  source = "../modules/horario"

  nombre        = local.nombre
  instancia_id  = module.servidor.instancia_id
  instancia_arn = module.servidor.instancia_arn
  encender      = var.horario_encender
  apagar        = var.horario_apagar
  activo        = var.horario_activo
}

# Bucket para los mysqldump del deploy y snapshots diarios del disco de datos
module "respaldos" {
  source = "../modules/respaldos"

  nombre       = local.nombre
  rol_servidor = module.servidor.rol_nombre
}

# Acceso de GitHub Actions a AWS (deploy y botón de encender/apagar)
module "github_oidc" {
  source = "../modules/github-oidc"

  nombre            = local.nombre
  repositorio       = "MigueMeza/matrix-api-app-pos"
  dueno_id          = "37991807"   # api.github.com/users/MigueMeza → id
  repositorio_id    = "1382119970" # api.github.com/repos/MigueMeza/matrix-api-app-pos → id
  instancia_arn     = module.servidor.instancia_arn
  bucket_deploy_arn = module.respaldos.bucket_arn
  crear_proveedor   = var.crear_proveedor_oidc_github
}

# Instalador y actualizaciones automáticas de la app de escritorio (bucket público de solo lectura)
module "descargas" {
  source = "../modules/descargas"

  nombre             = local.nombre
  repositorio        = "MigueMeza/matrix-desktop-app-pos"
  dueno_id           = "37991807"
  proveedor_oidc_arn = module.github_oidc.proveedor_arn
}

# Alerta de gasto por correo (solo si se configuró un correo)
module "presupuesto" {
  source = "../modules/presupuesto"
  count  = var.correo_alertas == "" ? 0 : 1

  nombre     = local.nombre
  limite_usd = var.presupuesto_mensual_usd
  correo     = var.correo_alertas
}
