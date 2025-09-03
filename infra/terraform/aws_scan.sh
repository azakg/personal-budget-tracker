#!/usr/bin/env bash
set -euo pipefail

# Настройки (можешь поменять)
PROJECT_TAG="budget-vpc"      # тег Name для VPC
ECR_NAME="budget-api"         # имя репозитория ECR

# Чтобы AWS CLI не открывал pager
export AWS_PAGER=""

# Если хочешь явно указать профиль:
# export AWS_PROFILE=default

echo "Scanning all AWS regions for leftover resources..."
echo

REGIONS=$(aws ec2 describe-regions --query "Regions[].RegionName" --output text)

for region in $REGIONS; do
  echo "===== Region: $region ====="

  # EKS clusters
  eks_out=$(aws eks list-clusters --region "$region" --output json)
  echo "EKS clusters: $eks_out"

  # VPC by Name tag
  vpcs=$(aws ec2 describe-vpcs \
    --region "$region" \
    --filters "Name=tag:Name,Values=$PROJECT_TAG" \
    --query "Vpcs[].VpcId" --output json)
  echo "VPCs (tag Name=$PROJECT_TAG): $vpcs"

  # ECR repository (ECR — региональный)
  # Если в регионе нет ECR API, команда просто вернёт пусто/ошибку — подавим ошибку
  ecr_repo=$(aws ecr describe-repositories \
    --region "$region" \
    --query "repositories[?repositoryName=='$ECR_NAME'].repositoryUri" \
    --output json 2>/dev/null || echo "[]")
  echo "ECR repo '$ECR_NAME': $ecr_repo"

  # Load Balancers (ALB/NLB) — elbv2
  elbv2=$(aws elbv2 describe-load-balancers \
    --region "$region" \
    --query "LoadBalancers[].LoadBalancerName" \
    --output json 2>/dev/null || echo "[]")
  echo "ELBv2 (ALB/NLB): $elbv2"

  # Classic ELB (устаревшие, но на всякий)
  clb=$(aws elb describe-load-balancers \
    --region "$region" \
    --query "LoadBalancerDescriptions[].LoadBalancerName" \
    --output json 2>/dev/null || echo "[]")
  echo "Classic ELB: $clb"

  # NAT Gateways
  nat=$(aws ec2 describe-nat-gateways \
    --region "$region" \
    --query "NatGateways[].NatGatewayId" --output json 2>/dev/null || echo "[]")
  echo "NAT Gateways: $nat"

  # Elastic IPs
  eips=$(aws ec2 describe-addresses \
    --region "$region" \
    --query "Addresses[].PublicIp" --output json 2>/dev/null || echo "[]")
  echo "Elastic IPs: $eips"

  echo
done

echo "Scan complete."

