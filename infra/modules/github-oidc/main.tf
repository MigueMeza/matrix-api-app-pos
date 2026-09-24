# Acceso de GitHub Actions a AWS sin llaves guardadas: GitHub presenta un token OIDC y AWS le
# entrega credenciales temporales de este rol. Solo desde la rama main o el environment
# "production" del repositorio.
#
# Permisos: encender/apagar el servidor y ejecutar comandos o abrir túneles por SSM (deploy).

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

data "aws_region" "actual" {}

locals {
  url_oidc      = "https://token.actions.githubusercontent.com"
  proveedor_arn = var.crear_proveedor ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
  region        = data.aws_region.actual.region
}

# Solo puede existir un proveedor de GitHub por cuenta: se crea o se reutiliza el existente
resource "aws_iam_openid_connect_provider" "github" {
  count = var.crear_proveedor ? 1 : 0

  url            = local.url_oidc
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.crear_proveedor ? 0 : 1

  url = local.url_oidc
}

data "aws_iam_policy_document" "asumir_github" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.proveedor_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.repositorio}:ref:refs/heads/main",
        "repo:${var.repositorio}:environment:production",
      ]
    }
  }
}

resource "aws_iam_role" "github" {
  name               = "${var.nombre}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.asumir_github.json
}

data "aws_iam_policy_document" "servidor" {
  statement {
    sid       = "EncenderApagar"
    actions   = ["ec2:StartInstances", "ec2:StopInstances"]
    resources = [var.instancia_arn]
  }

  statement {
    sid       = "ConsultarServidor"
    actions   = ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus", "ssm:DescribeInstanceInformation"]
    resources = ["*"]
  }

  statement {
    sid     = "ComandosYTuneles"
    actions = ["ssm:SendCommand", "ssm:StartSession"]
    resources = [
      var.instancia_arn,
      "arn:aws:ssm:${local.region}::document/AWS-RunShellScript",
      "arn:aws:ssm:${local.region}::document/AWS-StartPortForwardingSession",
      "arn:aws:ssm:${local.region}::document/AWS-StartPortForwardingSessionToRemoteHost",
    ]
  }

  statement {
    sid       = "ResultadoDeComandos"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"]
  }

  # Paquete temporal del deploy (compose, migraciones, .env.prod): se sube, el servidor lo descarga y se borra
  statement {
    sid       = "PaqueteDeploy"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.bucket_deploy_arn}/deploy/*"]
  }

  statement {
    sid       = "CerrarSusSesiones"
    actions   = ["ssm:TerminateSession", "ssm:ResumeSession"]
    resources = ["arn:aws:ssm:*:*:session/$${aws:userid}-*"]
  }
}

resource "aws_iam_role_policy" "servidor" {
  name   = "servidor"
  role   = aws_iam_role.github.id
  policy = data.aws_iam_policy_document.servidor.json
}
