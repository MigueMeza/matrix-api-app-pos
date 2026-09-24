# Descargas de la app de escritorio (Velopack): instalador y actualizaciones automáticas.
#
# - Bucket con lectura PÚBLICA solo en la carpeta app/: la app instalada en cada tienda revisa ahí si hay
#   versión nueva, sin credenciales. El ejecutable no trae secretos: sin usuario y NIP no hace nada.
# - Nadie puede listar el bucket ni escribir en él, salvo el rol de GitHub Actions del repo de la app,
#   y solo al crear un tag de versión (v*).
# - vpk borra solo las versiones viejas (--keepMaxReleases en el workflow).

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

data "aws_caller_identity" "actual" {}

locals {
  carpeta = "app"

  # Formato del claim "sub" de GitHub con ids: repo:<dueño>@<id>/<repo>@<id>:ref:refs/tags/v1.2.3
  # El id del dueño va fijo (garantiza que es tu cuenta); el del repo con comodín porque el repo es privado
  # y su id no se puede consultar sin autenticación. También se acepta el formato anterior, sin ids.
  dueno = split("/", var.repositorio)[0]
  repo  = split("/", var.repositorio)[1]
  sujetos_permitidos = [
    "repo:${local.dueno}@${var.dueno_id}/${local.repo}@*:ref:refs/tags/v*",
    "repo:${var.repositorio}:ref:refs/tags/v*",
  ]
}

# ---------------------------------------------------------------- bucket

resource "aws_s3_bucket" "descargas" {
  bucket = "${var.nombre}-descargas-${data.aws_caller_identity.actual.account_id}"
}

# Se permite la política pública del bucket (lectura de app/); las ACL públicas siguen bloqueadas
resource "aws_s3_bucket_public_access_block" "descargas" {
  bucket = aws_s3_bucket.descargas.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

data "aws_iam_policy_document" "lectura_publica" {
  statement {
    sid       = "LecturaPublicaDeLaApp"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.descargas.arn}/${local.carpeta}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_s3_bucket_policy" "descargas" {
  bucket = aws_s3_bucket.descargas.id
  policy = data.aws_iam_policy_document.lectura_publica.json

  # Con el bloqueo de políticas públicas activo, AWS rechazaría esta política
  depends_on = [aws_s3_bucket_public_access_block.descargas]
}

# ---------------------------------------------------------------- publicación desde GitHub Actions

data "aws_iam_policy_document" "asumir_github" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.proveedor_oidc_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.sujetos_permitidos
    }
  }
}

resource "aws_iam_role" "publicar" {
  name               = "${var.nombre}-github-app-escritorio"
  assume_role_policy = data.aws_iam_policy_document.asumir_github.json
}

data "aws_iam_policy_document" "publicar" {
  statement {
    sid       = "ListarVersiones"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.descargas.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.carpeta}/*"]
    }
  }

  statement {
    sid       = "SubirYBorrarVersiones"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.descargas.arn}/${local.carpeta}/*"]
  }
}

resource "aws_iam_role_policy" "publicar" {
  name   = "descargas"
  role   = aws_iam_role.publicar.id
  policy = data.aws_iam_policy_document.publicar.json
}
