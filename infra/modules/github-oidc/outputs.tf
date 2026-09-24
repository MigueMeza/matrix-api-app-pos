output "rol_arn" {
  description = "Rol que asumen los workflows (variable AWS_ROLE_ARN en GitHub)"
  value       = aws_iam_role.github.arn
}
