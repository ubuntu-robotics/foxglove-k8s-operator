run "basic_deploy" {

  assert {
    condition     = module.foxglove_studio_k8s.app_name == "foxglove-studio"
    error_message = "app_name did not match expected default value"
  }

  # Test requires integration endpoints - check count
  assert {
    condition     = length(module.foxglove_studio_k8s.requires) == 4
    error_message = "Expected 4 required integration endpoints"
  }

  # Test requires integration endpoints - check specific keys
  assert {
    condition     = contains(keys(module.foxglove_studio_k8s.requires), "catalogue")
    error_message = "requires output is missing 'catalogue' endpoint"
  }

  assert {
    condition     = contains(keys(module.foxglove_studio_k8s.requires), "ingress")
    error_message = "requires output is missing 'ingress' endpoint"
  }

  assert {
    condition     = contains(keys(module.foxglove_studio_k8s.requires), "logging")
    error_message = "requires output is missing 'logging' endpoint"
  }

  assert {
    condition     = contains(keys(module.foxglove_studio_k8s.requires), "tracing")
    error_message = "requires output is missing 'tracing' endpoint"
  }

  # Test requires integration endpoints - check exact values
  assert {
    condition     = module.foxglove_studio_k8s.requires["catalogue"] == "catalogue"
    error_message = "requires.catalogue endpoint did not match expected value"
  }

  assert {
    condition     = module.foxglove_studio_k8s.requires["ingress"] == "ingress"
    error_message = "requires.ingress endpoint did not match expected value"
  }

  assert {
    condition     = module.foxglove_studio_k8s.requires["logging"] == "logging"
    error_message = "requires.logging endpoint did not match expected value"
  }

  assert {
    condition     = module.foxglove_studio_k8s.requires["tracing"] == "tracing"
    error_message = "requires.tracing endpoint did not match expected value"
  }

  # Test provides integration endpoints - check count
  assert {
    condition     = length(module.foxglove_studio_k8s.provides) == 2
    error_message = "Expected 2 provided integration endpoints"
  }

  # Test provides integration endpoints - check specific keys
  assert {
    condition     = contains(keys(module.foxglove_studio_k8s.provides), "grafana_dashboard")
    error_message = "provides output is missing 'grafana_dashboard' endpoint"
  }

  assert {
    condition     = contains(keys(module.foxglove_studio_k8s.provides), "probes")
    error_message = "provides output is missing 'probes' endpoint"
  }

  # Test provides integration endpoints - check exact values
  assert {
    condition     = module.foxglove_studio_k8s.provides["grafana_dashboard"] == "grafana-dashboard"
    error_message = "provides.grafana_dashboard endpoint did not match expected value"
  }

  assert {
    condition     = module.foxglove_studio_k8s.provides["probes"] == "probes"
    error_message = "provides.probes endpoint did not match expected value"
  }
}
