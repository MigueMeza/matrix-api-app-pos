output "bucket" {
  description = "Variable DESCARGAS_BUCKET en el repo de la app"
  value       = aws_s3_bucket.descargas.bucket
}

output "url_actualizaciones" {
  description = "UpdatesUrl de la app (matrix-pos.csproj)"
  value       = "https://${aws_s3_bucket.descargas.bucket}.s3.amazonaws.com/${local.carpeta}/"
}

output "rol_publicar_arn" {
  description = "Variable AWS_ROLE_ARN en el repo de la app"
  value       = aws_iam_role.publicar.arn
}
