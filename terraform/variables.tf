variable "app_name" {
  description = "Application name"
  type        = string
  default     = "foxglove-studio"
}

variable "channel" {
  description = "Charm channel"
  type        = string
  default     = "latest/edge"
}

variable "config" {
  description = "Config options as in the ones we pass in juju config"
  type        = map(string)
  default     = {}
}

# We use constraints to set AntiAffinity in K8s
# https://discourse.charmhub.io/t/pod-priority-and-affinity-in-juju-charms/4091/13?u=jose
variable "constraints" {
  description = "Constraints to be applied"
  type        = string
  default     = ""
}

variable "model" {
  description = "Model name (must be a machine model)"
  type        = string
}

variable "revision" {
  description = "Charm revision"
  type        = number
  nullable    = true
  default     = null
}

variable "units" {
  description = "Number of units"
  type        = number
  default     = 1
}

variable "resources" {
  description = "Resources used by the charm"
  type        = map(string)
  default = {
    foxglove-studio-image : "ghcr.io/ubuntu-robotics/foxglove-studio:dev"
  }
}
