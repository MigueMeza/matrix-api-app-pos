output "ip_publica" {
  description = "IP fija del servidor: a donde apunta la app de escritorio (y el dominio, cuando exista)"
  value       = module.servidor.ip_publica
}

output "instancia_id" {
  description = "Variable SERVIDOR_INSTANCE_ID en GitHub"
  value       = module.servidor.instancia_id
}

output "rol_github_arn" {
  description = "Variable AWS_ROLE_ARN en GitHub"
  value       = module.github_oidc.rol_arn
}

output "bucket_respaldos" {
  description = "Variable BUCKET_RESPALDOS en GitHub: respaldos de MySQL y paquete temporal del deploy"
  value       = module.respaldos.bucket
}

output "conectarse" {
  description = "Terminal en el servidor sin SSH (requiere el Session Manager plugin de AWS CLI)"
  value       = "aws ssm start-session --target ${module.servidor.instancia_id} --region us-east-1"
}
