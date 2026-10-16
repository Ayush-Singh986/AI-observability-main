output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "aws_region" {
  description = "AWS region used for the cluster."
  value       = var.aws_region
}

output "ecr_registry" {
  description = "Registry hostname used by the Jenkins image mirroring stage."
  value       = split("/", aws_ecr_repository.online_boutique.repository_url)[0]
}

output "ecr_repository_url" {
  description = "ECR repository where the demo images are mirrored."
  value       = aws_ecr_repository.online_boutique.repository_url
}

output "jenkins_instance_profile_name" {
  description = "Instance profile to attach to Jenkins EC2 agents."
  value       = aws_iam_instance_profile.jenkins_agent.name
}

output "jenkins_role_arn" {
  description = "IAM role used by Jenkins EC2 agents."
  value       = aws_iam_role.jenkins_agent.arn
}

output "private_subnet_ids" {
  description = "Private subnet IDs for EKS nodes and Jenkins agents."
  value       = module.vpc.private_subnets
}
