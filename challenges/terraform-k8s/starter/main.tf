# ──────────────────────────────────────────────
# Providers
# ──────────────────────────────────────────────
# Both providers read your kubeconfig to authenticate
# to the kind cluster. Since you just created the cluster,
# your current context is already set to kind-terraform-lab.

provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = "kind-terraform-lab"
}

provider "helm" {
  kubernetes {
    config_path    = "~/.kube/config"
    config_context = "kind-terraform-lab"
  }
}

# ──────────────────────────────────────────────
# Namespace
# ──────────────────────────────────────────────
# TODO: Create a namespace called "terraform-challenge"
#       with labels: managed-by = "terraform", challenge = "terraform-k8s"

resource "kubernetes_namespace" "app" {
  # Fill this in — see Part 4 of the README
}

# ──────────────────────────────────────────────
# ConfigMap
# ──────────────────────────────────────────────
# TODO: Create a ConfigMap called "app-config" in the namespace above
#       with keys: APP_ENV, LOG_LEVEL, MESSAGE
#
# Hint: reference the namespace with
#       kubernetes_namespace.app.metadata[0].name

resource "kubernetes_config_map" "app" {
  # Fill this in — see Part 4 of the README
}

# ──────────────────────────────────────────────
# Secret
# ──────────────────────────────────────────────
# TODO: Create a Secret called "app-secret" in the namespace
#       with keys: DB_PASSWORD, API_KEY

resource "kubernetes_secret" "app" {
  # Fill this in — see Part 5 of the README
}

# ──────────────────────────────────────────────
# Deployment
# ──────────────────────────────────────────────
# TODO: Create a Deployment called "challenge-app"
#       - 2 replicas
#       - image: nginx:1.27
#       - inject the ConfigMap as env vars (env_from)
#       - inject DB_PASSWORD from the Secret (env with secret_key_ref)
#       - resource requests and limits
#       - readiness probe on port 80

resource "kubernetes_deployment" "app" {
  # Fill this in — see Part 6 of the README
}

# ──────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────
# TODO: Create a NodePort Service called "challenge-app"
#       - port 80 → target port 80
#       - node_port 30080 (matches kind config)

resource "kubernetes_service" "app" {
  # Fill this in — see Part 6 of the README
}

# ──────────────────────────────────────────────
# Helm Release
# ──────────────────────────────────────────────
# TODO: Deploy the bitnami/nginx chart as a ClusterIP service
#       in the same namespace

resource "helm_release" "nginx_extra" {
  # Fill this in — see Part 7 of the README
}
