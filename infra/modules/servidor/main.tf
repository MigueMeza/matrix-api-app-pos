# Una máquina EC2 donde viven los contenedores (API + MySQL) con docker compose.
#
# - La base de MySQL vive en un disco de datos aparte, montado en /var/lib/docker: si la instancia
#   se reemplaza (cambio de tipo, AMI...), el disco se vuelve a conectar y los datos siguen ahí.
# - IP fija, para que la app de escritorio siempre encuentre la API aunque el servidor se apague.
# - Sin SSH: el acceso es por SSM (Session Manager).

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

# ---------------------------------------------------------------- red

# VPC por defecto de la cuenta (ya trae internet gateway y ruta a internet). Sin NAT Gateway: ~$32/mes que aquí no hacen falta.
data "aws_vpc" "default" {
  default = true
}

# No todas las zonas tienen todos los tipos de instancia (ej. t4g): se usa una que sí
data "aws_ec2_instance_type_offerings" "disponible" {
  location_type = "availability-zone"

  filter {
    name   = "instance-type"
    values = [var.tipo_instancia]
  }
}

# Subred propia (la cuenta no tiene las subredes por defecto). Queda asociada a la tabla de rutas
# principal de la VPC, que ya sale a internet por el internet gateway: es una subred pública.
resource "aws_subnet" "servidor" {
  vpc_id            = data.aws_vpc.default.id
  cidr_block        = var.cidr_subred
  availability_zone = sort(data.aws_ec2_instance_type_offerings.disponible.locations)[0]

  # IP pública automática al arrancar: el user_data descarga Docker en los primeros segundos,
  # antes de que se conecte la IP fija (que después la reemplaza, sin cobro doble)
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.nombre}-publica"
  }
}

resource "aws_security_group" "servidor" {
  name        = "${var.nombre}-servidor"
  description = "Trafico web hacia la API. Sin SSH: el acceso es por SSM."
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name = "${var.nombre}-servidor"
  }
}

resource "aws_vpc_security_group_ingress_rule" "web" {
  for_each = toset([for puerto in var.puertos_publicos : tostring(puerto)])

  security_group_id = aws_security_group.servidor.id
  description       = "Puerto ${each.value}"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
}

# Salida libre: descargar imágenes de GHCR, paquetes del sistema, hablar con SSM y S3
resource "aws_vpc_security_group_egress_rule" "todo" {
  security_group_id = aws_security_group.servidor.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# ---------------------------------------------------------------- permisos de la máquina

data "aws_iam_policy_document" "asumir_ec2" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "servidor" {
  name               = "${var.nombre}-servidor"
  assume_role_policy = data.aws_iam_policy_document.asumir_ec2.json
}

# Acceso por Session Manager (terminal y túneles) sin abrir el puerto 22
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.servidor.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "servidor" {
  name = "${var.nombre}-servidor"
  role = aws_iam_role.servidor.name
}

# ---------------------------------------------------------------- máquina y discos

# Última Amazon Linux 2023 para la arquitectura elegida (la publica AWS en SSM)
data "aws_ssm_parameter" "ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-${var.arquitectura}"
}

resource "aws_ebs_volume" "datos" {
  availability_zone = aws_subnet.servidor.availability_zone
  size              = var.disco_datos_gb
  type              = "gp3"
  encrypted         = true

  tags = merge(var.etiquetas_disco_datos, {
    Name = "${var.nombre}-datos"
  })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_instance" "servidor" {
  ami                    = data.aws_ssm_parameter.ami.insecure_value
  instance_type          = var.tipo_instancia
  subnet_id              = aws_subnet.servidor.id
  vpc_security_group_ids = [aws_security_group.servidor.id]
  iam_instance_profile   = aws_iam_instance_profile.servidor.name

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    volumen_datos        = replace(aws_ebs_volume.datos.id, "-", "")
    version_compose      = var.version_docker_compose
    arquitectura_compose = var.arquitectura == "arm64" ? "aarch64" : "x86_64"
  })

  # Solo IMDSv2
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_size = var.disco_sistema_gb
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name = var.nombre
  }

  lifecycle {
    # Una AMI nueva o un cambio en user_data no deben recrear el servidor por sí solos.
    # Para actualizarlo a propósito: terraform apply -replace=module.servidor.aws_instance.servidor
    ignore_changes = [ami, user_data]
  }
}

resource "aws_volume_attachment" "datos" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.datos.id
  instance_id = aws_instance.servidor.id
}

resource "aws_eip" "servidor" {
  domain   = "vpc"
  instance = aws_instance.servidor.id

  tags = {
    Name = var.nombre
  }
}
