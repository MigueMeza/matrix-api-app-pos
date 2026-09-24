# Bucket S3 donde Terraform guarda el estado de infra/.
#
# Se aplica UNA sola vez, antes que todo lo demás, y su propio estado queda local
# (terraform.tfstate en esta carpeta, ignorado por git): el bucket no puede guardar
# el estado de quien lo crea.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      Proyecto        = "matrix-pos"
      AdministradoPor = "terraform"
    }
  }
}

data "aws_caller_identity" "actual" {}

resource "aws_s3_bucket" "estado" {
  # El id de la cuenta hace el nombre único en todo S3
  bucket = "matrix-pos-tfstate-${data.aws_caller_identity.actual.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

# Versiones anteriores del estado, por si un apply lo deja mal
resource "aws_s3_bucket_versioning" "estado" {
  bucket = aws_s3_bucket.estado.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "estado" {
  bucket = aws_s3_bucket.estado.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "bucket_estado" {
  description = "Va en infra/backend.hcl"
  value       = aws_s3_bucket.estado.bucket
}
