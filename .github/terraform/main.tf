provider "aws" {
  region = var.aws_region
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = var.cluster_name
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)
  image_tag_prefixes = [
    "currencyservice-",
    "loadgenerator-",
    "productcatalogservice-",
    "checkoutservice-",
    "shippingservice-",
    "cartservice-",
    "emailservice-",
    "paymentservice-",
    "frontend-",
    "recommendationservice-",
    "adservice-",
    "redis-",
    "busybox-",
    "incident-agent-",
  ]
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${local.name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = local.azs
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
  }
}

resource "aws_ecr_repository" "online_boutique" {
  name                 = "online-boutique"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "online_boutique" {
  repository = aws_ecr_repository.online_boutique.name

  policy = jsonencode({
    rules = [
      for index, prefix in local.image_tag_prefixes : {
        rulePriority = index + 1
        description  = "Retain the most recent 30 ${prefix} images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = [prefix]
          countType     = "imageCountMoreThan"
          countNumber   = 30
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

data "aws_iam_policy_document" "jenkins_agent_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "jenkins_agent" {
  name               = "${local.name}-jenkins-agent"
  assume_role_policy = data.aws_iam_policy_document.jenkins_agent_assume_role.json
}

resource "aws_iam_instance_profile" "jenkins_agent" {
  name = "${local.name}-jenkins-agent"
  role = aws_iam_role.jenkins_agent.name
}

data "aws_iam_policy_document" "jenkins_ecr_push" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.online_boutique.arn]
  }
}

resource "aws_iam_role_policy" "jenkins_ecr_push" {
  name   = "${local.name}-ecr-push"
  role   = aws_iam_role.jenkins_agent.id
  policy = data.aws_iam_policy_document.jenkins_ecr_push.json
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name                           = local.name
  cluster_version                        = var.kubernetes_version

  cluster_endpoint_public_access           = true
  cluster_endpoint_public_access_cidrs     = var.cluster_endpoint_public_access_cidrs
  cluster_endpoint_private_access          = true
  enable_cluster_creator_admin_permissions = true
  enable_irsa                              = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_addons = {
    coredns                = {}
    eks-pod-identity-agent = {}
    kube-proxy             = {}
    vpc-cni                = {}
  }

  eks_managed_node_groups = {
    default = {
      instance_types = var.node_instance_types
      min_size       = var.node_min_size
      max_size       = var.node_max_size
      desired_size   = var.node_desired_size
    }
  }

  access_entries = {
    jenkins_agent = {
      principal_arn = aws_iam_role.jenkins_agent.arn

      policy_associations = {
        online_boutique_edit = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
          access_scope = {
            type       = "namespace"
            namespaces = ["online-boutique"]
          }
        }
      }
    }
  }

  depends_on = [
    aws_iam_role_policy.jenkins_ecr_push,
  ]
}

data "aws_iam_policy_document" "jenkins_eks_describe" {
  statement {
    actions   = ["eks:DescribeCluster"]
    resources = [module.eks.cluster_arn]
  }
}

resource "aws_iam_role_policy" "jenkins_eks_describe" {
  name   = "${local.name}-eks-describe"
  role   = aws_iam_role.jenkins_agent.id
  policy = data.aws_iam_policy_document.jenkins_eks_describe.json
}
