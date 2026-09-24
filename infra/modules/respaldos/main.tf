# Dos tipos de respaldo:
# - Bucket S3 para los mysqldump que hace el deploy antes de cada migración (se borran solos a los N días).
#   Le da permiso de escritura al rol del servidor.
# - Snapshots diarios de los discos con la etiqueta Respaldo=diario (DLM), por si se pierde el disco completo.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

data "aws_caller_identity" "actual" {}

# ---------------------------------------------------------------- bucket de mysqldump

resource "aws_s3_bucket" "respaldos" {
  bucket = "${var.nombre}-respaldos-${data.aws_caller_identity.actual.account_id}"
}

resource "aws_s3_bucket_public_access_block" "respaldos" {
  bucket = aws_s3_bucket.respaldos.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "respaldos" {
  bucket = aws_s3_bucket.respaldos.id

  rule {
    id     = "borrar-respaldos-viejos"
    status = "Enabled"

    filter {}

    expiration {
      days = var.dias_respaldo
    }
  }
}

# El servidor sube y descarga respaldos del bucket
data "aws_iam_policy_document" "servidor" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.respaldos.arn}/*"]
  }

  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.respaldos.arn]
  }
}

resource "aws_iam_role_policy" "servidor" {
  name   = "respaldos"
  role   = var.rol_servidor
  policy = data.aws_iam_policy_document.servidor.json
}

# ---------------------------------------------------------------- snapshots de los discos

data "aws_iam_policy_document" "asumir_dlm" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["dlm.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "snapshots" {
  name               = "${var.nombre}-snapshots"
  assume_role_policy = data.aws_iam_policy_document.asumir_dlm.json
}

resource "aws_iam_role_policy_attachment" "snapshots" {
  role       = aws_iam_role.snapshots.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "discos" {
  description        = "Snapshot diario de los discos de ${var.nombre}"
  execution_role_arn = aws_iam_role.snapshots.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]
    target_tags    = local.etiqueta_snapshot

    schedule {
      name      = "diario"
      copy_tags = true

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = [var.hora_snapshot_utc]
      }

      retain_rule {
        count = var.snapshots_conservados
      }
    }
  }
}

locals {
  etiqueta_snapshot = {
    Respaldo = "diario"
  }
}
