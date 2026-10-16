variable "aws_region" {
  type        = string
  description = "AWS region for the EKS cluster and ECR repository."
  default     = "us-east-1"
}

variable "cluster_name" {
  type        = string
  description = "Name used for the EKS cluster and related resources."
  default     = "blame-the-deploy"
}

variable "kubernetes_version" {
  type        = string
  description = "EKS Kubernetes version."
  default     = "1.35"
}

variable "node_instance_types" {
  type        = list(string)
  description = "EC2 instance types for the EKS managed node group."
  default     = ["t3.large"]
}

variable "node_min_size" {
  type        = number
  description = "Minimum number of EKS worker nodes."
  default     = 2
}

variable "node_max_size" {
  type        = number
  description = "Maximum number of EKS worker nodes."
  default     = 3
}

variable "node_desired_size" {
  type        = number
  description = "Initial desired number of EKS worker nodes."
  default     = 2
}

variable "cluster_endpoint_public_access_cidrs" {
  type        = list(string)
  description = "CIDR ranges allowed to reach the public EKS API endpoint. Restrict this to trusted IPs."

  validation {
    condition = (
      length(var.cluster_endpoint_public_access_cidrs) > 0 &&
      !contains(var.cluster_endpoint_public_access_cidrs, "0.0.0.0/0")
    )
    error_message = "Provide at least one trusted CIDR and do not expose the EKS API to 0.0.0.0/0."
  }
}
