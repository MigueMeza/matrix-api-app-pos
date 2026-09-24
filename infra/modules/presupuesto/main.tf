# Correo de alerta si el gasto de la cuenta se acerca al presupuesto mensual
# (los 2 primeros presupuestos de una cuenta son gratis). Vigila toda la cuenta, no solo este proyecto.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

resource "aws_budgets_budget" "mensual" {
  name         = "${var.nombre}-mensual"
  budget_type  = "COST"
  limit_amount = tostring(var.limite_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Aviso anticipado: al ritmo actual, el mes va a pasar del 80%
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.correo]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.correo]
  }
}
