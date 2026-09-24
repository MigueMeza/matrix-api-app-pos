# Enciende y apaga una instancia EC2 en horarios fijos (EventBridge Scheduler, sin Lambda).
# Apagada, solo se paga el disco y la IP fija.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

data "aws_caller_identity" "actual" {}

# Rol que usa el Scheduler para encender y apagar solo esta instancia
data "aws_iam_policy_document" "asumir_scheduler" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.actual.account_id]
    }
  }
}

resource "aws_iam_role" "horario" {
  name               = "${var.nombre}-horario"
  assume_role_policy = data.aws_iam_policy_document.asumir_scheduler.json
}

data "aws_iam_policy_document" "encender_apagar" {
  statement {
    actions   = ["ec2:StartInstances", "ec2:StopInstances"]
    resources = [var.instancia_arn]
  }
}

resource "aws_iam_role_policy" "encender_apagar" {
  name   = "encender-apagar"
  role   = aws_iam_role.horario.id
  policy = data.aws_iam_policy_document.encender_apagar.json
}

resource "aws_scheduler_schedule" "encender" {
  name        = "${var.nombre}-encender"
  description = "Enciende el servidor antes de abrir las tiendas"
  state       = var.activo ? "ENABLED" : "DISABLED"

  schedule_expression          = var.encender
  schedule_expression_timezone = var.zona_horaria

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
    role_arn = aws_iam_role.horario.arn
    input    = jsonencode({ InstanceIds = [var.instancia_id] })
  }
}

resource "aws_scheduler_schedule" "apagar" {
  name        = "${var.nombre}-apagar"
  description = "Apaga el servidor despues del cierre"
  state       = var.activo ? "ENABLED" : "DISABLED"

  schedule_expression          = var.apagar
  schedule_expression_timezone = var.zona_horaria

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
    role_arn = aws_iam_role.horario.arn
    input    = jsonencode({ InstanceIds = [var.instancia_id] })
  }
}
