variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "name" {
  type    = string
  default = "predixion-call-webhook"
}

variable "environment" {
  type    = string
  default = "candidate"
}

variable "demo_http_only" {
  type        = bool
  default     = false
  description = "Temporary demo mode: HTTP on public subnets, one API task, no CRM worker or GitHub OIDC role."
}

variable "vpc_id" {
  type        = string
  description = "VPC containing the supplied public and private subnets."
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "At least two public subnets in separate Availability Zones for the ALB."
}

variable "private_subnet_ids" {
  type        = list(string)
  default     = []
  description = "Private subnets with NAT egress or VPC endpoints for ECS dependencies."
}

variable "certificate_arn" {
  type        = string
  default     = ""
  description = "ACM certificate ARN in ap-south-1 for the webhook hostname."
}

variable "crm_url" {
  type        = string
  default     = ""
  description = "CRM retry scheduling endpoint; use HTTPS."
}

variable "crm_secret_arn" {
  type        = string
  default     = ""
  description = "Existing Secrets Manager secret containing the raw CRM bearer token."
}

variable "github_repository" {
  type        = string
  default     = ""
  description = "GitHub owner/repository allowed to assume the OIDC deployment role."
}