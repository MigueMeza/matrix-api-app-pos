output "instancia_id" {
  value = aws_instance.servidor.id
}

output "instancia_arn" {
  value = aws_instance.servidor.arn
}

output "ip_publica" {
  description = "IP fija del servidor"
  value       = aws_eip.servidor.public_ip
}

output "rol_nombre" {
  description = "Rol de la máquina, para que otros módulos le agreguen permisos (ej. respaldos)"
  value       = aws_iam_role.servidor.name
}
