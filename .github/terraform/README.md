# AWS infrastructure

This Terraform configuration provisions the AWS infrastructure used by the Jenkins deployment pipeline: a VPC, an Amazon EKS cluster with managed nodes, an Amazon ECR repository, and an EC2 instance profile for Jenkins agents. The Jenkins role can push images to this ECR repository and edit resources in the `online-boutique` Kubernetes namespace.

See [SETUP.md](../../SETUP.md) for prerequisites, network access requirements, pipeline configuration, deployment, and cleanup instructions.

Terraform uses local state unless a remote backend is configured. Do not commit the state file. For team use, configure a versioned and encrypted S3 backend with state locking before applying the configuration.

The default public EKS API CIDR is open for demonstration convenience. Override `cluster_endpoint_public_access_cidrs` with trusted administrator and Jenkins CIDRs before applying. Restrict or disable the public endpoint for production.
