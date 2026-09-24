# Infraestructura (Terraform)

Un servidor EC2 en `us-east-1` donde viven la API y MySQL con `docker compose`.
Costo aproximado con el horario de las tiendas: **~$7 USD/mes** (t4g.micro, L-V 8:30 a 17:30).

## Estructura

```
infra/
├── bootstrap/        Bucket S3 donde Terraform guarda su estado. Se aplica una sola vez.
├── modules/          Piezas reutilizables; cada una hace una sola cosa:
│   ├── servidor/       EC2 t4g.micro + disco de datos + IP fija + firewall + rol de la máquina
│   ├── horario/        Enciende y apaga el servidor (EventBridge Scheduler)
│   ├── respaldos/      Bucket S3 para mysqldump + snapshots diarios del disco
│   ├── github-oidc/    Acceso de GitHub Actions a AWS sin llaves guardadas
│   └── presupuesto/    Correo si el gasto se acerca al límite
└── produccion/       El ambiente real: aquí se corre terraform. main.tf lista todo lo que existe.
```

Cada módulo tiene `main.tf` (los recursos), `variables.tf` (lo que recibe) y `outputs.tf` (lo que entrega).

| Archivo de `produccion/` | Qué es |
|---|---|
| `main.tf` | Llama a los módulos: el índice de lo que existe en AWS |
| `variables.tf` | Lo que se puede ajustar (tipo de máquina, horarios, correo…) con sus defaults |
| `outputs.tf` | Lo que Terraform muestra al terminar (IP, id de la instancia…) |
| `versions.tf` | Versión de Terraform/AWS y dónde se guarda el estado |
| `backend.hcl` | Nombre del bucket del estado (lleva el id de la cuenta). No se sube a git |
| `terraform.tfvars` | Tus valores (copia de `.example`). No se sube a git |
| `.terraform.lock.hcl` | Lo genera Terraform: fija la versión del proveedor. Sí se sube a git |

## Primera vez

Requisitos: Terraform >= 1.10 y AWS CLI con credenciales de la cuenta.

```bash
# 1. Bucket del estado (una sola vez)
cd infra/bootstrap
terraform init
terraform apply

# 2. Producción
cd ../produccion
cp terraform.tfvars.example terraform.tfvars      # pon tu correo
terraform init -backend-config=backend.hcl       # en PowerShell: terraform init "-backend-config=backend.hcl"
terraform plan
terraform apply
```

Los outputs `instancia_id` y `rol_github_arn` van como **variables** del repositorio en GitHub
(`SERVIDOR_INSTANCE_ID` y `AWS_ROLE_ARN`) para el workflow **Servidor** (encender/apagar a mano).

## Uso diario

- **Encender fuera de horario:** GitHub → Actions → Servidor → Run workflow → `encender`.
  El horario lo apaga a las 17:30.
- **Terminal en el servidor:** `terraform output conectarse` (requiere el Session Manager plugin).
- **Cambios:** edita los `.tf`, `terraform plan`, revisa, `terraform apply`.

> El disco de datos tiene `prevent_destroy`: `terraform destroy` falla a propósito para no borrar la base.
