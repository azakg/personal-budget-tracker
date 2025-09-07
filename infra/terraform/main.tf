terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 5.0" }
  }
}

provider "aws" {
  region = var.region
}

data "aws_availability_zones" "available" {}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name    = "${var.project}-vpc"
  cidr    = "10.0.0.0/16"

  azs             = slice(data.aws_availability_zones.available.names, 0, 3)
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true
}

module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  version         = "~> 20.0"

  cluster_name    = "${var.project}-eks"
  cluster_version = var.eks_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.public_subnets

  # ВАЖНО: включаем публичный endpoint и отключаем приватный
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = false

  # (опционально можно сузить CIDR)
  # cluster_endpoint_public_access_cidrs = ["<твой_публичный_IP>/32"]

  eks_managed_node_groups = {
    default = {
      desired_size   = 1
      min_size       = 0
      max_size       = 2
      instance_types = ["t3.micro"] # или что у тебя сейчас
      subnet_ids     = module.vpc.public_subnets
    }
  }
}

resource "aws_ecr_repository" "app" {
  name                 = "${var.project}-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

output "cluster_name"   { value = module.eks.cluster_name }
output "ecr_url"        { value = aws_ecr_repository.app.repository_url }
output "kubeconfig_cmd" {
  value = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

