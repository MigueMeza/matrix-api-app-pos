output "bucket" {
  description = "Bucket donde el deploy guarda los mysqldump"
  value       = aws_s3_bucket.respaldos.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.respaldos.arn
}

output "etiqueta_snapshot" {
  description = "Etiqueta que debe tener un disco para recibir el snapshot diario"
  value       = local.etiqueta_snapshot
}
