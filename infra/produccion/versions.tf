terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # El bucket se indica al hacer init: terraform init -backend-config=backend.hcl
  # use_lockfile: S3 bloquea el estado mientras alguien hace apply (sin DynamoDB)
  backend "s3" {
    key          = "matrix-pos/produccion.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      Proyecto        = "matrix-pos"
      Ambiente        = "produccion"
      AdministradoPor = "terraform"
    }
  }
}
