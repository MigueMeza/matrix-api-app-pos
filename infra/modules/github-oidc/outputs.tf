output "proveedor_arn" {
  description = "Proveedor OIDC de GitHub, para otros roles (ej. publicar la app de escritorio)"
  value       = local.proveedor_arn
}

output "rol_arn" {
  description = "Rol que asumen los workflows (variable AWS_ROLE_ARN en GitHub)"
  value       = aws_iam_role.github.arn
}
